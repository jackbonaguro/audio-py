from PySide6.QtWidgets import QApplication

from engine import AudioEngine
from gui import MainWindow

if __name__ == "__main__":
	# Initialize systems
	app = QApplication([])
	engine = AudioEngine()
	window = MainWindow(engine=engine)

	# Connect signals
	engine.fileLoaded.connect(window.on_file_loaded)

	# Run
	window.show()
	app.exec()
