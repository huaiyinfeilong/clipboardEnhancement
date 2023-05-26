import api
import textInfos
import documentBase
import globalVars


# 剪贴板文本信息类
class ClipboardTextInfo(textInfos.offsets.OffsetsTextInfo):
	def __init__(self, obj, position, navigatorObject=None):
		super(ClipboardTextInfo, self).__init__(obj, position)

	def _getStoryLength(self):
		return len(self._getStoryText())

	def _getStoryText(self):
		try:
			text = api.getClipData()
		except OSError:
			text = ""
		return text

	def _getNVDAObjectFromOffset(self, offset):
		return globalVars.cacheNavigatorObject


# 剪贴板对象类
class ClipboardObject(documentBase.TextContainerObject):
	def _get_TextInfo(self):
		return ClipboardTextInfo
