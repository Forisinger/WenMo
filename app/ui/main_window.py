"""文墨 - 主窗口：侧栏会话列表 + 对话区 + 历史记录页。

生成流程：send() 建用户消息并落库 → LLMWorker 后台流式 → 信号推气泡 →
结束（done/stopped/error）时助手消息一次性落库。
"""
import os

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QApplication, QComboBox, QDialog, QDialogButtonBox, QFileDialog,
    QFrame, QHBoxLayout, QInputDialog, QLabel, QLineEdit, QListWidget,
    QListWidgetItem, QMainWindow, QMessageBox, QPlainTextEdit, QPushButton,
    QScrollArea, QStackedWidget, QToolButton, QVBoxLayout, QWidget,
)

from core import db, exporter, prompts_store, settings_store
from core.config import APP_NAME, exports_dir
from core.llm import LLMWorker
from core.pipeline import PipelineWorker
from ui.chat_widgets import MessageBubble, TypingBubble
from ui.history_page import HistoryPage
from ui.settings_dialog import SettingsDialog


class InputEdit(QPlainTextEdit):
    """回车发送，Shift+回车换行。"""

    def __init__(self, send_cb, parent=None):
        super().__init__(parent)
        self._send_cb = send_cb
        self.setPlaceholderText("写下你的想法…（Enter 发送，Shift+Enter 换行）")

    def keyPressEvent(self, e):
        if e.key() in (Qt.Key_Return, Qt.Key_Enter) and not (e.modifiers() & Qt.ShiftModifier):
            self._send_cb()
            return
        super().keyPressEvent(e)


