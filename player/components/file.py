from PySide6.QtWidgets import (
	QHBoxLayout,
	QVBoxLayout,
	QLineEdit,
	QPushButton,
	QFileDialog,
	QFrame,
	QProgressBar,
)

from pathlib import Path


class FileLayout(QVBoxLayout):
	def __init__(self):
		super().__init__()

		self.browse_layout = QHBoxLayout()

		self.file_edit = QLineEdit()
		self.file_edit.setPlaceholderText("Select an audio file...")
		_default = Path(__file__).resolve().parent.parent / "burn.mp3"
		self.file_edit.setText(str(_default) if _default.exists() else "")
		self.file_edit.setReadOnly(True)
		self.file_edit.setFixedWidth(200)

		browse_btn = QPushButton("Browse")
		browse_btn.clicked.connect(self._browse)
		self.browse_layout.addWidget(self.file_edit, 1)
		self.browse_layout.addWidget(browse_btn)

		divider = QFrame()
		divider.setFrameShape(QFrame.Shape.VLine)
		divider.setFrameShadow(QFrame.Shadow.Sunken)
		self.browse_layout.addWidget(divider)

		load_btn = QPushButton("Load")
		load_btn.clicked.connect(self._load)
		self.browse_layout.addWidget(load_btn)

		self.addLayout(self.browse_layout)

		self.progress_bar = QProgressBar()
		self.progress_bar.setRange(0, 100)
		self.progress_bar.setValue(0)
		self.addWidget(self.progress_bar)

	def _browse(self):
		current = self.file_edit.text().strip()

		start_dir = str(Path(__file__).resolve().parent.parent)
		if current:
			start_path = Path(current)
			start_dir = str(start_path.parent if start_path.is_file() else start_path)
		path, _ = QFileDialog.getOpenFileName(
			self.file_edit, "Select audio file", start_dir,
			"Audio (*.mp3 *.wav *.flac *.m4a *.ogg);;All files (*)"
		)
		if path:
			self.file_edit.setText(path)

	def _load(self):
		path = Path(self.file_edit.text().strip())
		if not path.exists():
			return
		self.parent().parent().parent().load_file(path)

	def update_progress(self, progress: float):
		self.progress_bar.setValue(int(progress * 100))
