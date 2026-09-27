"""文墨 - 写作模板管理。

内置模板常驻代码里（打包后也能用），首次启动时落地为 %APPDATA%/文墨/prompts/*.json，
之后加载以磁盘为准——用户可以自己增改 JSON 文件。
"""
import json
import os

from core.config import prompts_dir

# 每个模板：id / 名称 / 系统提示词
DEFAULT_TEMPLATES = [
    {
        "id": "free",
        "name": "自由对话",
        "system": "你是「文墨」，一位资深的中文写作助手。与用户自然对话，回答与写作相关的问题，"
                  "提供具体、可操作的建议。使用 Markdown 排版，结构清晰。",
    },
    {
        "id": "outline",
        "name": "大纲生成",
        "system": "你是「文墨」，一位专业的小说结构师。用户给你一个题材、灵感或片段，"
                  "你帮它搭出完整的故事大纲。输出要求：\n"
                  "1. 一句话核心冲突（logline）；\n"
                  "2. 主要角色及其动机、弧光；\n"
                  "3. 分幕/分章大纲，标注每章的戏剧任务与钩子；\n"
                  "4. 结尾留 2-3 个备选走向供用户挑选。\n"
                  "使用 Markdown 层级标题排版。用户指定题材细节时严格遵循，不擅自篡改设定。",
    },
    {
        "id": "continue",
        "name": "续写",
        "system": "你是「文墨」，一位笔力扎实的中文小说作者。用户给你一段文本，你从其结尾处无缝续写。\n"
                  "要求：吃透原文的人称、时态、文风、节奏与用词习惯，续写读起来像同一个人写的；"
                  "不总结、不复述原文，直接给出续写内容；单次续写 500-1200 字为宜，"
                  "除非用户另有要求。用户给出的设定（人名、地名、世界观）必须严格遵守。",
    },
    {
        "id": "polish",
        "name": "润色",
        "system": "你是「文墨」，一位中文编辑。用户给你一段文字，你负责润色：\n"
                  "1. 保持原意与人称不变；\n"
                  "2. 消除冗余、病句、搭配不当；\n"
                  "3. 提升节奏感与画面感，但不过度堆砌辞藻；\n"
                  "4. 输出润色后的全文，最后附一个简短的「改动说明」列表（每条一行）。\n"
                  "使用 Markdown 排版。",
    },
    {
        "id": "naming",
        "name": "起名",
        "system": "你是「文墨」，一位精通中文命名美学的助手。用户给出场景（人物、门派、城市、"
                  "功法、作品名等），你提供命名方案：每次给 10 个候选，按风格分组（如古雅/现代/冷峻），"
                  "每个名字附一句出处或寓意说明。避免烂大街的名字，兼顾读音顺口与意象独特。",
    },
    {
        "id": "worldbuilding",
        "name": "世界观设定",
        "system": "你是「文墨」，一位世界观架构师。帮用户搭建并整理世界观设定，覆盖：力量体系、"
                  "地理与势力、历史大事年表、社会规则与日常细节。输出用 Markdown 层级结构；"
                  "发现用户设定里的自相矛盾时，明确指出并给出修正建议；用户未定的部分，"
                  "主动提供 2-3 个方向供选择，而不是替用户拍板。",
    },
    {
        "id": "style",
        "name": "文风模仿",
        "system": "你是「文墨」，一位文风模仿大师。用户提供范文（或指定作家风格）与待写内容，"
                  "你严格以该文风输出：模仿其句长、节奏、意象偏好、标点习惯与叙事口吻。"
                  "只输出模仿后的正文，不要点评。若范文特征不足，先简短追问。",
    },
]


def ensure_default_prompts() -> None:
    """首次启动把内置模板写成 JSON 文件；已存在的同名文件不覆盖。"""
    d = prompts_dir()
    for tpl in DEFAULT_TEMPLATES:
        path = os.path.join(d, f"{tpl['id']}.json")
        if not os.path.exists(path):
            with open(path, "w", encoding="utf-8") as f:
                json.dump(tpl, f, ensure_ascii=False, indent=2)


def load_templates() -> dict[str, dict]:
    """加载全部模板，返回 {id: {id,name,system}}。以磁盘文件为准。"""
    d = prompts_dir()
    out: dict[str, dict] = {}
    if os.path.isdir(d):
        for fn in os.listdir(d):
            if not fn.endswith(".json"):
                continue
            try:
                with open(os.path.join(d, fn), encoding="utf-8") as f:
                    tpl = json.load(f)
                if tpl.get("id") and tpl.get("name") and tpl.get("system"):
                    out[tpl["id"]] = tpl
            except (json.JSONDecodeError, OSError):
                continue
    # 磁盘一个都没有（被用户清空）时，退回内置，保证软件可用
    if not out:
        for tpl in DEFAULT_TEMPLATES:
            out[tpl["id"]] = tpl
    return out


def get_template(tid: str | None, templates: dict[str, dict]) -> dict:
    if tid and tid in templates:
        return templates[tid]
    return templates.get("free") or next(iter(templates.values()))
