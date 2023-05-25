import api
import textInfos
from logHandler import log
import textUtils

data = ""


class ClipboardTextInfo(textInfos.offsets.OffsetsTextInfo):
	def __init__(self, lines):
		obj = api.getFocusObject()
		position = textInfos.POSITION_FIRST
		super().__init__(obj, position)
		self.lines = lines

	def _getStoryLength(self):
		return len(self._getStoryText())

	def _getStoryText(self):
		return "\r\n".join(self.lines)
