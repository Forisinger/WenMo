"""文墨 - 设置对话框。

API Key 存 Windows 凭据管理器（界面只显示尾 4 位）；
BaseURL / 模型名 / temperature / 上下文轮数存 settings 表；
「测试连接」发一条极短请求验证地址 + Key + 模型名。
"""
from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import (
    QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox, QFormLayout,
    QHBoxLayout, QLabel, QLineEdit, QPushButton, QSpinBox, QVBoxLayout,
)

from core import settings_store
from core.config import PROVIDER_PRESETS
from core.llm import test_connection


class _TestWorker(QThread):
    done = Signal(bool, str)

    def __init__(self, base_url, key, model, parent=None):
        super().__init__(parent)
        self._args = (base_url, key, model)

    def run(self):
        self.done.emit(*test_connection(*self._args))


class SettingsDialog(QDialog):
    settings_changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("设置 — 文墨")
        self.setMinimumWidth(520)
        self._test_worker = None

        root = QVBoxLayout(self)
        form = QFormLayout()
        form.setSpacing(10)
        root.addLayout(form)

        # 服务商预设
        self.preset = QComboBox()
        for p in PROVIDER_PRESETS:
            self.preset.addItem(p["name"])
        self.preset.currentIndexChanged.connect(self._apply_preset)
        form.addRow("服务商预设", self.preset)

        # BaseURL
        self.base_url = QLineEdit(settings_store.get("base_url"))
        self.base_url.setPlaceholderText("https://api.deepseek.com/v1")
        form.addRow("接口地址", self.base_url)

        # 模型
        self.model = QLineEdit(settings_store.get("model"))
        self.model.setPlaceholderText("deepseek-flash")
        form.addRow("模型名", self.model)

        # API Key
        key_row = QHBoxLayout()
        current_key = settings_store.get_api_key()
        self.key_edit = QLineEdit()
        self.key_edit.setPlaceholderText(
            f"已保存（尾号 {current_key[-4:]}），输入新 Key 覆盖" if current_key else "sk-…")
        self.key_edit.setEchoMode(QLineEdit.Password)
        key_row.addWidget(self.key_edit, 1)
        self.key_hint = QLabel(
            "已入凭据管理器" if settings_store.all_config()["key_in_keyring"] else "明文本地存储")
        key_row.addWidget(self.key_hint)
        form.addRow("API Key", key_row)

        # temperature / 轮数
        self.temperature = QDoubleSpinBox()
        self.temperature.setRange(0.0, 2.0)
        self.temperature.setSingleStep(0.1)
        self.temperature.setValue(float(settings_store.get("temperature") or 0.8))
        form.addRow("Temperature", self.temperature)

        self.max_rounds = QSpinBox()
        self.max_rounds.setRange(2, 200)
        self.max_rounds.setValue(int(settings_store.get("max_rounds") or 20))
        form.addRow("上下文最大轮数", self.max_rounds)

        # 测试连接
        test_row = QHBoxLayout()
        self.test_btn = QPushButton("测试连接")
        self.test_btn.clicked.connect(self._do_test)
        self.test_result = QLabel("")
        self.test_result.setObjectName("ChatHint")
        test_row.addWidget(self.test_btn)
        test_row.addWidget(self.test_result, 1)
        root.addLayout(test_row)

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    # ---- 事件 ----
    def _apply_preset(self, idx: int) -> None:
        p = PROVIDER_PRESETS[idx]
        if p["base_url"]:
            self.base_url.setText(p["base_url"])
            self.model.setText(p["model"])

    def _do_test(self) -> None:
        if self._test_worker and self._test_worker.isRunning():
            return
        key = self.key_edit.text().strip() or settings_store.get_api_key()
        self.test_btn.setEnabled(False)
        self.test_result.setText("测试中…")
        self._test_worker = _TestWorker(self.base_url.text().strip(), key,
                                        self.model.text().strip(), self)
        self._test_worker.done.connect(self._on_test_done)
        self._test_worker.start()

    def _on_test_done(self, ok: bool, msg: str) -> None:
        self.test_btn.setEnabled(True)
        self.test_result.setText(("✓ " if ok else "✗ ") + msg)

    def _save(self) -> None:
        base_url = self.base_url.text().strip()
        model = self.model.text().strip()
        if base_url:
            settings_store.set("base_url", base_url)
        if model:
            settings_store.set("model", model)
        new_key = self.key_edit.text().strip()
        if new_key:
            in_keyring = settings_store.set_api_key(new_key)
            self.key_hint.setText("已入凭据管理器" if in_keyring else "明文本地存储")
            self.key_edit.clear()
            self.key_edit.setPlaceholderText(f"已保存（尾号 {new_key[-4:]}），输入新 Key 覆盖")
        settings_store.set("temperature", str(self.temperature.value()))
        settings_store.set("max_rounds", str(self.max_rounds.value()))
        self.settings_changed.emit()
        self.accept()
