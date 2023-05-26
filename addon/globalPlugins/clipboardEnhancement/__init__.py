import api
import globalPluginHandler
import scriptHandler
import ui
import gui
import globalVars
import textInfos
import speech
from logHandler import log
from core import callLater
from keyboardHandler import KeyboardInputGesture
from . import calendar
from . import utility 
from . import constants
from . import cues
from .clipEditor import MyFrame
from . import NAVScreenshot
import os
import json
import review
from .clipboardReview import ClipboardObject
from versionInfo import version_year
speechModule = speech.speech if version_year >= 2021 else speech


raw_setReviewPosition = None
def proxy_setReviewPosition(reviewPosition, clearNavigatorObject=False, isCaret=False, isMouse=False):
	global raw_setReviewPosition
	clearNavigatorObject = True
	print(f"reviewPosition={reviewPosition}")
	return raw_setReviewPosition(reviewPosition, clearNavigatorObject, isCaret, isMouse)


# 剪贴板记录数据文件
CLIPBOARD_HISTORY_FILENAME = \
	os.path.abspath(
		os.path.join(os.path.dirname(__file__), "../../../../", "cphistory.db"))


def disableInSecureMode(decoratedCls):
	if globalVars.appArgs.secure:
		return globalPluginHandler.GlobalPlugin
	return decoratedCls


