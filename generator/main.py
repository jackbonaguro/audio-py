from PySide6.QtWidgets import QApplication

from engine import AudioEngine
from gui import MainWindow


if __name__ == "__main__":
    app = QApplication([])
    engine = AudioEngine()
    window = MainWindow(engine=engine)
    window.show()
    app.exec()
