"""UI 视觉验收（离线，不调 API，不动数据库）：填充假消息后截图。

用法：venv/Scripts/python.exe tests/ui_preview.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from core.settings_store import seed_first_run
from ui.main_window import MainWindow
from ui.theme import THEME
from ui.chat_widgets import MessageBubble


def main() -> None:
    seed_first_run()
    app = QApplication(sys.argv)
    app.setStyleSheet(THEME)
    win = MainWindow()
    win.show()

    def fill() -> None:
        win._clear_chat()
        win._hide_welcome()

        u = MessageBubble("user")
        u.finalize("帮我以「深海里的信」为题写一个 200 字的科幻微小说开头。")
        win._add_bubble_row(u)

        a = MessageBubble("assistant", "preview-1")
        # 模拟四阶段流水线：3 个阶段块流式生长 → 逐个收起 → 正文定稿
        stages = [
            ("规划大纲", "1. 主题定位：深海基站 + 时间错位的信件；\n"
                        "2. 骨架：收信异常 → 潜入残骸 → 身份揭晓；\n"
                        "3. 结尾钩子：落款是自己的名字。"),
            ("补充设定", "人物：林晚，灯塔站观察员，孤僻而较真；\n"
                        "背景：2077 年，马里亚纳「灯塔站」水听阵列；\n"
                        "逻辑修补：信件经由时间褶皱折返，站史档案可佐证。"),
            ("细化大纲", "第 1 节（约80字）：异常信号打破值班夜；\n"
                        "第 2 节（约80字）：水听阵列捕捉到带信封的信号；\n"
                        "第 3 节（约40字）：落款揭晓，收束于寒意。"),
        ]
        for i, (name, text) in enumerate(stages, start=1):
            a.begin_stage(i, name)
            a.append_stage(i, text)
            a.end_stage(i)
        a.finalize(
            "### 深海里的信\n\n"
            "马里亚纳海沟，水深一万零九百米。**灯塔站**的观察员林晚收到了一条"
            "不该存在的消息——发信时间显示为七十年前，落款是她自己的名字。\n\n"
            "「水听阵列又抓到了那个信号。」同事的头发因静电竖起，「这次……带信封了。」\n\n"
            "1. 沉船残骸\n"
            "2. 时间褶皱\n"
            "3. 一封没有寄出的信",
            "【阶段1·规划大纲】\n" + stages[0][1] + "\n\n"
            "【阶段2·补充设定】\n" + stages[1][1] + "\n\n"
            "【阶段3·细化大纲】\n" + stages[2][1],
        )
        win._add_bubble_row(a)
        QTimer.singleShot(600, shoot)

    def shoot() -> None:
        a = win._bubbles[-1]
        doc_h = int(a.body.document().size().height())
        print("window:", win.width(), "x", win.height(),
              "| column:", win.chat_container.width(),
              "| assistant bubble:", a.width(), "x", a.height(),
              "| body:", a.body.width(), "x", a.body.height(),
              "| doc h:", doc_h,
              "| stage sections:", len(a._stage_sections))
        assert a.body.height() <= doc_h + 10, \
            f"正文高度仍虚高: body={a.body.height()} vs doc={doc_h}"
        img = app.primaryScreen().grabWindow(int(win.winId()))
        out = os.environ.get("UI_PREVIEW_OUT", r"D:/WenMo/app/_ui_check.png")
        img.save(out)
        print("PREVIEW_SHOT_OK ->", out)
        app.quit()

    QTimer.singleShot(500, fill)
    QTimer.singleShot(6000, app.quit)  # 兜底
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