@disableInSecureMode
class GlobalPlugin(globalPluginHandler.GlobalPlugin):
	scriptCategory = "剪贴板增强"
	pt = pti = {}

	def __init__(self):
		super().__init__()
		global raw_setReviewPosition
		raw_setReviewPosition = api.setReviewPosition
		api.setReviewPosition = proxy_setReviewPosition
		self.flg = 1
		self.spoken2 = self.spoken = ""
		self.spoken_word = self.spoken_char = -1
		self.oldSpeak = speechModule.speak
		speechModule.speak = self.newSpeak
		self.text = ""
		self.files = []
		self.info = ""
		self.lines = ["无数据"]
		self.line = self.char = self.word = -1
		self.monitor = None
		self.editor = None
		callLater(100, self.clipboard)
		self.Dict = None
		callLater(200, self.loadFiles)
		# 剪贴板记录池，用以存放剪贴板数据
		self.clipboardDataPool = list()
		# 夹在剪贴板记录数据文件
		try:
			self.clipboardDataPool = self._loadClipboardHistoryFromFile()
		except Exception as e:
			log.info(f"夹在剪贴板历史文件失败：{e}")
			self.clipboardDataPool = []
		# 剪贴板记录光标
		self.cursorClipboardHistory = 0
		# 剪贴板追加拷贝标志，剪贴板记录功能根据此标志来决定剪贴板数据应当拷贝还是追加
		self.flagAppendClipboard = False
		""" 首次剪贴板拷贝事件标记，指明是否为插件启动后的首次拷贝
		如果为首次拷贝，则对比夹在的历史记录中的第一条数据是否与当前数据相同，若相同则说明数据重复，需删除记录
		这是因为插件启动后，如果剪贴板中存在数据，插件会收到剪贴板拷贝事件，但剪贴板中的数据可能仍是上次插件退出时的数据"""
		self.firstClipboardEvent = True
		# 添加“剪贴板浏览模式”
		mode = ("clipboard", _("剪贴板浏览模式"), self._getClipboardPosition)
		review.modes.append(mode)

	# 返回剪贴板对象
	def _getClipboardPosition(self, obj):
		try:
			api.getClipData()
		except OSError:
			return None
		globalVars.cacheNavigatorObject = obj
		clipObj = ClipboardObject()
		return clipObj.makeTextInfo(textInfos.POSITION_FIRST), clipObj

	# 保存剪贴板记录数据到磁盘
	def _saveClipboardHistoryToFile(self):
		with open(CLIPBOARD_HISTORY_FILENAME, "w") as f:
			data = json.dumps(self.clipboardDataPool)
			f.write(data)

	# 从文件夹在剪贴板记录数据
	def _loadClipboardHistoryFromFile(self):
		data = None
		with open(CLIPBOARD_HISTORY_FILENAME, "r") as f:
			data = f.read()
			data = json.loads(data)
		return data

	def clipboard(self):
		self.editor = MyFrame(gui.mainFrame, title="剪贴板编辑器")
		self.monitor = utility.ClipboardMonitor(self.editor.GetHandle())
		self.monitor.customization = self.func
		callLater(100, self.monitor.get_clipboard_data)
		self.monitor.StartMonitor()
		self.editor.setClipboardPosition = self.setPosition

	def setPosition(self, char, line):
		self.char, self.line = char, line

	def loadFiles(self):
		self.Dict = utility.loadDict()

	def func(self):
		self.text = ""
		self.files = None
		self.info = "无数据"
		self.lines = ["无数据"]
		self.word = self.line = self.char = -1
		data = self.monitor.getData()
		# 添加数据到剪贴板记录池
		# 仅能添加文本类型的记录，如果不是文本记录则不添加
		if isinstance(data, str):
			self.clipboardDataPool.insert(0, data)
			# 判断是否为剪贴板追加拷贝，如果为追加拷贝则拷贝当前数据并删除索引=1的上一条数据
			if self.flagAppendClipboard is True:
				self.flagAppendClipboard = False
				if len(self.clipboardDataPool) >= 2:
					self.clipboardDataPool.pop(1)
			# 如果为首次剪贴板拷贝事件，则对比记录中的第一条与本次记录是否相同，若相同，仅保留一个
			if self.firstClipboardEvent is True:
				self.firstClipboardEvent = False
				if len(self.clipboardDataPool) >= 2 and data == self.clipboardDataPool[1]:
					self.clipboardDataPool.pop(0)
			# 控制剪贴板记录最多不能超过50条
			maxClipboardHistoryCount = 50
			if len(self.clipboardDataPool) == (maxClipboardHistoryCount+1):
				self.clipboardDataPool.pop()
			# 重置剪贴板记录光标，使其指向当前剪贴板记录
			self.cursorClipboardHistory = 0
			# 保存剪贴板历史数据到文件
			self._saveClipboardHistoryToFile()
		if isinstance(data, str):
			self.text = data
			self.lines = data.splitlines(True)
		elif isinstance(data, list):
			self.files = data
			self.lines = list(utility.fileLists(data))
		elif isinstance(data, bytes):
			self.lines = [f"图片： {utility.getBitmapInfo()}"]
			self.info = f"图片： {utility.getBitmapInfo()}"

	@scriptHandler.script(
		description=_("剪贴板综述"), 
		gestures=["kb(desktop):control+numpaddelete", "kb(laptop):NVDA+Alt+'"])
	def script_briefClip(self, gesture):
		if self.text:
			self.info = f'第{self.line+1}行， 共{len(self.lines)}行， {len("".join(self.lines))}个字'
		elif self.files is not None:
			self.info = self.monitor.calc(self.files)
		ui.message(self.info)

	@scriptHandler.script(
		description=_("剪贴板第一行"), 
		gestures=["kb(desktop):control+numpaddivide", "kb(laptop):NVDA+Alt+shift+UpArrow"])
	def script_firstLine(self, gesture):
		self.line = 0
		ui.message(self.lines[self.line])

	@scriptHandler.script(
		description=_("剪贴板最后一行"), 
		gestures=["kb(desktop):control+NumpadMultiply", "kb(laptop):NVDA+Alt+shift+DownArrow"])
	def script_lastLine(self, gesture):
		self.line = len(self.lines) - 1
		ui.message(self.lines[self.line])

	@scriptHandler.script(
		description=_("剪贴板上一行"), 
		gestures=["kb(desktop):control+numpad7", "kb(laptop):NVDA+Alt+UpArrow"])
	def script_previousLine(self, gesture):
		self.switchLine(-1)

	@scriptHandler.script(
		description=_("剪贴板下一行"), 
		gestures=["kb(desktop):control+numpad9", "kb(laptop):NVDA+Alt+DownArrow"])
	def script_nextLine(self, gesture):
		self.switchLine(1)

	@scriptHandler.script(
		description=_("剪贴板向上十行"), 
		gestures=["kb(desktop):control+NumpadMinus", "kb(laptop):NVDA+Shift+Alt+PageUp"])
	def script_previousLine10(self, gesture):
		self.switchLine(-10)

	@scriptHandler.script(
		description=_("剪贴板向下十行"), 
		gestures=["kb(desktop):control+NumpadPlus", "kb(laptop):NVDA+Shift+Alt+PageDown"])
	def script_nextLine10(self, gesture):
		self.switchLine(10)

	def switchLine(self, step):
		self.line += step
		if self.line < 0:
			self.line = 0
			cues.StartOrEnd()
		if self.line >= len(self.lines):
			self.line = len(self.lines) - 1
			cues.StartOrEnd()
		if self.files:
			cues.FileInClipboard()
		ui.message(self.lines[self.line])
		self.word = self.char = -1

	@scriptHandler.script(
		description=_("重复刚听到的内容"), 
		gestures=["kb(desktop):control+Windows+numpaddelete"])
	def script_repeatSpoken(self, gesture):
		ui.message(self.spoken)

	@scriptHandler.script(
		description=_("使用较慢的语速和重读单词重复刚听到的内容"),
	)
	def script_speakSlowly(self, gesture):
		sequence = []
		sequence.append(speech.commands.RateCommand(offset=-30))
		for text in self.spoken.split():
			sequence.append(text)
			sequence.append(speech.commands.EndUtteranceCommand())
		self.oldSpeak(sequence)

	def newSpeak(self, sequence, *args, **kwargs):
		data = ""
		if isinstance(sequence, str):
			data = sequence
		else:
			data = " ".join([i for i in sequence if isinstance(i, str)])
		if self.flg == 1:  # 捕获最后依次的朗读
			self.spoken = data
			self.spoken_word = self.spoken_char = -1
		elif self.flg == 2:  # 捕获缓冲区中的朗读
			self.spoken2 = data
			self.flg = 1
		else:  # 不补货
			self.flg = 1
		self.oldSpeak(sequence, *args, **kwargs)

	@scriptHandler.script(
		description=_("拷贝刚听到的内容"), 
		gesture=_("kb:NVDA+c"))
	def script_copySpoken(self, gesture):
		repeatCount = scriptHandler.getLastScriptRepeatCount()
		if repeatCount == 1:
			api.copyToClip(self.spoken2)
			self.flg = 0
			ui.message("拷贝")
		elif repeatCount == 0:
			api.copyToClip(self.spoken)
			self.flg = 0
			ui.message("拷贝")

	def _getClipText(self):
		text = ""
		try:
			text = api.getClipData()
		except Exception as e:
			log.error(e)
			return text
		if isinstance(text, str) and text:
			return text
		return ""

	@scriptHandler.script(
		description=_("追加刚听到的内容到剪贴板"), 
		gesture="kb:nvda+X")
	def script_append(self, gesture):
		# 设置追加剪贴板操作标志为True，剪贴板记录功能需要根据此标志决定剪贴板数据是新增还是合并
		self.flagAppendClipboard = True
		clip = ""
		count = scriptHandler.getLastScriptRepeatCount()
		if count == 1:
			end = "\n" if not self.text.endswith("\n") and self.text else ""
			clip = end.join((self.text, self.spoken2))
			api.copyToClip(clip)
			self.flg = 0
			ui.message("添加")
		elif count == 0:
			end = "\n" if not self.text.endswith("\n") and self.text else ""
			clip = end.join((self.text, self.spoken))
			api.copyToClip(clip)
			self.flg = 0
			ui.message("添加")

	@scriptHandler.script(
		description=_("打开剪贴板编辑器"), 
		gesture="kb:NVDA+E")
	def script_clipEditor(self, gesture):
		if self.editor is None:
			self.editor = MyFrame(gui.mainFrame, title="剪贴板编辑器")
		self.editor.edit.SetValue(self.text.replace('\r\n', '\n'))
		point = self.editor.edit.XYToPosition(self.char if self.char >= 0 else 0,
		self.line if self.line >= 0 else 0)
		self.editor.edit.SetInsertionPoint(point)
		self.editor.Show(True)
		self.editor.Maximize(True)
		self.editor.Raise()

	def switchSpokenWord(self, d=0):
		# 分词，用 [0] 得到分割后的单词列表
		words = utility.segmentWord(self.spoken)[0]
		if not words:
			return
		self.spoken_word += d
		Count = len(words)
		if self.spoken_word >= Count:
			self.spoken_word = Count - 1
			cues.LineBoundary()
		if self.spoken_word < 0:
			self.spoken_word = 0
			cues.LineBoundary()

		word = words[self.spoken_word].lower()
		self.flg = 2
		ui.message(word)

		# 解释当前单词
		if d == 0:
			word = utility.translateWord(self.Dict, word)
			if word:
				self.flg = 2
				ui.message(word)
		# 上/下一个单词
		else:
			p = utility.segmentWord(self.spoken)[1]
			self.spoken_char = p[self.spoken_word] - 1

	@scriptHandler.script(
		description=_("刚听到内容的下一个词句"), 
		gestures=["kb(desktop):Control+Windows+Numpad6", "kb(laptop):NVDA+shift+Windows+RightArrow"])
	def script_nextSpokenWord(self, gesture):
		self.switchSpokenWord(1)

	@scriptHandler.script(
		description=_("刚听到内容的当前词句（解释英文单词）"), 
		gestures=["kb(desktop):control+Windows+Numpad5", "kb(laptop):NVDA+shift+Windows+."])
	def script_currentSpokenWord(self, gesture):
		self.switchSpokenWord()

	@scriptHandler.script(
		description=_("刚听到内容的上一个词句"), 
		gestures=["kb(desktop):Control+Windows+Numpad4", "kb(laptop):NVDA+shift+Windows+LeftArrow"])
	def script_previousSpokenWord(self, gesture):
		self.switchSpokenWord(-1)

	@scriptHandler.script(
		description=_("刚听到内容的下一个字"), 
		gestures=["kb(desktop):Control+Windows+Numpad3", "kb(laptop):NVDA+Windows+RightArrow"])
	def script_nextSpokenChar(self, gesture):
		if not self.spoken:
			return
		p = utility.segmentWord(self.spoken)[1]
		self.spoken_char += 1
		self.spoken_word = utility.charPToWordP(p, self.spoken_char)
		count = len(self.spoken)
		if self.spoken_char >= count: 
			self.spoken_char = count - 1
			cues.LineBoundary()
		self.flg = 2
		speechModule.speakSpelling(self.spoken[self.spoken_char])

	@scriptHandler.script(
		description=_("刚听到内容的上一个字"), 
		gestures=["kb(desktop):Control+Windows+Numpad1", "kb(laptop):NVDA+Windows+LeftArrow"])
	def script_previousSpokenChar(self, gesture):
		if not self.spoken:
			return
		p = utility.segmentWord(self.spoken)[1]
		self.spoken_char -= 1
		self.spoken_word = utility.charPToWordP(p, self.spoken_char)
		if self.spoken_char < 0: 
			self.spoken_char = 0
			cues.LineBoundary()
		self.flg = 2
		speechModule.speakSpelling(self.spoken[self.spoken_char])

	@scriptHandler.script(
		description=_("刚听到内容的当前字（连按两次解释）"), 
		gestures=["kb(desktop):Control+Windows+numpad2", "kb(laptop):NVDA+windows+."])
	def script_currentSpokenChar(self, gesture):
		if not self.spoken:
			return
		if self.spoken_char < 0:
			self.spoken_char = 0
		self.flg = 2
		self._charExplanation(self.spoken[self.spoken_char])

	@scriptHandler.script(
		description=_("剪贴板当前字（连按两次解释）"), 
		gestures=["kb(desktop):Control+Numpad2", "kb(laptop):NVDA+Alt+."])
	def script_currentChar(self, gesture):
		if self.line < 0:
			self.line = 0
		text = self.lines[self.line]
		if not text:
			return ui.message("空白")
		if self.char < 0:
			self.char = 0
		self._charExplanation(text[self.char])

	def _charExplanation(self, c):
		n = scriptHandler.getLastScriptRepeatCount()
		if n == 1:
			speechModule.speakSpelling(c, useCharacterDescriptions=True)
		elif n == 0:
			speechModule.speakSpelling(c)

	@scriptHandler.script(
		description=_("剪贴板上一个字"), 
		gestures=["kb(desktop):Control+Numpad1", "kb(laptop):NVDA+Alt+LeftArrow"])
	def script_previousChar(self, gesture):
		self._switchChar(-1)

	@scriptHandler.script(
		description=_("剪贴板下一个字"), 
		gestures=["kb(desktop):Control+Numpad3", "kb(laptop):NVDA+Alt+RightArrow"])
	def script_nextChar(self, gesture):
		self._switchChar(1)

	def _switchChar(self, d):
		if self.line < 0:
			self.line = 0
		text = self.lines[self.line]
		self.char += d
		count = len(text)
		if self.char < 0:  # 如果到了行首
			if self.line > 0:  # 且当前不是第一行
				self.line -= 1  # 则切换到前一行
				text = self.lines[self.line]
				self.char = len(text) - 1  # 字符位置从这一行的行末开始
				words = utility.segmentWord(text)[0]
				self.word = len(words) - 1
			else:  # 如果移动到了第一行的行首
				self.char = 0
			cues.LineBoundary()
		elif self.char >= count:  # 如果到了行尾
			if self.line < len(self.lines) - 1:  # 且当前不是最后一行
				self.line += 1  # 则切换到后一行
				text = self.lines[self.line]
				self.char = 0  # 字符位置从这一行的行首开始
				self.word = 0
			else:  # 如果移动到了最后一行的行尾
				self.char = count - 1
			cues.LineBoundary()

		if text:
			p = utility.segmentWord(text)[1]
			self.word = utility.charPToWordP(p, self.char)
			speechModule.speakSpelling(text[self.char])
		else:
			ui.message("空白")

	def _switchWord(self, d=0):
		if self.line < 0:
			self.line = 0
		text = self.lines[self.line]
		words = utility.segmentWord(text)[0]
		count = len(words)
		self.word += d
		f = False

		if self.word >= count:  # 如果是本行内最后一个单词
			if self.line < len(self.lines) - 1:  # 且不是最后一行
				self.line += 1  # 则切换到下一行
				text = self.lines[self.line]
				words = utility.segmentWord(text)[0]
				self.word = 0
				f = True
			else:  # 如果是最后一行，定位到最后一个单词
				self.word = count - 1
			cues.StartOrEnd()
		elif self.word < 0 and d != 0:  # 如果是本行内第一个单词
			if self.line > 0:  # 且不是第一行
				self.line -= 1  # 则切换到前一行
				text = self.lines[self.line]
				words = utility.segmentWord(text)[0]
				self.word = len(words) - 1
				f = True
