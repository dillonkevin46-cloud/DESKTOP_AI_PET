import sys
import time
from dataclasses import dataclass
from PyQt6.QtWidgets import (
    QApplication, QWidget, QLabel, QMenu, QSystemTrayIcon, QVBoxLayout
)
from PyQt6.QtCore import Qt, QTimer, QPoint, QRect, QThread, pyqtSignal
from PyQt6.QtGui import QPixmap, QAction, QIcon, QGuiApplication

@dataclass
class PetState:
    hunger: int = 0
    energy: int = 100
    boredom: int = 0
    affection: int = 50
    current_activity: str = 'idle'

class StatDecayWorker(QThread):
    """Background thread that manages the biological clock of the pet."""
    state_updated = pyqtSignal(object)

    def __init__(self, state: PetState):
        super().__init__()
        self.state = state
        self.running = True

    def run(self):
        ticks_passed = 0
        while self.running:
            # Sleep in smaller chunks to allow faster thread termination
            time.sleep(0.5)
            ticks_passed += 0.5

            if ticks_passed >= 5:
                # Drain energy, increase hunger and boredom
                self.state.energy = max(0, self.state.energy - 5)
                self.state.hunger = min(100, self.state.hunger + 5)
                self.state.boredom = min(100, self.state.boredom + 5)

                # Emit the updated state back to the main GUI thread
                self.state_updated.emit(self.state)
                ticks_passed = 0

    def stop(self):
        self.running = False
        self.wait()

class SpriteAnimator:
    """Handles loading and animating a sprite sheet."""
    def __init__(self, sprite_sheet_path: str, frame_width: int, frame_height: int, frame_count: int, update_interval: int = 100):
        self.sprite_sheet_path = sprite_sheet_path
        self.frame_width = frame_width
        self.frame_height = frame_height
        self.frame_count = frame_count
        self.current_frame = 0

        self.frames = []
        self._load_frames()

        self.timer = QTimer()
        self.timer.setInterval(update_interval)

    def _load_frames(self):
        sprite_sheet = QPixmap(self.sprite_sheet_path)
        if sprite_sheet.isNull():
            # If the image failed to load, we can create dummy empty pixmaps or log a warning
            print(f"Warning: Could not load sprite sheet from {self.sprite_sheet_path}")
            # Create a placeholder transparent frame if file not found
            placeholder = QPixmap(self.frame_width, self.frame_height)
            placeholder.fill(Qt.GlobalColor.transparent)
            self.frames = [placeholder] * self.frame_count
            return

        for i in range(self.frame_count):
            # Assuming a horizontal sprite sheet for simplicity
            rect = QRect(i * self.frame_width, 0, self.frame_width, self.frame_height)
            frame = sprite_sheet.copy(rect)
            self.frames.append(frame)

    def start(self, callback):
        """Starts the animation, calling `callback` with the current frame's pixmap."""
        self._callback = callback
        self.timer.timeout.connect(self._update_frame)
        self.timer.start()

    def stop(self):
        self.timer.stop()

    def _update_frame(self):
        if not self.frames:
            return

        frame = self.frames[self.current_frame]
        if hasattr(self, '_callback'):
            self._callback(frame)

        self.current_frame = (self.current_frame + 1) % self.frame_count

class PetWindow(QWidget):
    """The main transparent, frameless window for the virtual pet."""
    def __init__(self, sprite_path: str):
        super().__init__()

        self.drag_position = QPoint()
        self.total_screen_geometry = QRect()

        self.state = PetState()

        self._setup_window()
        self._setup_multi_monitor()
        self._setup_ui()
        self._setup_tray()
        self._setup_animation(sprite_path)
        self._setup_worker()

    def _setup_worker(self):
        self.worker = StatDecayWorker(self.state)
        self.worker.state_updated.connect(self.update_pet_state)
        self.worker.start()

    def update_pet_state(self, state: PetState):
        # Threshold Logic
        if state.energy < 10 and state.current_activity != 'sleeping':
            state.current_activity = 'sleeping'
            print("State change: Energy is low! Switching to sleep sprite.", flush=True)
        elif state.hunger > 80 and state.current_activity != 'hungry':
            state.current_activity = 'hungry'
            print("State change: Very hungry! Switching to hungry sprite.", flush=True)
        else:
            print(f"Tick - Energy: {state.energy}, Hunger: {state.hunger}, Boredom: {state.boredom}, Activity: {state.current_activity}", flush=True)

    def _setup_window(self):
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool  # Hides from taskbar on some systems
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

    def _setup_multi_monitor(self):
        screens = QGuiApplication.screens()
        total_rect = QRect()
        for screen in screens:
            total_rect = total_rect.united(screen.geometry())

        self.total_screen_geometry = total_rect
        print(f"Total bounding geometry of all monitors: {self.total_screen_geometry}")

    def _setup_ui(self):
        # We need a layout to hold the QLabel
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)

        self.image_label = QLabel(self)
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.layout.addWidget(self.image_label)

    def _setup_tray(self):
        self.tray_icon = QSystemTrayIcon(self)

        # Creating a red placeholder icon for the tray
        placeholder_icon = QPixmap(16, 16)
        placeholder_icon.fill(Qt.GlobalColor.red)
        self.tray_icon.setIcon(QIcon(placeholder_icon))

        self.tray_menu = QMenu(self)

        quit_action = QAction("Quit", self)
        quit_action.triggered.connect(self.quit_app)
        self.tray_menu.addAction(quit_action)

        self.tray_icon.setContextMenu(self.tray_menu)
        self.tray_icon.show()

    def _setup_animation(self, sprite_path: str):
        # Placeholder dimensions, adjust these for actual sprite sheet
        frame_w = 64
        frame_h = 64
        frame_count = 4

        self.animator = SpriteAnimator(sprite_path, frame_w, frame_h, frame_count)
        self.animator.start(self._on_frame_updated)

    def _on_frame_updated(self, pixmap: QPixmap):
        self.image_label.setPixmap(pixmap)
        self.resize(pixmap.size())

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.drag_position = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self.drag_position)
            event.accept()

    def quit_app(self):
        print("Stopping worker thread safely...")
        self.worker.stop()
        QApplication.instance().quit()

def main():
    app = QApplication(sys.argv)

    # Ensure application doesn't close when the main window is hidden
    # (Though we keep ours visible, it's good practice for tray apps)
    app.setQuitOnLastWindowClosed(False)

    # Placeholder sprite path
    SPRITE_SHEET_PATH = "placeholder_sprite.png"

    pet = PetWindow(SPRITE_SHEET_PATH)
    pet.show()

    sys.exit(app.exec())

if __name__ == "__main__":
    main()
