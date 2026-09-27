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
_APP_TITLE = "文墨 — AI 写作助手"


def _raise_existing_window() -> None:
    """把已有实例的主窗口还原并拉到屏幕最顶层。"""
    import ctypes

    user32 = ctypes.windll.user32
    hwnd = user32.FindWindowW(None, _APP_TITLE)
    if not hwnd:
        return
    if user32.IsIconic(hwnd):
        user32.ShowWindow(hwnd, 9)          # SW_RESTORE：最小化则还原
    else:
        user32.ShowWindow(hwnd, 5)          # SW_SHOW
    # topmost 闪烁：强制压过所有窗口，再还回普通层级，最后抢前台
    SWP_NOMOVE, SWP_NOSIZE = 0x0002, 0x0001
    HWND_TOPMOST, HWND_NOTOPMOST = -1, -2
    user32.SetWindowPos(hwnd, HWND_TOPMOST, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE)
    user32.SetWindowPos(hwnd, HWND_NOTOPMOST, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE)
    user32.SetForegroundWindow(hwnd)
    user32.SwitchToThisWindow(hwnd, True)   # 绕过前台锁定限制的兜底


def _acquire_single_instance() -> bool:
    """单实例锁（Win32 命名互斥体）。

    返回 True = 获得锁，正常启动；False = 已有实例（已唤起其窗口，调用方应退出）。
    互斥体随进程存活，崩溃/被杀时由系统自动释放，不会留死锁。
    """
    import ctypes

    ERROR_ALREADY_EXISTS = 183
    SYNCHRONIZE = 0x00100000
    name = "WenMo.SingleInstance"
    # use_last_error=True：ctypes 才会稳定捕获 Win32 错误码（windll 默认不捕获）
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    # 先直接探测锁是否已被持有
    if k32.OpenMutexW(SYNCHRONIZE, False, name):
        _raise_existing_window()
        return False
    k32.CreateMutexW(None, False, name)
    if ctypes.get_last_error() == ERROR_ALREADY_EXISTS:
        _raise_existing_window()
        return False
    return True


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
        if not _acquire_single_instance():
            return                           # 已有实例：窗口已唤起，本进程退出
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
