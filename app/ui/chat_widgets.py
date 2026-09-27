"""文墨 - 消息组件（DeepSeek 风格 + 四阶段流水线渲染）。

形态：
  用户消息   = 右对齐圆角气泡 + 右侧头像（纯文本，QLabel 收缩自适应）
  助手消息   = 左侧头像 + 无底色通栏正文（Markdown），
               正文上方一组可折叠块：
                 - 普通思维链 → 单个「已深度思考」
                 - 流水线产物 → 「阶段1·规划大纲」「阶段2·补充设定」「阶段3·细化大纲」各一块
               正文下方复制/重新生成/删除操作栏。

流式期间助手正文用纯文本增量渲染（快），结束后切换为 Markdown。
右键菜单保留：复制 / 删除 / 重新生成（仅助手）。
"""
import re

import markdown as _md

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QAbstractScrollArea, QApplication, QHBoxLayout, QLabel, QMenu,
    QSizePolicy, QTextBrowser, QToolButton, QVBoxLayout, QWidget,
)

_COLUMN_MAX_W = 820   # 对话列最大宽（与主窗口 ChatColumn 保持一致）
_USER_MAX_W = 560     # 用户气泡最大宽

_STAGE_RE = re.compile(r"【阶段(\d+)·([^】]+)】\s*\n?")


def _md_to_html(text: str) -> str:
    return _md.markdown(text, extensions=["fenced_code", "tables", "nl2br"])


def _split_stages(reasoning: str) -> list[tuple[str, str]] | None:
    """解析落库的阶段标记文本 → [(标题, 内容)]；无标记返回 None。"""
    if "【阶段" not in reasoning:
        return None
    matches = list(_STAGE_RE.finditer(reasoning))
    if not matches:
        return None
    sections = []
    for i, m in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(reasoning)
        body = reasoning[m.end():end].strip()
        sections.append((f"阶段{m.group(1)}·{m.group(2)}", body))
    return sections


def _make_avatar(role: str) -> QLabel:
    av = QLabel("文" if role == "assistant" else "我")
    av.setObjectName("AvatarAssistant" if role == "assistant" else "AvatarUser")
    av.setFixedSize(34, 34)
    av.setAlignment(Qt.AlignCenter)
    return av


