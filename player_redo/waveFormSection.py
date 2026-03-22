import numpy as np
from PySide6.QtWidgets import QWidget
from PySide6.QtGui import QPainter, QColor, QPen, QImage
from PySide6.QtCore import Qt, QTimer

from audioBuffer import AudioBuffer

class WaveformWidget(QWidget):
	"""Paints a waveform from preloaded PCM chunks."""

	def __init__(self, parent=None):
		super().__init__(parent)
		self.setMinimumHeight(80)
		self.setStyleSheet("background-color: #1a1a1a; border-radius: 4px;")
		self._buffer: AudioBuffer | None = None
		self._waveform_data: np.ndarray | None = None
		self._channels = 0
		self._waveform: np.ndarray | None = None
		self._cached_image: QImage | None = None
		self._resize_timer = QTimer(self)
		self._resize_timer.setSingleShot(True)
		self._resize_timer.timeout.connect(self._recompute_waveform)

	def set_audio(self, buffer: AudioBuffer):
		"""Set from AudioBuffer (used when engine runs in-process)."""
		self._buffer = buffer
		self._channels = 2
		self._waveform_data = None
		self._recompute_waveform()

	def set_waveform_data(self, waveform: np.ndarray):
		"""Set from precomputed waveform (mins, maxs per pixel). Shape: (width, 2)."""
		self._buffer = None
		self._waveform_data = waveform
		self._recompute_waveform()

	def _recompute_waveform(self):
		w = self.width() or 400
		if w <= 0:
			self._waveform = None
			self._cached_image = None
		elif self._waveform_data is not None:
			# Precomputed from remote process; may need to resample to current width
			wd = self._waveform_data.shape[0]
			if wd == w:
				self._waveform = self._waveform_data
			else:
				# Simple linear resample
				indices = np.linspace(0, wd - 1, w).astype(np.intp)
				self._waveform = self._waveform_data[indices]
			self._cached_image = self._waveform_to_image(self._waveform)
		elif self._buffer:
			self._waveform = self._buffer_to_waveform(self._buffer, w)
			self._cached_image = self._waveform_to_image(self._waveform)
		else:
			self._waveform = None
			self._cached_image = None
		self.update()

	def resizeEvent(self, event):
		super().resizeEvent(event)
		if self._buffer or self._waveform_data is not None:
			# Debounce: recompute only after resize settles (keeps main thread free during drag)
			self._resize_timer.start(150)

	def paintEvent(self, event):
		super().paintEvent(event)
		if self._cached_image is None or self._cached_image.isNull():
			return
		painter = QPainter(self)
		# Single draw call — fast, avoids blocking the audio callback during repaint
		painter.drawImage(self.rect(), self._cached_image)

	def _waveform_to_image(self, waveform: np.ndarray) -> QImage:
		"""Render waveform mins/maxs to a QImage. Done once per recompute, not per paint."""
		w, _ = waveform.shape
		h = max(80, self.height())
		img = QImage(w, h, QImage.Format.Format_ARGB32)
		img.fill(0xFF1A1A1A)  # #1a1a1a background
		mid, amp = h / 2, (h / 2) * 0.95
		pen = QPen(QColor(100, 180, 255))
		pen.setWidth(1)
		painter = QPainter(img)
		painter.setPen(pen)
		painter.setBrush(Qt.BrushStyle.NoBrush)
		for x in range(w):
			mn, mx = waveform[x]
			painter.drawLine(int(x), int(mid - mx * amp), int(x), int(mid - mn * amp))
		painter.end()
		return img

	def _buffer_to_waveform(self, buffer: AudioBuffer, width: int) -> np.ndarray:
		if not buffer or buffer.sample_len <= 0:
			return np.zeros((width, 2))
		# AudioBuffer stores float32 in [-1, 1], shape (sample_len * 2,) for stereo
		frames = np.reshape(buffer.buffer[:buffer.write_pos], (-1, 2))
		mono = frames.mean(axis=1).astype(np.float32)
		n = len(mono)
		if n == 0:
			return np.zeros((width, 2))
		samples_per_pixel = max(1, n // width)
		mins = np.zeros(width)
		maxs = np.zeros(width)
		for i in range(width):
			start = i * samples_per_pixel
			end = min((i + 1) * samples_per_pixel, n)
			if start < end:
				mins[i] = mono[start:end].min()
				maxs[i] = mono[start:end].max()
		return np.column_stack((mins, maxs))
