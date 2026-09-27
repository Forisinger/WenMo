"""文墨 - 深色主题 QSS（DeepSeek 风格对话界面）。"""

THEME = """
* {
    font-family: "Microsoft YaHei UI", "Microsoft YaHei", sans-serif;
    font-size: 14px;
    color: #e2e5ec;
}
QMainWindow, QDialog { background: #17191f; }
QWidget { background: transparent; }

/* ---- 侧栏 ---- */
#Sidebar { background: #1d2027; border-right: 1px solid #262a33; }
#AppTitle { font-size: 20px; font-weight: 600; color: #dfe4ee; padding: 6px 2px; }
#AppSub { font-size: 12px; color: #7d8593; padding-bottom: 4px; }

QListWidget {
    background: #22252e; border: 1px solid #2b303b; border-radius: 8px;
    padding: 4px; outline: 0;
}
QListWidget::item { padding: 8px 10px; border-radius: 6px; color: #c8cdd8; }
QListWidget::item:hover { background: #2a2f3a; }
QListWidget::item:selected { background: #33405e; color: #eef1f7; }

/* ---- 按钮 ---- */
QPushButton {
    background: #2a2f3a; border: 1px solid #343b48; border-radius: 7px;
    padding: 7px 14px; color: #d7dbe4;
}
QPushButton:hover { background: #333a48; }
QPushButton:pressed { background: #3b4353; }
QPushButton:disabled { color: #6b7280; background: #23272f; border-color: #2b303b; }

/* 输入面板右下角的圆形两态按钮：发送 / 停止 */
QPushButton#BtnSend {
    background: #3d5afe; border: none; border-radius: 19px;
    min-width: 38px; max-width: 38px; min-height: 38px; max-height: 38px;
    color: white; font-size: 18px; font-weight: 600; padding: 0;
}
QPushButton#BtnSend:hover { background: #556cf7; }
QPushButton#BtnSend:disabled { background: #2c3350; color: #6b7280; }
QPushButton#BtnStop {
    background: #8c3134; border: none; border-radius: 19px;
    min-width: 38px; max-width: 38px; min-height: 38px; max-height: 38px;
    color: #ffd9db; font-size: 14px; font-weight: 600; padding: 0;
}
QPushButton#BtnStop:hover { background: #a03a3e; }

/* ---- 输入面板 ---- */
#InputPanel {
    background: #20242c; border: 1px solid #2b303b; border-radius: 14px;
}
#InputPanel QPlainTextEdit {
    background: transparent; border: none; padding: 10px 12px 4px 12px;
    selection-background-color: #3d5afe;
}
#InputHint { color: #6b7280; font-size: 12px; }

/* ---- 聊天区 ---- */
#ChatScroll { background: #17191f; border: none; }
#ChatColumn { background: transparent; }
#ChatHeader { font-size: 16px; font-weight: 600; color: #dfe4ee; }
#ChatTpl { color: #7d8593; font-size: 12px; }
#ChatHint { color: #7d8593; font-size: 12px; }

QScrollArea { border: none; }
QScrollBar:vertical { background: transparent; width: 10px; margin: 2px; }
QScrollBar::handle:vertical { background: #333a48; border-radius: 5px; min-height: 30px; }
QScrollBar::handle:vertical:hover { background: #424b5d; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }

/* ---- 消息 ---- */
#AvatarAssistant {
    background: #3d5afe; color: white; font-weight: 600; font-size: 15px;
    border-radius: 17px;
}
#AvatarUser {
    background: #475069; color: #e2e5ec; font-weight: 600; font-size: 13px;
    border-radius: 17px;
}

/* 用户气泡：右对齐圆角 */
#BubbleUser {
    background: #2f3a5c; border: 1px solid #3b4a74; border-radius: 12px;
    padding: 10px 14px;
}

/* 助手正文：无底色通栏 */
#BubbleBody { background: transparent; border: none; font-size: 14px; }

/* 思维链折叠块 */
#ReasoningToggle {
    background: transparent; border: none; color: #8f98a8;
    font-size: 12px; padding: 2px 0; text-align: left;
}
#ReasoningToggle:hover { color: #c8cdd8; }
#ReasoningBox {
    background: #1b1e25; border: 1px solid #2b303b; border-radius: 8px;
    color: #8f98a8; padding: 8px; font-size: 13px;
}

/* 空会话欢迎语 */
#WelcomeHint {
    color: #6b7280; font-size: 15px; background: transparent;
    padding: 40px;
}

/* 助手消息操作栏 */
#ActionBtn {
    background: transparent; border: none; border-radius: 6px;
    color: #8f98a8; font-size: 12px; padding: 3px 9px;
}
#ActionBtn:hover { background: #2a2f3a; color: #e2e5ec; }

/* 创作流水线开关 */
#PipelineToggle {
    background: transparent; border: none; border-radius: 6px;
    color: #8f98a8; font-size: 12px; padding: 4px 10px;
}
#PipelineToggle:hover { background: #2a2f3a; color: #e2e5ec; }
#PipelineToggle:checked { background: #2c3350; color: #8fa8ff; }

/* ---- 菜单 / 对话框杂项 ---- */
QMenu { background: #262a33; border: 1px solid #343b48; border-radius: 6px; padding: 4px; }
QMenu::item { padding: 6px 22px; border-radius: 4px; }
QMenu::item:selected { background: #3d5afe; color: white; }
QComboBox {
    background: #22252e; border: 1px solid #2b303b; border-radius: 7px; padding: 6px 10px;
}
QComboBox QAbstractItemView {
    background: #262a33; border: 1px solid #343b48;
    selection-background-color: #33405e;
}
QLabel { background: transparent; }
QSpinBox, QDoubleSpinBox {
    background: #22252e; border: 1px solid #2b303b; border-radius: 6px; padding: 5px;
}
QDialogButtonBox QPushButton { min-width: 76px; }
"""
