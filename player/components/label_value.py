from PySide6.QtWidgets import QHBoxLayout, QLabel, QWidget
from PySide6.QtGui import QFontDatabase, QFontMetrics


class LabelValuePair(QWidget):
	"""Label + monospace value with fixed character width. Reusable for time, tempo, track name, etc."""

	def __init__(
		self,
		label: str,
		sample_strings: list[str],
		tooltip: str | None = None,
	):
		super().__init__()
		layout = QHBoxLayout(self)
		layout.setContentsMargins(0, 0, 0, 0)
		layout.setSpacing(0)

		self._label = QLabel(label)
		mono = QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont)
		mono.setFixedPitch(True)
		fm = QFontMetrics(mono)
		width = max(fm.horizontalAdvance(s) for s in sample_strings) + 1 if sample_strings else 50

		self._value = QLabel(sample_strings[0] if sample_strings else "")
		self._value.setFont(mono)
		self._value.setMinimumWidth(width)
		if tooltip:
			self._value.setToolTip(tooltip)

		layout.addWidget(self._label)
		layout.addWidget(self._value)

	def set_text(self, text: str):
		self._value.setText(text)

	def set_enabled(self, enabled: bool):
		self._value.setEnabled(enabled)

	@property
	def value_label(self):
		"""Direct access to value QLabel for setText/setEnabled if needed."""
		return self._value
