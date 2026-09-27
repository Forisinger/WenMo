"""文墨 - 四阶段创作流水线。

① 规划大纲 → ② 补充设定 → ③ 细化大纲 → ④ 生成文本
前三阶段过程可见（折叠块），第四阶段的正文才是正式回复。

阶段产物落库格式（存 messages.reasoning 列）：
    【阶段1·规划大纲】
    <内容>
    【阶段2·补充设定】
    ...
"""
from PySide6.QtCore import QThread, Signal

from core.llm import stream_request

STAGES = [
    ("规划大纲",
     "你现在是写作策划。基于【对话上下文】与【用户请求】，先自主规划本次创作的大纲：\n"
     "1. 主题定位与核心冲突（或文章论点）；\n"
     "2. 结构骨架（开头 / 发展 / 高潮 / 结尾，或相应的论述结构）；\n"
     "3. 各部分要点，逐条列出。\n"
     "只输出大纲本身，不要输出正文，不要解释你在做什么。"),
    ("补充设定",
     "你现在是设定设计师。审视上面的大纲，为本次创作补充必要的支撑设定：\n"
     "1. 人物（或主体）及其动机、关系；\n"
     "2. 世界观 / 背景细节 / 时间线；\n"
     "3. 风格与基调（人称、时态、语言质感）；\n"
     "4. 指出大纲中的逻辑漏洞并给出修补方案。\n"
     "用户已给出的设定必须遵守，不得篡改。只输出设定补充本身。"),
    ("细化大纲",
     "你现在是执行编辑。把大纲与设定整合为一份细化后的执行大纲：\n"
     "1. 分节 / 分章列出；\n"
     "2. 每节写明：要点、节奏、篇幅分配（如「约300字」）；\n"
     "3. 标注开头句的处理方式与全文收束方式。\n"
     "只输出细化大纲本身。"),
    ("生成文本",
     "你现在是作者。严格依据上面的细化大纲生成完整文本：\n"
     "- 直接输出正文本身，不要复述大纲、不要分点说明、不要加任何点评或后记；\n"
     "- 严格遵守用户请求中给定的题材、设定、文风与篇幅要求；\n"
     "- 只有一次机会交付成稿，保证完整性。"),
]


def format_stages(completed: list[tuple[str, str]]) -> str:
    """把 (阶段名, 内容) 列表格式化为落库/解析用的标记文本。"""
    parts = []
    for i, (name, text) in enumerate(completed, start=1):
        parts.append(f"【阶段{i}·{name}】\n{text.strip()}")
    return "\n\n".join(parts)


class PipelineWorker(QThread):
    """四阶段顺序流式生成。"""

    stage_started = Signal(int, str)        # 阶段序号(1-4), 阶段名
    stage_token = Signal(int, str)          # 阶段序号, 增量
    stage_done = Signal(int)                # 阶段序号（正常完成即收起）
    token = Signal(str)                     # 第4阶段正文增量（复用现有 token 通道）
    finished_sig = Signal(str, str, str)    # status, content(正文), reasoning(阶段标记文本)

    def __init__(self, base_url: str, api_key: str, model: str,
                 history: list[dict], user_request: str, template_system: str,
                 temperature: float, parent=None):
        super().__init__(parent)
        self._base_url = base_url
        self._api_key = api_key
        self._model = model
        self._history = history          # [{"role","content"}]，不含本轮新消息
        self._user_request = user_request
        self._template_system = template_system
        self._temperature = temperature
        self._stop = False
        self._holder: dict = {}
        self._completed: list[tuple[str, str]] = []

    def stop(self) -> None:
        self._stop = True
        resp = self._holder.get("resp")
        if resp is not None:
            try:
                resp.close()
            except Exception:
                pass

    def _build_messages(self, stage_idx: int) -> list[dict]:
        """每阶段：system=模板提示词+阶段指令；user=历史+请求+前序阶段产物。"""
        name, instruction = STAGES[stage_idx]
        messages: list[dict] = [{"role": "system",
                                 "content": f"{self._template_system}\n\n{instruction}"}]
        messages.extend(self._history)
        user_parts = [f"【用户请求】\n{self._user_request}"]
        for i, (done_name, text) in enumerate(self._completed):
            user_parts.append(f"【已完成阶段{i + 1}·{done_name}】\n{text.strip()}")
        messages.append({"role": "user", "content": "\n\n".join(user_parts)})
        return messages

    def run(self) -> None:
        import os
        import time
        _dbg = os.environ.get("WENMO_DEBUG") == "1"

        def _d(msg):
            if _dbg:
                print(f"[pipeline %.1fs] %s" % (time.time() - _t0, msg), flush=True)

        _t0 = time.time()
        _d("run() 进入")
        final_content = ""
        final_reasoning = ""
        for idx in range(len(STAGES)):
            if self._stop:
                _d(f"阶段{idx + 1} 前检测到 stop")
                break
            name, _ = STAGES[idx]
            # 前 3 个阶段发阶段信号（折叠块展示）；第 4 阶段正文直接走 token 通道
            if idx < 3:
                self.stage_started.emit(idx + 1, name)
            _d(f"阶段{idx + 1}·{name} stream_request 开始")
            status, content, _, err = stream_request(
                self._base_url, self._api_key, self._model,
                self._build_messages(idx), self._temperature,
                on_token=(lambda piece, i=idx: self.stage_token.emit(i + 1, piece))
                if idx < 3 else self.token.emit,
                stop_check=lambda: self._stop,
                response_holder=self._holder,
            )
            _d(f"阶段{idx + 1} 返回 status={status} len={len(content)} err={err[:60]}")
            if status == "error":
                self.finished_sig.emit("error", final_content, err)
                return
            if idx == 3:
                final_content = content
                break
            self._completed.append((name, content))
            self.stage_done.emit(idx + 1)

        final_reasoning = format_stages(self._completed)
        status = "stopped" if self._stop else "done"
        if status == "stopped" and not final_content.strip():
            final_content = "（已停止）"
        _d(f"emit finished {status}")
        self.finished_sig.emit(status, final_content, final_reasoning)
