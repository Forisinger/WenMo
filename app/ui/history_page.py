"""文墨 - 历史记录页：全局搜索消息内容，双击跳转定位到会话。"""
import time

from PySide6.QtCore import Signal, Qt
from PySide6.QtWidgets import (
    QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem,
    QPushButton, QVBoxLayout, QWidget,
)

from core import db


def _fmt(ts: float) -> str:
    return time.strftime("%m-%d %H:%M", time.localtime(ts))


class HistoryPage(QWidget):
    open_message = Signal(str, str)   # (session_id, message_id)

    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 20, 24, 20)
        lay.setSpacing(12)

        title = QLabel("历史记录")
        title.setObjectName("ChatHeader")
        lay.addWidget(title)

        row = QHBoxLayout()
        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText("搜索全部对话内容，回车执行…")
        self.search_box.returnPressed.connect(self.do_search)
        self.search_btn = QPushButton("搜索")
        self.search_btn.clicked.connect(self.do_search)
        row.addWidget(self.search_box, 1)
        row.addWidget(self.search_btn)
        lay.addLayout(row)

        self.hint = QLabel("输入关键词搜索历史消息，双击结果跳转到对应会话。")
        self.hint.setObjectName("ChatHint")
        lay.addWidget(self.hint)

        self.result_list = QListWidget()
        self.result_list.itemDoubleClicked.connect(self._on_open)
        lay.addWidget(self.result_list, 1)

    def do_search(self) -> None:
        q = self.search_box.text().strip()
        self.result_list.clear()
        if not q:
            self.hint.setText("请输入搜索关键词。")
            return
        rows = db.search_messages(q)
        if not rows:
            self.hint.setText(f"没有找到包含「{q}」的消息。")
            return
        self.hint.setText(f"找到 {len(rows)} 条包含「{q}」的消息：")
        for r in rows:
            snippet = r["content"].replace("\n", " ")
            idx = snippet.find(q)
            start = max(0, idx - 20)
            snippet = ("…" if start > 0 else "") + snippet[start:start + 80] + "…"
            who = "我" if r["role"] == "user" else "文墨"
            item = QListWidgetItem(f"[{r['session_title']}] {who} · {_fmt(r['created_at'])}\n  {snippet}")
            item.setData(Qt.UserRole, (r["session_id"], r["message_id"]))
            self.result_list.addItem(item)

    def _on_open(self, item: QListWidgetItem) -> None:
        data = item.data(Qt.UserRole)
        if data:
            self.open_message.emit(data[0], data[1])
