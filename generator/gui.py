from PySide6.QtCore import Qt, Signal, QPoint
from PySide6.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
    QHBoxLayout,
    QGridLayout,
    QPushButton,
    QFrame,
    QSizePolicy,
    QVBoxLayout,
    QLabel,
)
from PySide6.QtGui import QKeyEvent, QIcon, QPixmap, QColor

KEY_TO_NOTE = {
    Qt.Key.Key_Z: "C4",
    Qt.Key.Key_S: "C#4",
    Qt.Key.Key_X: "D4",
    Qt.Key.Key_D: "D#4",
    Qt.Key.Key_C: "E4",
    Qt.Key.Key_V: "F4",
    Qt.Key.Key_G: "F#4",
    Qt.Key.Key_B: "G4",
    Qt.Key.Key_H: "G#4",
    Qt.Key.Key_N: "A4",
    Qt.Key.Key_J: "A#4",
    Qt.Key.Key_M: "B4",
    #
    Qt.Key.Key_Q: "C5",
    Qt.Key.Key_2: "C#5",
    Qt.Key.Key_W: "D5",
    Qt.Key.Key_3: "D#5",
    Qt.Key.Key_E: "E5",
    Qt.Key.Key_R: "F5",
    Qt.Key.Key_5: "F#5",
    Qt.Key.Key_T: "G5",
    Qt.Key.Key_6: "G#5",
    Qt.Key.Key_Y: "A5",
    Qt.Key.Key_7: "A#5",
    Qt.Key.Key_U: "B5",
}

OFFSET_WITHIN_OCTAVE = {
    "C": 0,
    "C#": 3,
    "D": 4,
    "D#": 7,
    "E": 8,
    "F": 12,
    "F#": 15,
    "G": 16,
    "G#": 19,
    "A": 20,
    "A#": 23,
    "B": 24,
}

NOTE_ORDER = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]

WIDTH = 600
HEIGHT = 160

DEBUG = False

def note_to_frequency(note: str) -> float:
    """Convert note name (e.g. 'C4') to frequency in Hz."""
    name, octave = note[:-1], int(note[-1])
    idx = NOTE_ORDER.index(name)
    # A4 = 440 Hz
    semitones = (octave - 4) * 12 + idx - 9  # A is index 9
    return 440 * (2 ** (semitones / 12))

class PianoKey(QPushButton):
    """A single piano key (white or black) with press feedback."""

    def __init__(self, note: str, is_black: bool, parent=None):
        super().__init__(parent)
        self.note = note
        self.is_black = is_black
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        # Don't use checkable - it makes clicks toggle instead of press+release.
        # Use keyboardPressed property for physical key visuals instead.
        self.setProperty("keyboardPressed", False)
        self._apply_style()

    def _apply_style(self):
        if self.is_black:
            self.setStyleSheet("""
                QPushButton {
                    background-color: #111;
                    border: 1px solid #333;
                    border-radius: 0 0 4px 4px;
                }
                QPushButton:hover {
                    background-color: #222;
                }
                QPushButton:pressed, QPushButton[keyboardPressed="true"] {
                    background-color: #444;
                }
            """)
        else:
            self.setStyleSheet("""
                QPushButton {
                    background-color: #fff;
                    border: 1px solid #bbb;
                    border-radius: 0 0 6px 6px;
                }
                QPushButton:hover {
                    background-color: #eee;
                }
                QPushButton:pressed, QPushButton[keyboardPressed="true"] {
                    background-color: #ccc;
                }
            """)

    def handle_key_event(self, pressed: bool):
        self.setProperty("keyboardPressed", pressed)
        self.style().unpolish(self)
        self.style().polish(self)