class NewSessionDialog(QDialog):
    def __init__(self, templates: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle("新建会话 — 文墨")
        self.setMinimumWidth(380)
        lay = QVBoxLayout(self)
        self.name_edit = QLineEdit("新的会话")
        lay.addWidget(QLabel("会话名称"))
        lay.addWidget(self.name_edit)
        lay.addWidget(QLabel("写作模板"))
        self.tpl_combo = QComboBox()
        for tpl in templates.values():
            self.tpl_combo.addItem(tpl["name"], tpl["id"])
        lay.addWidget(self.tpl_combo)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        lay.addWidget(buttons)

    def result_tuple(self):
        return self.name_edit.text().strip() or "新的会话", self.tpl_combo.currentData()


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"{APP_NAME} — AI 写作助手")
        self.resize(1180, 760)
        self.setMinimumSize(860, 560)

        self.templates = prompts_store.load_templates()
        self.current_session_id: str | None = None
        self._worker: LLMWorker | None = None
        self._placeholder: TypingBubble | None = None
        self._assistant_bubble: MessageBubble | None = None
        self._bubbles: list[MessageBubble] = []

        self._build_ui()
        self._reload_sessions()
        self._open_initial()

    def _open_initial(self) -> None:
        """启动时：优先打开最近会话；没有任何会话则显示欢迎语。"""
        sessions = db.list_sessions()
        if sessions:
            self.current_session_id = sessions[0]["id"]
            self._reload_sessions()
            self.open_session(sessions[0]["id"])
        else:
            self.chat_title.setText("文墨")
            self._show_welcome()

    # ================= UI 构建 =================
    def _build_ui(self) -> None:
        central = QWidget()
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ---- 侧栏 ----
        sidebar = QWidget()
        sidebar.setObjectName("Sidebar")
        sidebar.setFixedWidth(252)
        sl = QVBoxLayout(sidebar)
        sl.setContentsMargins(14, 16, 14, 14)
        sl.setSpacing(8)

        title = QLabel(APP_NAME)
        title.setObjectName("AppTitle")
        sub = QLabel("AI 写作助手 · 写文 Agent")
        sub.setObjectName("AppSub")
        sl.addWidget(title)
        sl.addWidget(sub)

        self.btn_new = QPushButton("＋ 新建会话")
        self.btn_new.clicked.connect(self.new_session)
        sl.addWidget(self.btn_new)

        self.session_list = QListWidget()
        self.session_list.itemClicked.connect(self._on_session_clicked)
        self.session_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.session_list.customContextMenuRequested.connect(self._session_menu)
        sl.addWidget(self.session_list, 1)

        self.btn_chat = QPushButton("对话")
        self.btn_chat.clicked.connect(lambda: self.stack.setCurrentIndex(0))
        self.btn_history = QPushButton("历史记录")
        self.btn_history.clicked.connect(lambda: self.stack.setCurrentIndex(1))
        self.btn_settings = QPushButton("设置")
        self.btn_settings.clicked.connect(self.open_settings)
        sl.addWidget(self.btn_chat)
        sl.addWidget(self.btn_history)
        sl.addWidget(self.btn_settings)

        root.addWidget(sidebar)

        # ---- 右侧堆叠：对话 / 历史 ----
        self.stack = QStackedWidget()
        self.stack.addWidget(self._build_chat_page())
        self.history_page = HistoryPage()
        self.history_page.open_message.connect(self._jump_to_message)
        self.stack.addWidget(self.history_page)
        root.addWidget(self.stack, 1)

        self.setCentralWidget(central)

    def _build_chat_page(self) -> QWidget:
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(20, 16, 20, 16)
        lay.setSpacing(10)

        # 顶部标题（居中，DeepSeek 式）
        head = QHBoxLayout()
        head_col = QVBoxLayout()
        head_col.setSpacing(2)
        self.chat_title = QLabel("文墨")
        self.chat_title.setObjectName("ChatHeader")
        self.chat_title.setAlignment(Qt.AlignHCenter)
        self.chat_tpl = QLabel("")
        self.chat_tpl.setObjectName("ChatTpl")
        self.chat_tpl.setAlignment(Qt.AlignHCenter)
        head_col.addWidget(self.chat_title)
        head_col.addWidget(self.chat_tpl)
        head.addStretch(1)
        head.addLayout(head_col)
        head.addStretch(1)
        lay.addLayout(head)

        # 对话区：内容收进居中窄列（≤820px），大屏两侧留白
        self.chat_scroll = QScrollArea()
        self.chat_scroll.setObjectName("ChatScroll")
        self.chat_scroll.setWidgetResizable(True)
        outer = QWidget()
        outer_lay = QHBoxLayout(outer)
        outer_lay.setContentsMargins(0, 0, 0, 0)
        outer_lay.setSpacing(0)
        self.chat_container = QWidget()
        self.chat_container.setObjectName("ChatColumn")
        self.chat_lay = QVBoxLayout(self.chat_container)
        self.chat_lay.setContentsMargins(8, 8, 8, 8)
        self.chat_lay.setSpacing(14)
        self.chat_lay.addStretch(1)
        outer_lay.addStretch(1)
        outer_lay.addWidget(self.chat_container, 0)
        outer_lay.addStretch(1)
        self.chat_scroll.setWidget(outer)
        lay.addWidget(self.chat_scroll, 1)
        # 视口宽度变化时，把对话列宽度定死为 min(820, 可用宽-28)
        self.chat_scroll.viewport().installEventFilter(self)

        # 输入面板：圆角大面板 + 右下角圆形两态按钮（DeepSeek 式）
        panel = QFrame()
        panel.setObjectName("InputPanel")
        panel_lay = QVBoxLayout(panel)
        panel_lay.setContentsMargins(4, 4, 8, 8)
        panel_lay.setSpacing(2)
        self.input = InputEdit(self.send)
        self.input.setFixedHeight(76)
        panel_lay.addWidget(self.input)
        bottom_row = QHBoxLayout()
        self.btn_pipeline = QToolButton()
        self.btn_pipeline.setObjectName("PipelineToggle")
        self.btn_pipeline.setText("✦ 创作流水线")
        self.btn_pipeline.setCheckable(True)
        self.btn_pipeline.setCursor(Qt.PointingHandCursor)
        self.btn_pipeline.setToolTip(
            "开启后按「规划大纲→补充设定→细化大纲→生成文本」四阶段生成（较慢但更完整）")
        self.btn_pipeline.setChecked(settings_store.get("pipeline") != "0")
        self.btn_pipeline.toggled.connect(self._on_pipeline_toggled)
        bottom_row.addWidget(self.btn_pipeline, 0, Qt.AlignLeft)
        hint = QLabel("Enter 发送 · Shift+Enter 换行 · 生成中点击按钮停止")
        hint.setObjectName("InputHint")
        bottom_row.addWidget(hint, 1)
        self.btn_action = QPushButton("↑")
        self.btn_action.setCursor(Qt.PointingHandCursor)
        self.btn_action.clicked.connect(self._on_action)
        self._set_action_state(sending=False)
        bottom_row.addWidget(self.btn_action, 0, Qt.AlignBottom)
        panel_lay.addLayout(bottom_row)
        lay.addWidget(panel)
        return page

    def _on_pipeline_toggled(self, checked: bool) -> None:
        settings_store.set("pipeline", "1" if checked else "0")

    # 发送/停止共用一个圆形按钮的两态切换
    def eventFilter(self, obj, event) -> bool:
        from PySide6.QtCore import QEvent
        if obj is self.chat_scroll.viewport() and event.type() == QEvent.Resize:
            w = obj.width() - 28
            self.chat_container.setFixedWidth(max(320, min(820, w)))
        return super().eventFilter(obj, event)

    def _set_action_state(self, sending: bool) -> None:
        btn = self.btn_action
        if sending:
            btn.setText("■")
            btn.setToolTip("停止生成")
            name = "BtnStop"
        else:
            btn.setText("↑")
            btn.setToolTip("发送")
            name = "BtnSend"
        btn.setObjectName(name)
        btn.style().unpolish(btn)
        btn.style().polish(btn)

    def _on_action(self) -> None:
        if self._worker and self._worker.isRunning():
            self.stop_generation()
        else:
            self.send()

    # ================= 会话列表 =================
    def _reload_sessions(self) -> None:
        self.session_list.clear()
        for s in db.list_sessions():
            item = QListWidgetItem(s["title"])
            item.setData(Qt.UserRole, s["id"])
            self.session_list.addItem(item)
            if s["id"] == self.current_session_id:
                self.session_list.setCurrentItem(item)

    def _on_session_clicked(self, item: QListWidgetItem) -> None:
        sid = item.data(Qt.UserRole)
        if sid and sid != self.current_session_id:
            self.open_session(sid)

    def _session_menu(self, pos) -> None:
        item = self.session_list.itemAt(pos)
        if not item:
            return
        from PySide6.QtWidgets import QMenu
        sid = item.data(Qt.UserRole)
        menu = QMenu(self)
        act_rename = menu.addAction("重命名")
        act_export_md = menu.addAction("导出 Markdown")
        act_export_txt = menu.addAction("导出纯文本")
        menu.addSeparator()
        act_del = menu.addAction("删除会话")
        act = menu.exec(self.session_list.viewport().mapToGlobal(pos))
        if act is None:
            return
        if act is act_rename:
            new_title, ok = QInputDialog.getText(self, "重命名", "新的会话名：",
                                                 text=item.text())
            if ok and new_title.strip():
                db.rename_session(sid, new_title.strip())
                self._reload_sessions()
                if sid == self.current_session_id:
                    self.chat_title.setText(new_title.strip())
        elif act is act_export_md:
            self._export(sid, "md")
        elif act is act_export_txt:
            self._export(sid, "txt")
        elif act is act_del:
            if QMessageBox.question(
                    self, "删除会话",
                    f"确定删除「{item.text()}」吗？\n该会话的全部消息将一并删除，且不可恢复。"
            ) == QMessageBox.Yes:
                db.delete_session(sid)
                if sid == self.current_session_id:
                    self.current_session_id = None
                    self._clear_chat()
                    self.chat_title.setText("文墨")
                    self.chat_tpl.setText("")
                    if not db.list_sessions():
                        self._show_welcome()
                self._reload_sessions()

    def _export(self, sid: str, fmt: str) -> None:
        s = db.get_session(sid)
        if not s:
            return
        ext = "md" if fmt == "md" else "txt"
        path, _ = QFileDialog.getSaveFileName(
            self, "导出会话", os.path.join(exports_dir(), f"{s['title']}.{ext}"),
            f"{ext.upper()} (*.{ext})")
        if not path:
            return
        try:
            n = exporter.export_session(sid, path, fmt)
            QMessageBox.information(self, "导出完成", f"已导出 {n} 条消息到：\n{path}")
        except OSError as e:
            QMessageBox.warning(self, "导出失败", str(e))

    def new_session(self) -> None:
        dlg = NewSessionDialog(self.templates, self)
        if dlg.exec() != QDialog.Accepted:
            return
        title, tid = dlg.result_tuple()
        sid = db.create_session(title, tid)
        self.current_session_id = sid
        self._reload_sessions()
        self.open_session(sid)
        self.stack.setCurrentIndex(0)

    # ================= 对话展示 =================
    def _clear_chat(self) -> None:
        while self.chat_lay.count() > 1:  # 末尾是 stretch
            item = self.chat_lay.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()
        self._bubbles.clear()
        self._placeholder = None
        self._assistant_bubble = None
        self._welcome = None  # widget 已随布局清理，引用置空

    def _show_welcome(self) -> None:
        """空会话欢迎语（DeepSeek 式居中问候）。"""
        if hasattr(self, "_welcome") and self._welcome is not None:
            return
        self._welcome = QLabel("我是文墨，很高兴见到你！\n从左侧新建会话开始写作，或直接输入想法。")
        self._welcome.setObjectName("WelcomeHint")
        self._welcome.setAlignment(Qt.AlignHCenter)
        self.chat_lay.insertWidget(0, self._welcome, 1, Qt.AlignHCenter | Qt.AlignVCenter)

    def _hide_welcome(self) -> None:
        if getattr(self, "_welcome", None) is not None:
            self.chat_lay.removeWidget(self._welcome)
            self._welcome.deleteLater()
            self._welcome = None

    def _add_bubble_row(self, bubble: MessageBubble) -> None:
        self._hide_welcome()
        # 对齐方式由气泡内部处理（用户=右，助手=左），直接整行插入
        self.chat_lay.insertWidget(self.chat_lay.count() - 1, bubble)
        self._bubbles.append(bubble)
        QTimer.singleShot(0, self._scroll_bottom)

    def _scroll_bottom(self) -> None:
        sb = self.chat_scroll.verticalScrollBar()
        sb.setValue(sb.maximum())

    def open_session(self, sid: str, focus_message: str | None = None) -> None:
        if self._worker and self._worker.isRunning():
            QMessageBox.information(self, APP_NAME, "正在生成中，请先停止或等待完成。")
            return
        session = db.get_session(sid)
        if not session:
            return
        self.current_session_id = sid
        self.chat_title.setText(session["title"])
        tpl = prompts_store.get_template(session.get("preset_id"), self.templates)
        self.chat_tpl.setText(f"模板：{tpl['name']}")
        self._clear_chat()
        msgs = db.get_messages(sid)
        if not msgs:
            self._show_welcome()
        for m in msgs:
            bubble = MessageBubble(m["role"], m["id"])
            bubble.finalize(m["content"], m.get("reasoning") or "")
            bubble.delete_requested.connect(self._delete_message)
            bubble.regenerate_requested.connect(self._regenerate)
            self._add_bubble_row(bubble)
            if focus_message and m["id"] == focus_message:
                QTimer.singleShot(0, lambda b=bubble: self.chat_scroll.ensureWidgetVisible(b, 0, 200))
        self.stack.setCurrentIndex(0)
        if not focus_message:
            QTimer.singleShot(0, self._scroll_bottom)

    def _jump_to_message(self, sid: str, mid: str) -> None:
        self.open_session(sid, focus_message=mid)

    def _delete_message(self, mid: str) -> None:
        # 删除助手消息时级联删除触发它的用户消息 → 上下文随之回滚
        db.delete_message_pair(mid)
        if self.current_session_id:
            self.open_session(self.current_session_id)

    # ================= 生成 =================
    def send(self) -> None:
        if self._worker and self._worker.isRunning():
            return
        if not self.current_session_id:
            QMessageBox.information(self, APP_NAME, "请先新建或选择一个会话。")
            return
        text = self.input.toPlainText().strip()
        if not text:
            return
        if not settings_store.get_api_key():
            # 在对话区直接提示（不落库、不弹窗）
            self._show_no_key_notice()
            self.input.clear()
            return

        sid = self.current_session_id
        session = db.get_session(sid)
        # 首条消息自动做标题
        if session["title"] == "新的会话":
            db.rename_session(sid, text[:20])
            self.chat_title.setText(text[:20])
        db.add_message(sid, "user", text)

        bubble = MessageBubble("user")
        bubble.finalize(text)
        self._add_bubble_row(bubble)
        self.input.clear()
        self._reload_sessions()
        self._start_generation()

    def _show_no_key_notice(self) -> None:
        """未配置 API Key：在对话区插入一条提示气泡（不落库，不进历史）。"""
        self._hide_welcome()
        bubble = MessageBubble("assistant")
        bubble.finalize(
            "⚠ **尚未连接 API Key**\n\n"
            "请点击左侧「设置」，在 **API Key** 一栏填写你的 Key（保存前会自动验证）再发送。")
        self.chat_lay.insertWidget(self.chat_lay.count() - 1, bubble)
        QTimer.singleShot(0, self._scroll_bottom)

    def _build_payload(self) -> list[dict]:
        sid = self.current_session_id
        session = db.get_session(sid)
        tpl = prompts_store.get_template(session.get("preset_id"), self.templates)
        msgs = [{"role": "system", "content": tpl["system"]}]
        history = [m for m in db.get_messages(sid, include_error=False)
                   if m["role"] in ("user", "assistant")]
        max_rounds = int(settings_store.get("max_rounds") or 20)
        for m in history[-max_rounds * 2:]:
            msgs.append({"role": m["role"], "content": m["content"]})
        return msgs

    def _start_generation(self) -> None:
        cfg = settings_store.all_config()
        self._placeholder = TypingBubble()
        self._add_bubble_row(self._placeholder)
        self._assistant_bubble = None

        payload = self._build_payload()
        if self.btn_pipeline.isChecked():
            # 四阶段流水线：payload = [system, ...历史(含本轮用户消息)]
            self._worker = PipelineWorker(
                cfg["base_url"], cfg["api_key"], cfg["model"],
                payload[1:-1], payload[-1]["content"], payload[0]["content"],
                float(cfg["temperature"] or 0.8), self)
            self._worker.stage_started.connect(self._on_stage_started)
            self._worker.stage_token.connect(self._on_stage_token)
            self._worker.stage_done.connect(self._on_stage_done)
        else:
            self._worker = LLMWorker(
                cfg["base_url"], cfg["api_key"], cfg["model"],
                payload, float(cfg["temperature"] or 0.8), self)
            self._worker.reasoning.connect(self._on_reasoning)
        self._worker.token.connect(self._on_token)
        self._worker.finished_sig.connect(self._on_finished)
        self._set_action_state(sending=True)
        self._worker.start()
        QTimer.singleShot(0, self._scroll_bottom)

    # ---- 流水线阶段信号 ----
    def _on_stage_started(self, idx: int, title: str) -> None:
        bubble = self._active_bubble()
        bubble.begin_stage(idx, title)
        self._scroll_bottom()

    def _on_stage_token(self, idx: int, piece: str) -> None:
        bubble = self._active_bubble()
        bubble.append_stage(idx, piece)
        self._scroll_bottom()

    def _on_stage_done(self, idx: int) -> None:
        if self._assistant_bubble is not None:
            self._assistant_bubble.end_stage(idx)

    def _active_bubble(self) -> MessageBubble:
        """取当前正在流式输出的气泡：占位气泡直接转正，没有就新建。"""
        bubble = self._assistant_bubble or self._placeholder
        if bubble is None:
            bubble = MessageBubble("assistant")
            self._add_bubble_row(bubble)
        self._placeholder = None
        self._assistant_bubble = bubble
        return bubble

    def _on_token(self, piece: str) -> None:
        bubble = self._active_bubble()
        bubble.set_stream_text((bubble._content or "") + piece)
        self._scroll_bottom()

    def _on_reasoning(self, piece: str) -> None:
        bubble = self._active_bubble()
        bubble.set_stream_reasoning((bubble._reasoning or "") + piece)
        self._scroll_bottom()

    def _on_finished(self, status: str, content: str, extra: str) -> None:
        self._set_action_state(sending=False)
        sid = self.current_session_id
        cfg = settings_store.all_config()

        bubble = self._assistant_bubble or self._placeholder
        if bubble is not None:
            self._placeholder = None
            if status == "done":
                bubble.finalize(content, extra)
            elif status == "stopped":
                bubble.finalize(content or "（已停止）", extra)
            else:
                bubble.finalize((content + "\n\n" if content else "") + f"⚠ {extra}")

        if sid:
            if status == "error":
                db.add_message(sid, "assistant", content or f"⚠ {extra}",
                               model=cfg["model"], status="error",
                               reasoning=extra if content else None)
            else:
                db.add_message(sid, "assistant", content or "（已停止）",
                               model=cfg["model"], status=status, reasoning=extra)
        self._reload_sessions()

    def stop_generation(self) -> None:
        if self._worker and self._worker.isRunning():
            self._worker.stop()

    def _regenerate(self, mid: str) -> None:
        """删除该助手消息（必须是最后一条）后重新生成。"""
        if self._worker and self._worker.isRunning():
            return
        sid = self.current_session_id
        if not sid:
            return
        msgs = db.get_messages(sid)
        if not msgs or msgs[-1]["id"] != mid or msgs[-1]["role"] != "assistant":
            QMessageBox.information(self, APP_NAME, "只能重新生成最后一条回复。")
            return
        db.delete_message(mid)
        self.open_session(sid)
        self._start_generation()

    # ================= 设置 =================
    def open_settings(self) -> None:
        dlg = SettingsDialog(self)
        dlg.exec()