class MessageBubble(QWidget):
    delete_requested = Signal(str)        # 消息 id
    regenerate_requested = Signal(str)    # 消息 id（仅助手）

    def __init__(self, role: str, message_id: str = "",
                 parent: QWidget | None = None):
        super().__init__(parent)
        self.role = role
        self.message_id = message_id
        self._content = ""
        self._reasoning = ""
        self._streaming = False
        self._stage_sections: dict[int, tuple[QToolButton, QTextBrowser]] = {}
        # 横向撑满对话列（QTextBrowser 默认 sizeHint 只有 256px，会被挤窄）
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)

        root = QHBoxLayout(self)
        root.setContentsMargins(0, 2, 0, 2)
        root.setSpacing(10)

        avatar = _make_avatar(role)
        self.content_col = QVBoxLayout()
        self.content_col.setSpacing(4)

        # ---- 正文（先创建：折叠块要插在它前面）----
        if role == "user":
            self.body = QLabel()
            self.body.setObjectName("BubbleUser")
            self.body.setWordWrap(True)
            self.body.setTextInteractionFlags(Qt.TextSelectableByMouse)
            self.body.setMaximumWidth(_USER_MAX_W)
        else:
            self.body = QTextBrowser()
            self.body.setObjectName("BubbleBody")
            self.body.setOpenExternalLinks(True)
        self.content_col.addWidget(self.body)

        # ---- 普通思维链块（仅助手；流水线阶段块按需动态插入）----
        self.reasoning_toggle: QToolButton | None = None
        self.reasoning_box: QTextBrowser | None = None
        if role == "assistant":
            self.reasoning_toggle, self.reasoning_box = self._make_section("已深度思考")

        # ---- 操作栏（仅助手，完成后显示）----
        self.action_bar: QWidget | None = None
        if role == "assistant":
            self.action_bar = QWidget()
            bar_lay = QHBoxLayout(self.action_bar)
            bar_lay.setContentsMargins(0, 0, 0, 0)
            bar_lay.setSpacing(2)
            for label, cb in (
                ("复制", self._copy_content),
                ("重新生成", lambda: self.regenerate_requested.emit(self.message_id)),
                ("删除", lambda: self.delete_requested.emit(self.message_id)),
            ):
                btn = QToolButton()
                btn.setObjectName("ActionBtn")
                btn.setText(label)
                btn.setCursor(Qt.PointingHandCursor)
                btn.clicked.connect(cb)
                bar_lay.addWidget(btn)
            bar_lay.addStretch(1)  # 按钮靠左紧凑排列
            self.action_bar.setVisible(False)
            self.content_col.addWidget(self.action_bar)

        # ---- 组装：助手=头像在左；用户=内容在右、头像在右 ----
        if role == "assistant":
            self.content_col.addStretch(1)
            root.addWidget(avatar, 0, Qt.AlignTop)
            root.addLayout(self.content_col, 1)
        else:
            root.addStretch(1)
            root.addLayout(self.content_col, 0)
            root.addWidget(avatar, 0, Qt.AlignBottom)
        self.setMaximumWidth(_COLUMN_MAX_W)

    # ---- 可折叠块（思维链 / 流水线阶段共用）----
    def _make_section(self, title: str) -> tuple[QToolButton, QTextBrowser]:
        toggle = QToolButton()
        toggle.setObjectName("ReasoningToggle")
        toggle.setText("▸ " + title)
        toggle.setCheckable(True)
        toggle.setCursor(Qt.PointingHandCursor)
        toggle.setVisible(False)
        box = QTextBrowser()
        box.setObjectName("ReasoningBox")
        box.setVisible(False)
        box.setOpenExternalLinks(False)
        box.setMaximumHeight(180)
        box.setContextMenuPolicy(Qt.NoContextMenu)
        # 插到正文之前（操作栏之前）
        at = self.content_col.indexOf(self.body)
        self.content_col.insertWidget(at, toggle)
        self.content_col.insertWidget(at + 1, box)
        toggle.toggled.connect(lambda checked, t=toggle, b=box: self._on_section_toggle(t, b, checked))
        return toggle, box

    @staticmethod
    def _on_section_toggle(toggle: QToolButton, box: QTextBrowser, checked: bool) -> None:
        title = toggle.text()[2:]  # 去掉前缀箭头
        toggle.setText(("▾ " if checked else "▸ ") + title)
        box.setVisible(checked)

    # ---- 流水线阶段（流式中）----
    def begin_stage(self, idx: int, title: str) -> None:
        if idx in self._stage_sections:
            return
        toggle, box = self._make_section(f"阶段{idx}·{title}")
        self._stage_sections[idx] = (toggle, box)
        toggle.setVisible(True)
        toggle.setChecked(True)  # 流式中自动展开

    def append_stage(self, idx: int, piece: str) -> None:
        sec = self._stage_sections.get(idx)
        if not sec or not piece:
            return
        toggle, box = sec
        box.setPlainText(box.toPlainText() + piece)
        sb = box.verticalScrollBar()
        sb.setValue(sb.maximum())

    def end_stage(self, idx: int) -> None:
        sec = self._stage_sections.get(idx)
        if sec:
            sec[0].setChecked(False)  # 该阶段完成即收起

    # ---- 普通思维链（流式中，单次生成路径）----
    def set_stream_reasoning(self, reasoning: str) -> None:
        if not reasoning or self.reasoning_toggle is None:
            return
        self.reasoning_toggle.setVisible(True)
        if not self.reasoning_toggle.isChecked():
            self.reasoning_toggle.setChecked(True)
        self.reasoning_box.setPlainText(
            self.reasoning_box.toPlainText() + reasoning)
        sb = self.reasoning_box.verticalScrollBar()
        sb.setValue(sb.maximum())

    # ---- 正文 ----
    def set_stream_text(self, content: str) -> None:
        """流式：纯文本增量，快。"""
        self._streaming = True
        self._content = content
        self.body.setPlainText(content)
        self._autoscroll()

    def finalize(self, content: str, reasoning: str = "") -> None:
        """结束：正文定稿渲染 + 折叠块定稿 + 操作栏显示。"""
        self._streaming = False
        self._content = content
        self._reasoning = reasoning

        if self.role == "user":
            self.body.setText(content)
        else:
            # 流水线阶段块：解析标记，静态重建（收起状态）
            if self._stage_sections or _split_stages(reasoning):
                for (toggle, box) in self._stage_sections.values():
                    toggle.deleteLater()
                    box.deleteLater()
                self._stage_sections.clear()
                sections = _split_stages(reasoning) or []
                for title, body in sections:
                    toggle, box = self._make_section(title)
                    box.setPlainText(body)
                    toggle.setVisible(True)
                    toggle.setChecked(False)
                # 阶段块重建后，清掉旧的普通思维链块占位（有阶段块时不需要它）
                if self.reasoning_toggle is not None and not reasoning.strip():
                    pass
            elif reasoning:
                self.reasoning_toggle.setVisible(True)
                self.reasoning_box.setPlainText(reasoning)
                self.reasoning_toggle.setChecked(False)

            self.body.setHtml(_md_to_html(content) if content.strip() else "<i>（无内容）</i>")
            if self.message_id and self.action_bar is not None:
                self.action_bar.setVisible(True)
        self._autoscroll()

    def _autoscroll(self) -> None:
        if isinstance(self.body, QAbstractScrollArea):
            sb = self.body.verticalScrollBar()
            sb.setValue(sb.maximum())

    # ---- 操作 ----
    def _copy_content(self) -> None:
        QApplication.clipboard().setText(self._content)

    def contextMenuEvent(self, event) -> None:
        menu = QMenu(self)
        act_copy = QAction("复制内容", menu)
        act_copy.triggered.connect(self._copy_content)
        menu.addAction(act_copy)
        if self.message_id:
            if self.role == "assistant":
                act_regen = QAction("重新生成", menu)
                act_regen.triggered.connect(
                    lambda: self.regenerate_requested.emit(self.message_id))
                menu.addAction(act_regen)
            act_del = QAction("删除此消息", menu)
            act_del.triggered.connect(lambda: self.delete_requested.emit(self.message_id))
            menu.addAction(act_del)
        menu.exec(event.globalPos())


class TypingBubble(MessageBubble):
    """占位气泡：尚未收到任何 token 时的「正在思考」提示。"""

    def __init__(self, parent=None):
        super().__init__("assistant", "", parent)
        self.body.setPlainText("正在思考…")
