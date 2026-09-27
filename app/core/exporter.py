"""文墨 - 会话导出：Markdown / 纯文本。"""
import time

from core import db


def _fmt_time(ts: float) -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(ts))


def _role_name(role: str) -> str:
    return {"user": "我", "assistant": "文墨"}.get(role, role)


def build_markdown(session: dict, messages: list[dict]) -> str:
    lines = [f"# {session['title']}", ""]
    lines.append(f"> 导出时间：{_fmt_time(time.time())}  ")
    lines.append(f"> 消息数：{len(messages)}")
    lines.append("")
    lines.append("---")
    lines.append("")
    for m in messages:
        lines.append(f"## {_role_name(m['role'])}")
        lines.append("")
        lines.append(f"*{_fmt_time(m['created_at'])}*")
        lines.append("")
        lines.append(m["content"])
        if m.get("reasoning"):
            lines.append("")
            lines.append("<details><summary>思考过程</summary>")
            lines.append("")
            lines.append(m["reasoning"])
            lines.append("")
            lines.append("</details>")
        lines.append("")
        lines.append("---")
        lines.append("")
    return "\n".join(lines)


def build_text(session: dict, messages: list[dict]) -> str:
    lines = [f"【{session['title']}】", f"导出时间：{_fmt_time(time.time())}", ""]
    for m in messages:
        lines.append(f"—— {_role_name(m['role'])} · {_fmt_time(m['created_at'])} ——")
        lines.append(m["content"])
        if m.get("reasoning"):
            lines.append(f"[思考过程] {m['reasoning']}")
        lines.append("")
    return "\n".join(lines)


def export_session(session_id: str, path: str, fmt: str = "md") -> int:
    """导出指定会话到 path，返回导出的消息条数。fmt: 'md' | 'txt'"""
    session = db.get_session(session_id)
    if not session:
        raise ValueError("会话不存在")
    messages = db.get_messages(session_id)
    content = build_markdown(session, messages) if fmt == "md" else build_text(session, messages)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    return len(messages)
