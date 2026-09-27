"""文墨 - 冒烟测试（无窗口，纯逻辑层验证）。

用法：venv/Scripts/python.exe tests/smoke_test.py
覆盖：模块导入 / 数据库读写级联 / 真实 API 流式对话。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

PASS = []


def ok(name: str) -> None:
    PASS.append(name)
    print(f"  ✓ {name}")


# ---------- 1. 模块导入 ----------
print("[1] 模块导入")
import core.config as config
import core.db as db
import core.exporter as exporter
import core.llm as llm
import core.prompts_store as prompts_store
import core.settings_store as settings_store
from ui import chat_widgets, history_page, main_window, settings_dialog, theme  # noqa: F401
ok("全部模块导入成功")

# ---------- 2. 数据库 ----------
print("[2] 数据库")
db.init_db()
sid = db.create_session("测试会话", "free")
u1 = db.add_message(sid, "user", "你好，请介绍一下你自己")
db.add_message(sid, "assistant", "我是文墨，你的写作助手。")
assert len(db.get_messages(sid)) == 2
db.rename_session(sid, "改名后的会话")
assert db.get_session(sid)["title"] == "改名后的会话"
rows = db.search_messages("文墨")
assert any(r["session_id"] == sid for r in rows)
# 级联删除
db.add_message(sid, "user", "再来一条")
sid2 = db.create_session("级联测试")
db.add_message(sid2, "user", "x")
db.delete_session(sid)
assert db.get_session(sid) is None
db.delete_session(sid2)
ok("建会话/落消息/改名/搜索/级联删除")

# 导出
sid3 = db.create_session("导出测试", "free")
db.add_message(sid3, "user", "**加粗**内容")
db.add_message(sid3, "assistant", "回复内容")
out = os.path.join(config.exports_dir(), "smoke_export.md")
n = exporter.export_session(sid3, out, "md")
assert n == 2 and os.path.exists(out) and os.path.getsize(out) > 0
db.delete_session(sid3)
os.remove(out)
ok("会话导出 md")

# 删除助手消息级联回滚用户消息
sid4 = db.create_session("级联回滚测试", "free")
uid = db.add_message(sid4, "user", "触发消息")
aid = db.add_message(sid4, "assistant", "AI 回复")
db.add_message(sid4, "user", "下一条用户消息")  # 不应被误删
deleted = db.delete_message_pair(aid)
assert deleted == [aid, uid], f"级联删除返回异常: {deleted}"
left = db.get_messages(sid4)
assert len(left) == 1 and left[0]["content"] == "下一条用户消息", "上下文回滚失败"
assert db.get_message(aid) is None and db.get_message(uid) is None
db.delete_session(sid4)
ok("删除助手消息级联回滚用户消息")

# ---------- 3. 模板 ----------
print("[3] 写作模板")
prompts_store.ensure_default_prompts()
tpls = prompts_store.load_templates()
assert len(tpls) >= 7, f"模板数量不足: {len(tpls)}"
assert prompts_store.get_template("outline", tpls)["name"] == "大纲生成"
ok(f"内置模板 {len(tpls)} 个，加载与回退正常")

# ---------- 4. 设置 ----------
print("[4] 设置存储")
settings_store.seed_first_run()
key = settings_store.get_api_key() or ""
cfg = settings_store.all_config()
assert cfg["base_url"] and cfg["model"]
if key:
    key_ok, key_msg = llm.test_connection(cfg["base_url"], key, cfg["model"])
    if not key_ok:
        ok(f"已配置的 Key 验证失败（{key_msg}）——真实 API 用例将跳过")
        key = ""
    else:
        ok(f"Key 已配置且有效（尾号 {key[-4:]}），BaseURL={cfg['base_url']}, Model={cfg['model']}")
else:
    ok("本机未配置 Key（开源版不内置）——真实 API 用例将跳过")

# ---------- 5/6. 真实 API 用例（配置了 Key 才跑） ----------
if key:
    print("[5] 真实 API 流式对话（deepseek-flash）")
    from PySide6.QtCore import QCoreApplication, QTimer

    app = QCoreApplication(sys.argv)
    result = {"status": None, "content": "", "reasoning": "", "tokens": 0}

    worker = llm.LLMWorker(
        cfg["base_url"], key, cfg["model"],
        [{"role": "user", "content": "用一句话介绍你自己。"}], 0.8)
    worker.token.connect(lambda p: (result.update(content=result["content"] + p),
                                    result.update(tokens=result["tokens"] + 1)))
    worker.reasoning.connect(lambda p: result.update(reasoning=result["reasoning"] + p))
    worker.finished_sig.connect(lambda s, c, e: result.update(status=s, err=e))
    worker.start()

    def _check() -> None:
        if result["status"] is not None:
            timer.stop()  # 只触发一次，避免污染后续测试节
            app.quit()

    timer = QTimer()
    timer.timeout.connect(_check)
    timer.start(100)
    guard5 = QTimer()                     # 90s 兜底：可主动停止，防止污染后续测试节
    guard5.setSingleShot(True)
    guard5.timeout.connect(app.quit)
    guard5.start(90000)
    app.exec()

    assert result["status"] == "done", f"流式失败: status={result['status']} err={result.get('err')}"
    assert result["tokens"] > 0 and len(result["content"]) > 5
    ok(f"流式完成：{result['tokens']} 个增量块，回复 {len(result['content'])} 字"
       + (f"（含思考 {len(result['reasoning'])} 字）" if result["reasoning"] else ""))

    # ---------- 6. 四阶段创作流水线 ----------
    print("[6] 四阶段创作流水线（规划大纲→补充设定→细化大纲→生成文本）")
    guard5.stop()  # 上节的兜底 quit 不再生效
    from PySide6.QtCore import QObject, Slot as QSlot
    from core.pipeline import PipelineWorker, format_stages

    class _PipelineSink(QObject):
        """模拟真实应用的信号接收方式（槽在主线程执行）。"""

        def __init__(self, cfg2, key2, tpls2):
            super().__init__()
            self.r = {"starts": [], "done": 0, "tokens": 0, "status": None,
                      "content": "", "reasoning": ""}
            self.pw = PipelineWorker(
                cfg2["base_url"], key2, cfg2["model"], [], "写一首关于秋天的四行小诗。",
                tpls2["free"]["system"], 0.8)
            self.pw.stage_started.connect(self.on_start)
            self.pw.stage_token.connect(self.on_token)
            self.pw.stage_done.connect(self.on_stage_done)
            self.pw.finished_sig.connect(self.on_finished)
            self.pw.start()

        @QSlot(int, str)
        def on_start(self, i, n):
            self.r["starts"].append(n)
            print(f"    ▶ 阶段{i}·{n}")

        @QSlot(int, str)
        def on_token(self, i, p):
            self.r["tokens"] += 1

        @QSlot(int)
        def on_stage_done(self, i):
            self.r["done"] += 1
            print(f"    ✓ 阶段{i} 完成")

        @QSlot(str, str, str)
        def on_finished(self, s, c, r):
            self.r.update(status=s, content=c, reasoning=r)
            print(f"    流水线结束：{s}，正文 {len(c)} 字")

    sink = _PipelineSink(cfg, key, tpls)
    t2 = QTimer()
    t2.timeout.connect(lambda: app.quit() if sink.r["status"] is not None else None)
    t2.start(200)
    QTimer.singleShot(420000, app.quit)  # 7 分钟兜底（流水线四阶段，服务端偶发慢）
    app.exec()

    result2 = sink.r
    assert result2["status"] == "done", \
        f"流水线失败: status={result2['status']}, stages={result2['starts']}, " \
        f"done={result2['done']}, tokens={result2['tokens']}"
    assert result2["starts"] == ["规划大纲", "补充设定", "细化大纲"], \
        f"阶段顺序异常: {result2['starts']}"
    assert result2["done"] == 3
    assert len(result2["content"]) > 10, "最终正文为空"
    for m in ("【阶段1·规划大纲】", "【阶段2·补充设定】", "【阶段3·细化大纲】"):
        assert m in result2["reasoning"], f"缺少标记 {m}"
    ok(f"4 阶段跑通：正文 {len(result2['content'])} 字，3 个阶段块已落 reasoning 标记")
else:
    print("    （跳过第 5/6 节：需要配置 API Key 后才能跑真实 API 用例）")

print(f"\n全部 {len(PASS)} 项通过 ✓")