# 如果是第一行，定位到第一个单词
			else:
				self.word = 0
			cues.StartOrEnd()

		if not d == 0:
			p = utility.segmentWord(text)[1]
			self.char = p[self.word] - 1

		word = words[self.word]
		ui.message(word)

		word = word.lower()

		if d == 0:
			word = utility.translateWord(self.Dict, word)
			if word:
				ui.message(word)
		if f:
			return

	@scriptHandler.script(
		description=_("剪贴板上一个词句"), 
		gestures=["kb(desktop):Control+Numpad4", "kb(laptop):NVDA+Shift+Alt+LeftArrow"])
	def script_previousWord(self, gesture):
		self._switchWord(-1)

	@scriptHandler.script(
		description=_("剪贴板下一个词句"), 
		gestures=["kb(desktop):Control+Numpad6", "kb(laptop):NVDA+Shift+Alt+RightArrow"])
	def script_nextWord(self, gesture):
		self._switchWord(1)

	@scriptHandler.script(
		description=_("剪贴板当前词句（解释英文单词）"), 
		gestures=["kb(desktop):Control+Numpad5", "kb(laptop):NVDA+Shift+Alt+."])
	def script_currentWord(self, gesture):
		self._switchWord(0)

	@scriptHandler.script(
		description=_("从剪贴板当前行向下朗读"), 
		gestures=["kb(desktop):Control+Numpad8", "kb(laptop):NVDA+Alt+l"])
	def script_fromCurrentLine(self, gesture):
		if self.line < 0:
			self.line = 0
		text = self.lines[self.line:]
		speechModule.speak(text)

	@scriptHandler.script(
		description=_("打开剪贴板内（或刚听到的）网址"), 
		gestures=["kb(desktop):control+numpadEnter", "kb(laptop):NVDA+Alt+Enter"])
	def script_openURL(self, gesture):
		try:
			if not (utility.tryOpenURL(self.spoken) or utility.tryOpenURL(self.text)):
				ui.message("未找到可供打开的 URL或文件路径")
		except FileNotFoundError as e:
			ui.message(str(e))

	@scriptHandler.script(
		description=_("读出时间（连按两次读出日期）"),
		gesture="kb:NVDA+f12")
	def script_speakDateTime(self, gesture):
		if scriptHandler.getLastScriptRepeatCount() > 0:
			ui.message(calendar.getDate() + '。\n' + calendar.get_constellation())
		else:
			ui.message(calendar.getTime())

	@scriptHandler.script(
		description=_("读出农历日期（连按两次读出本月节气）"), 
		gesture="kb:NVDA+f11")
	def script_speakLunarDate(self, gesture):
		if scriptHandler.getLastScriptRepeatCount() > 0:
			ui.message(calendar.getJieQi())
		else:
			ui.message(calendar.getLunarDate())

	@scriptHandler.script(
		description=_("编辑文档的字数统计"), 
		gestures=["kb(desktop):windows+numpaddelete", "kb(laptop):NVDA+alt+="])
	def script_editInfo(self, gesture):
		if not utility.isSupport():
			ui.message("此功能不可用，请使用朗读状态栏功能获取相关信息")
			return
		pos = api.getReviewPosition().copy()
		if not ('_startOffset' in dir(pos) or '_rangeObj' in dir(pos)):
			ui.message("未获取到相关信息")
			return
		if '_startOffset' in dir(pos):
			pos._endOffset = 387419741
			pos._startOffset = pos._endOffset - 1
		else:
			pos._rangeObj.End = 387419741
			pos._rangeObj.Start = pos._rangeObj.End - 1
		formatField = textInfos.FormatField()
		for field in pos.getTextWithFields(constants.formatConfig):
			if isinstance(field, textInfos.FieldCommand) and isinstance(field.field, textInfos.FormatField):
				formatField.update(field.field)
		repeats = scriptHandler.getLastScriptRepeatCount()
		if repeats == 0:
			text = speechModule.getFormatFieldSpeech(formatField, formatConfig=constants.formatConfig) if formatField else None
			if text:
				text = "".join(text)
				if text.find(u"页") >= 0:
					text = text[1:text.find(u"页") + 1]
				else:
					text = text.replace(u"行", u"") + u"航"
				if '_startOffset' in dir(pos):
					pos._startOffset = 0
				else:
					pos._rangeObj.Start = 0
				i = len(pos.clipboardText.replace("\r", "").replace("\n", ""))
				ui.message(u"共" + text + str(i) + u"字")
			else:
				ui.message("此处不支持")

	@scriptHandler.script(
		description=_("编辑文档的当前光标位置"), 
		gestures=["kb(desktop):windows+NumPad5", "kb(laptop):NVDA+alt+\\"])
	def script_editCurrent(self, gesture):
		if not utility.isSupport():
			ui.message("此功能不可用")
			return
		pos = api.getReviewPosition().copy()
		if not '_startOffset' in dir(pos) and not '_rangeObj' in dir(pos):
			ui.message(u"无法获取位置")
		pos2 = api.getReviewPosition().copy()
		pos.expand(textInfos.UNIT_LINE)
		pos.setEndPoint(pos2, "endToEnd")
		column = len(pos.clipboardText)
		pos.expand(textInfos.UNIT_LINE)
		formatField = textInfos.FormatField()
		for field in pos.getTextWithFields(constants.formatConfig):
			if isinstance(field, textInfos.FieldCommand) and isinstance(field.field, textInfos.FormatField):
				formatField.update(field.field)
		repeats = scriptHandler.getLastScriptRepeatCount()
		if repeats == 0:
			text = speechModule.getFormatFieldSpeech(formatField, formatConfig=constants.formatConfig) if formatField else None
			if text:
				text = "， ".join(text)
				ui.message("{}，{}列".format(text, column))
			else:
				ui.message("此处不支持")

	@scriptHandler.script(
		description=_("编辑文档标记开始点"), 
		gestures=["kb(desktop):windows+Numpad4", "kb(laptop):NVDA+alt+["])
	def script_markStart(self, gesture):
		self.pt[api.getFocusObject().windowThreadID] = api.getReviewPosition().copy()  # i2=obj.windowHandle
		ui.message("选择开始点")

	@scriptHandler.script(
		description=_("编辑文档标记结束点"), 
		gestures=["kb(desktop):windows+NumPad6", "kb(laptop):NVDA+alt+]"])
	def script_markEnd(self, gesture):
		id = api.getFocusObject().windowThreadID
		pos = api.getReviewPosition().copy()
		try:
			if not id in self.pt.keys():
				pos.move(textInfos.UNIT_CHARACTER, -381419741, endPoint="start")
			else:
				ptp = self.pt[id]
				if pos.compareEndPoints(ptp, "endToEnd") == 0:
					ui.message("不支持选择")
					return
				if pos.compareEndPoints(ptp, "endToEnd") > 0:
					pos.setEndPoint(ptp, "startToStart")
				else:
					pos.setEndPoint(ptp, "endToEnd")
			api.getReviewPosition().obj._selectThenCopyRange = pos
			pos.updateSelection()
			ui.message("选择结束点")
		except:
			pass

	@scriptHandler.script(
		description=_("查询选中单词或词组"), 
		gestures=[])
	def script_QueryDictionaryWithSelected(self, gesture):
		selectedText=self.getSelectionText()
		if not selectedText:
			ui.message("请选中要查询的单词或词组")
			return
		result = utility.translateWord(self.Dict, selectedText.strip().lower())
		ui.message(result)

	@scriptHandler.script(
		description=_("截图当前浏览对象到剪贴板"), 
		gestures=["kb:NVDA+printScreen"])
	def script_NAVScreenshotToClipboard(self, gesture):
	# 如果开启了黑屏则给出提示，但仍然会执行截图
		if NAVScreenshot.isScreenCurtainRunning():
			ui.message("当前处于黑屏状态")
		else:
			NAVScreenshot.navigatorObjectScreenshot()

	@scriptHandler.script(
		description=_("追加已选文字到剪贴板"), 
		gestures=["kb:NVDA+alt+A"])
	def script_AppendTextToClipboard(self, gesture):
		self.AppendTextToClipboard()


	def AppendTextToClipboard(self):
		# 过滤连续手势
		repeatCount =scriptHandler.getLastScriptRepeatCount()
		if repeatCount:
			return
		ClipboardText = ""
		ResultText = ""
		selectedText=self.getSelectionText()
		if not selectedText:
			ui.message("未选择文本")
			return

		# 获取剪贴板文本
		try:
			ClipboardText = api.getClipData()
		except:
			api.copyToClip(selectedText)
			ui.message("拷贝")
			return

		# 拼接要复制的文本
		ResultText = ClipboardText +"\n" +selectedText
		try:
			api.copyToClip(ResultText)
			ui.message("已追加")
		except:
			ui.message("追加失败")


	def getSelectionText(self):
		info = ""
		obj=api.getFocusObject()
		treeInterceptor=obj.treeInterceptor
		if hasattr(treeInterceptor,'TextInfo') and not treeInterceptor.passThrough:
			obj=treeInterceptor
		try:
			info=obj.makeTextInfo(textInfos.POSITION_SELECTION)
		except (RuntimeError, NotImplementedError):
			info=None
		if not info or info.isCollapsed:
			return None
		else:
			return info.text


	def terminate(self):
		self.monitor.Stop()
		self.monitor = None
		speechModule.speak = self.oldSpeak
		self.oldSpeak = None
		if self.editor:
			self.editor.isExit = True
			self.editor.Destroy()
		self.editor = None
		# 卸载api.setReviewPosition挂钩
		global raw_setReviewPosition
		api.setReviewPosition = raw_setReviewPosition
		super().terminate()

	@scriptHandler.script(
		description=_("粘贴刚听到的内容"),
		gestures=["kb:NVDA+`"])
	def script_pasteLastSpoken(self, gesture):
		self.monitor.work = False
		api.copyToClip(self.spoken.rstrip("\r\n"))
		KeyboardInputGesture.fromName("control+v").send()
		utility.Thread(target = utility.paste, args=(self,)).start()

	def _changeClipboardHistory(self, step):
		# 参数检查，步长值只能=1货=-1
		if step != 1 and step != -1:
			return
		countHistory = len(self.clipboardDataPool)
		# 没有剪贴板记录则什么也不做，直接返回
		if countHistory == 0:
			return
		# 计算剪贴板记录光标
		self.cursorClipboardHistory += step
		if self.cursorClipboardHistory >= countHistory:
			self.cursorClipboardHistory = countHistory - 1
		elif self.cursorClipboardHistory < 0:
			self.cursorClipboardHistory = 0
		data = self.clipboardDataPool[self.cursorClipboardHistory]
		lines = []
		if isinstance(data, str):
			lines = data.splitlines(True)
		elif isinstance(data, list):
			lines = list(utility.fileLists(data))
		elif isinstance(data, bytes):
			lines = [f"图片： {utility.getBitmapInfo()}"]
		return "".join(lines)

	@scriptHandler.script(
		description=_("下一条剪贴板记录"),
		gestures=["kb(desktop):CONTROL+WINDOWS+NUMPADPLUS", "kb(laptop):CONTROL+WINDOWS+]"])
	def script_nextClipboardHistory(self, gesture):
		# 如果剪贴板记录为空，提示并退出
		if len(self.clipboardDataPool) == 0:
			ui.message("无剪贴板记录")
			cues.StartOrEnd()
			return
		# 如果到达上线索引，给出提示音
		if self.cursorClipboardHistory == (len(self.clipboardDataPool) - 1):
			cues.StartOrEnd()
		data = self._changeClipboardHistory(1)
		# 仅朗读记录文本的前1000个字符，避免大文本导致NVDA假死
		ui.message(f"{self.cursorClipboardHistory+1}. {data[:1000]}")

	@scriptHandler.script(
		description=_("上一条剪贴板记录"),
		gestures=["kb(desktop):CONTROL+WINDOWS+NUMPADMINUS", "kb(laptop):CONTROL+WINDOWS+["])
	def script_prevClipboardHistory(self, gesture):
		# 如果剪贴板记录为空，提示并退出
		if len(self.clipboardDataPool) == 0:
			ui.message("无剪贴板记录")
			cues.StartOrEnd()
			return
		# 如果到达下线索引，给出提示音
		if self.cursorClipboardHistory == 0:
			cues.StartOrEnd()
		data = self._changeClipboardHistory(-1)
		# 仅朗读记录文本的前1000个字符，避免大文本导致NVDA假死
		ui.message(f"{self.cursorClipboardHistory+1}. {data[:1000]}")

	@scriptHandler.script(
		description=_("拷贝剪贴板记录到系统剪贴板"),
		gestures=["kb(desktop):CONTROL+WINDOWS+NUMPADMULTIPLY", "kb(laptop):CONTROL+WINDOWS+\\"])
	def script_addClipboardHistoryToClipboard(self, gesture):
		countHistory = len(self.clipboardDataPool)
		# 没有剪贴板记录则什么也不做，直接返回
		if countHistory == 0:
			ui.message("无剪贴板记录")
			return
		data = self.clipboardDataPool[self.cursorClipboardHistory]
		# 从剪贴板记录中删除需要添加的记录，因为拷贝剪贴板记录到系统剪贴板后，会新增一条相同的剪贴板记录
		self.clipboardDataPool.pop(self.cursorClipboardHistory)
		api.copyToClip(data)

	@scriptHandler.script(
		description=_("清空所有剪贴板记录"),
		gestures=["kb(desktop):CONTROL+WINDOWS+DELETE", "kb(laptop):CONTROL+WINDOWS+DELETE"])
	def script_emptyClipboardHistory(self, gesture):
		countRepeat = scriptHandler.getLastScriptRepeatCount()
		# 如果不是三击手势则退出
		if countRepeat != 2:
			return
		# 如果没有剪贴板记录则提示并返回
		countClipboardHistory = len(self.clipboardDataPool)
		if countClipboardHistory == 0:
			ui.message("无剪贴板记录")
			return
		# 清空剪贴板所有记录
		self.clipboardDataPool = []
		# 设置剪贴板记录光标指向列表开头
		self.cursorClipboardHistory = 0
		ui.message("已成功的清空了所有剪贴板记录")
		# 保存剪贴板记录数据到磁盘
		self._saveClipboardHistoryToFile()