class PianoWidget(QFrame):
    """Virtual piano keyboard with clickable keys."""

    note_pressed = Signal(str)
    note_released = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._keys: dict[str, PianoKey] = {}
        self._setup_ui()

    def _setup_ui(self):
        self.setFixedHeight(HEIGHT - (2 * 8))
        self.setFixedWidth(WIDTH - (2 * 8))
        self.setStyleSheet("background-color: #00f;")

        self.layout = QGridLayout()
        self.layout.setSpacing(0)
        self.layout.setContentsMargins(0,0,0,0)

        self.setup_keys(octave=4)
        self.setup_keys(octave=5)

        self.layout.setRowStretch(0, 3)
        self.layout.setRowStretch(1, 1)
        self.setLayout(self.layout)
    
    def setup_keys(self, octave: int = 4):
        black_keys = []
        white_keys = []

        for i in range(12):
            note = NOTE_ORDER[i]
            offsetWithinOctave = OFFSET_WITHIN_OCTAVE[note]
            full_note = f"{note}{octave}"
            if note.endswith("#"):
                key = PianoKey(full_note, True)
                self._keys[full_note] = key
                # black key spans 2 columns, overlapping below keys
                black_keys.append((key, offsetWithinOctave))
            else:
                key = PianoKey(full_note, False)
                self._keys[full_note] = key
                white_keys.append((key, offsetWithinOctave))
            key.pressed.connect(lambda n=full_note: self.note_pressed.emit(n))
            key.released.connect(lambda n=full_note: self.note_released.emit(n))

        for key in white_keys:
            self.layout.addWidget(key[0], 0, key[1] + octave * 28, 2, 4)

        for key in black_keys:
            self.layout.addWidget(key[0], 0, key[1] + octave * 28, 1, 2)


def on_note(note: str, pressed: bool):
    """Shared callback for both GUI and keyboard events."""
    freq = note_to_frequency(note)
    action = "pressed" if pressed else "released"
    if DEBUG:
        print(f"Note {note} ({freq:.1f} Hz) {action}")


class DraggableArea(QWidget):
    """Invisible widget that moves the window when clicked and dragged."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._drag_pos: QPoint | None = None

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = event.globalPosition().toPoint()

    def mouseMoveEvent(self, event):
        if self._drag_pos is not None and event.buttons() & Qt.MouseButton.LeftButton:
            delta = event.globalPosition().toPoint() - self._drag_pos
            window = self.window()
            window.move(window.pos() + delta)
            self._drag_pos = event.globalPosition().toPoint()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = None


class MainWindow(QMainWindow):
    def __init__(self, engine=None):
        super().__init__()
        self.engine = engine
        self.setWindowTitle("Virtual Piano")
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint)
        self.piano = PianoWidget()

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        margin_style = "background-color: #482000;"

        # Top margin
        top_bar = DraggableArea(container)
        top_bar.setFixedHeight(8)
        top_bar.setStyleSheet(margin_style)
        layout.addWidget(top_bar)
        
        middle = QWidget()
        middle_layout = QHBoxLayout(middle)
        middle_layout.setContentsMargins(0, 0, 0, 0)
        middle_layout.setSpacing(0)
        for side, size in [("left", 8), ("right", 8)]:
            margin = DraggableArea(middle)
            margin.setFixedWidth(size)
            margin.setStyleSheet(margin_style)
            middle_layout.addWidget(margin)
            if side == "left":
                middle_layout.addWidget(self.piano, 1)
        layout.addWidget(middle)

        # Bottom margin
        bottom_bar = DraggableArea(container)
        bottom_bar.setFixedHeight(8)
        bottom_bar.setStyleSheet(margin_style)
        layout.addWidget(bottom_bar)

        self.setCentralWidget(container)
        self.setFixedSize(WIDTH, HEIGHT)

        self.piano.note_pressed.connect(lambda n: self.on_note(n, True))
        self.piano.note_released.connect(lambda n: self.on_note(n, False))

    def keyPressEvent(self, event):
        if event.isAutoRepeat():
            return
        if isinstance(event, QKeyEvent):
            try:
                note = KEY_TO_NOTE[event.key()]
                self.on_note(note, True)
            except KeyError:
                pass

    def keyReleaseEvent(self, event):
        if event.isAutoRepeat():
            return
        if isinstance(event, QKeyEvent):
            try:
                note = KEY_TO_NOTE[event.key()]
                self.on_note(note, False)
            except KeyError:
                pass

    def on_note(self, note: str, pressed: bool):
        freq = note_to_frequency(note)
        action = "pressed" if pressed else "released"
        if DEBUG:
            print(f"Note {note} ({freq:.1f} Hz) {action}")
        keyWidget = self.piano._keys[note]
        keyWidget.handle_key_event(pressed)
        if self.engine is not None:
            if pressed:
                self.engine.play_note(freq)
            else:
                self.engine.stop_note(freq)
