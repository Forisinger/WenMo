"""文墨 - 程序入口。"""
import os
import sys
import traceback

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from core import prompts_store
from core.config import data_dir
from core.settings_store import seed_first_run
from ui.main_window import MainWindow
from ui.theme import THEME

_CRASH_LOG = os.path.join(data_dir(), "crash.log")


def _icon_path() -> str:
    """应用图标路径：兼容 PyInstaller onefile 解包目录与源码运行。"""
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, "assets", "icon.ico")


def _log_crash(exc: BaseException) -> None:
    try:
        with open(_CRASH_LOG, "a", encoding="utf-8") as f:
            import time
            f.write(f"\n==== {time.strftime('%Y-%m-%d %H:%M:%S')} ====\n")
            f.write(traceback.format_exc())
    except OSError:
        pass


def main() -> None:
    try:
        seed_first_run()                       # 首启：预置 Key + 默认配置 + 建库
        prompts_store.ensure_default_prompts() # 首启：落地写作模板 JSON

        app = QApplication(sys.argv)
        app.setApplicationName("文墨")
        app.setOrganizationName("WenMo")
        app.setWindowIcon(QIcon(_icon_path()))
        app.setStyleSheet(THEME)

        win = MainWindow()
        win.show()
        sys.exit(app.exec())
    except Exception:
        _log_crash(sys.exception())
        raise


if __name__ == "__main__":
    main()
