"""文墨 - SQLite 持久化层。

三张表：sessions / messages / settings（技术文档第 4 节）。
在 messages 表上额外加了 reasoning 列，用于保存 DeepSeek 思维链模型的思考内容。
"""
import os
import sqlite3
import time
import uuid

from core.config import db_path

_CONN: sqlite3.Connection | None = None


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(db_path())
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db() -> None:
    global _CONN
    if _CONN is None:
        _CONN = _connect()
    _CONN.executescript(
        """
        CREATE TABLE IF NOT EXISTS sessions (
          id          TEXT PRIMARY KEY,
          title       TEXT NOT NULL,
          preset_id   TEXT,
          created_at  REAL NOT NULL,
          updated_at  REAL NOT NULL
        );
        CREATE TABLE IF NOT EXISTS messages (
          id          TEXT PRIMARY KEY,
          session_id  TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
          role        TEXT NOT NULL,
          content     TEXT NOT NULL,
          reasoning   TEXT,
          model       TEXT,
          status      TEXT DEFAULT 'done',
          created_at  REAL NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_messages_session ON messages(session_id, created_at);
        CREATE TABLE IF NOT EXISTS settings (
          key   TEXT PRIMARY KEY,
          value TEXT NOT NULL
        );
        """
    )
    _CONN.commit()


def _c() -> sqlite3.Connection:
    if _CONN is None:
        init_db()
    return _CONN


def _now() -> float:
    return time.time()


# ---------------- sessions ----------------

def create_session(title: str = "新的会话", preset_id: str | None = None) -> str:
    sid = str(uuid.uuid4())
    t = _now()
    _c().execute(
        "INSERT INTO sessions(id,title,preset_id,created_at,updated_at) VALUES(?,?,?,?,?)",
        (sid, title, preset_id, t, t),
    )
    _c().commit()
    return sid


def get_session(sid: str) -> dict | None:
    row = _c().execute("SELECT * FROM sessions WHERE id=?", (sid,)).fetchone()
    return dict(row) if row else None


def list_sessions() -> list[dict]:
    rows = _c().execute(
        "SELECT * FROM sessions ORDER BY updated_at DESC"
    ).fetchall()
    return [dict(r) for r in rows]


def rename_session(sid: str, title: str) -> None:
    _c().execute("UPDATE sessions SET title=?, updated_at=? WHERE id=?", (title, _now(), sid))
    _c().commit()


def touch_session(sid: str) -> None:
    _c().execute("UPDATE sessions SET updated_at=? WHERE id=?", (_now(), sid))
    _c().commit()


def set_session_preset(sid: str, preset_id: str | None) -> None:
    _c().execute("UPDATE sessions SET preset_id=? WHERE id=?", (preset_id, sid))
    _c().commit()


def delete_session(sid: str) -> None:
    _c().execute("DELETE FROM sessions WHERE id=?", (sid,))  # 级联删消息
    _c().commit()


# ---------------- messages ----------------

def add_message(session_id: str, role: str, content: str, model: str | None = None,
                status: str = "done", reasoning: str | None = None) -> str:
    mid = str(uuid.uuid4())
    _c().execute(
        "INSERT INTO messages(id,session_id,role,content,reasoning,model,status,created_at)"
        " VALUES(?,?,?,?,?,?,?,?)",
        (mid, session_id, role, content, reasoning, model, status, _now()),
    )
    _c().commit()
    touch_session(session_id)
    return mid


def get_messages(session_id: str, include_error: bool = True) -> list[dict]:
    if include_error:
        rows = _c().execute(
            "SELECT * FROM messages WHERE session_id=? ORDER BY created_at ASC", (session_id,)
        ).fetchall()
    else:
        rows = _c().execute(
            "SELECT * FROM messages WHERE session_id=? AND status!='error' ORDER BY created_at ASC",
            (session_id,),
        ).fetchall()
    return [dict(r) for r in rows]


def get_message(mid: str) -> dict | None:
    row = _c().execute("SELECT * FROM messages WHERE id=?", (mid,)).fetchone()
    return dict(row) if row else None


def update_message(mid: str, content: str, reasoning: str | None = None,
                   status: str = "done", model: str | None = None) -> None:
    _c().execute(
        "UPDATE messages SET content=?, reasoning=?, status=?, model=? WHERE id=?",
        (content, reasoning, status, model, mid),
    )
    _c().commit()


def delete_message(mid: str) -> None:
    _c().execute("DELETE FROM messages WHERE id=?", (mid,))
    _c().commit()


def delete_message_pair(mid: str) -> list[str]:
    """删除一条助手消息及其触发它的用户消息（回滚上下文记忆）。

    返回实际删除的消息 id 列表。非助手消息只删自身。
    上下文每次生成都从库重建，删行即回滚。
    """
    msg = get_message(mid)
    if msg is None:
        return []
    conn = _c()
    ids = [mid]
    if msg["role"] == "assistant":
        row = conn.execute(
            "SELECT id FROM messages WHERE session_id=? AND role='user' AND created_at<=? "
            "ORDER BY created_at DESC LIMIT 1",
            (msg["session_id"], msg["created_at"]),
        ).fetchone()
        if row:
            ids.append(row["id"])
    conn.execute(
        f"DELETE FROM messages WHERE id IN ({','.join('?' * len(ids))})", ids)
    conn.commit()
    return ids


def search_messages(query: str, limit: int = 200) -> list[dict]:
    """全局搜索消息内容，联出会话标题，按时间倒序。"""
    like = f"%{query}%"
    rows = _c().execute(
        """
        SELECT m.id AS message_id, m.session_id, m.role, m.content, m.created_at, s.title AS session_title
        FROM messages m JOIN sessions s ON s.id = m.session_id
        WHERE m.content LIKE ?
        ORDER BY m.created_at DESC LIMIT ?
        """,
        (like, limit),
    ).fetchall()
    return [dict(r) for r in rows]


# ---------------- settings ----------------

def get_setting(key: str, default: str | None = None) -> str | None:
    row = _c().execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    return row["value"] if row else default


def set_setting(key: str, value: str) -> None:
    _c().execute(
        "INSERT INTO settings(key,value) VALUES(?,?)"
        " ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (key, value),
    )
    _c().commit()
