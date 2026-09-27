# WenMo (文墨) — Technical Documentation

> Version: v1.2 · 2026-09-27
> Reflects the implemented state of the app (desktop build + four-stage creative pipeline).
> Chinese project planning docs: `技术文档.md`, `开发计划.md` (both in Chinese).

---

## 1. Overview

WenMo is a local-first AI writing assistant for **Windows desktop only**, built around a chat interface. Core capabilities:

1. **Persistent chat history** — every session and message is stored in a local SQLite database; nothing is lost on restart.
2. **Browsable, searchable history** — session list, message history, global full-text search, export to Markdown / plain text.
3. **Bring-your-own-key LLM access** — the user provides an API key, base URL and model name; streaming output throughout.
4. **Four-stage creative pipeline** — outline planning → worldbuilding → detailed outline → final draft (optional, on by default).
5. **Single-file exe** — packaged with PyInstaller, double-click to run.

Positioning: not a general chatbot but a **writing assistant** — the system prompt is composed from writing-oriented templates (outline / continuation / polish / naming / worldbuilding / style mimicry).

## 2. Tech Stack

| Purpose | Choice | Notes |
|---|---|---|
| Runtime | **Python 3.12+** (dev machine: 3.13) | Project-local venv, no global pollution |
| Desktop UI | **PySide6** (official Qt 6 bindings) | Chat UI, dark QSS theme, long lists |
| HTTP / SSE streaming | **httpx** | Token-by-token rendering |
| Local database | **sqlite3** (stdlib) | Single-file DB, zero extra dependencies |
| Secret storage | **keyring** | Windows Credential Manager (DPAPI), never plain text |
| Markdown rendering | **markdown** + QTextBrowser | Model output is typically Markdown |
| Packaging | **PyInstaller** | `--onefile --noconsole` single exe |

Rejected alternatives: Tkinter (crude widgets), Flet (still ships a Flutter runtime — contradicts dropping Flutter), Electron (not Python).

## 3. Architecture

```
┌──────────────────────────────────────────────────────┐
│                 UI layer (PySide6)                   │
│  session sidebar │ chat column │ history │ settings  │
│  MessageBubble / stage blocks / action bar           │
└────────────────────┬─────────────────────────────────┘
                     │ Qt signal/slot across QThread
┌────────────────────▼─────────────────────────────────┐
│                Business logic                        │
│  MainWindow chat controller (worker lifecycle)       │
│  LLMWorker      — single-shot streaming generation   │
│  PipelineWorker — four-stage creative pipeline       │
├───────────────┬──────────────────┬───────────────────┤
│  LLM access   │  Persistence     │  Templates        │
│  llm.py       │  db.py (sqlite3) │  prompts_store.py │
│  httpx SSE    │  wenmo.db        │  %APPDATA%/文墨/  │
└───────┬───────┴──────────────────┴───────────────────┘
        │ HTTPS (user-configured base URL + key)
┌───────▼────────┐
│  LLM provider  │  DeepSeek / Zhipu / Kimi / Qwen / any
└────────────────┘  OpenAI-compatible endpoint
```

**Principles:** the API key only ever goes into the Windows Credential Manager — never a plain-text file, never a log, never an export. All network I/O runs on background threads; the UI never blocks. Messages are written to the database only when a stream reaches a terminal state (`done` / `stopped` / `error`), so an interruption never loses generated text.

## 4. Data Model (SQLite, `%APPDATA%\文墨\wenmo.db`)

```sql
CREATE TABLE sessions (
  id          TEXT PRIMARY KEY,        -- uuid4
  title       TEXT NOT NULL,           -- first 20 chars of the first user message; renamable
  preset_id   TEXT,                    -- writing template id, nullable
  created_at  REAL NOT NULL,           -- unix timestamps
  updated_at  REAL NOT NULL
);

CREATE TABLE messages (
  id          TEXT PRIMARY KEY,
  session_id  TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
  role        TEXT NOT NULL,           -- 'user' | 'assistant' | 'system'
  content     TEXT NOT NULL,           -- final visible text
  reasoning   TEXT,                    -- chain-of-thought and/or 【阶段N·name】 pipeline blocks
  model       TEXT,                    -- model that produced the reply
  status      TEXT DEFAULT 'done',     -- 'streaming' | 'done' | 'error' | 'stopped'
  created_at  REAL NOT NULL
);
CREATE INDEX idx_messages_session ON messages(session_id, created_at);

CREATE TABLE settings (                -- non-sensitive config only; the key lives in keyring
  key   TEXT PRIMARY KEY,              -- 'base_url' | 'model' | 'temperature' | 'max_rounds' | 'pipeline' | ...
  value TEXT NOT NULL
);
```

## 5. LLM Access Layer

### 5.1 Protocol

OpenAI-compatible `POST {base_url}/chat/completions`, `Authorization: Bearer <API key>`, `"stream": true`. DeepSeek, Zhipu GLM, Kimi and Qwen all speak this protocol — **switching providers = changing three settings**.

### 5.2 Streaming

- `httpx.Client.stream()` parses `data: {...}` lines; `choices[0].delta.content` and `delta.reasoning_content` are forwarded to the UI through Qt signals, token by token.
- `data: [DONE]` ends the stream; the stop button closes the response and persists partial output with status `stopped`.
- Timeouts: 180 s read / 15 s connect. Network / 401 / timeout errors mark the message `error` without discarding what was already generated.

### 5.3 Creative Pipeline (`core/pipeline.py`)

`PipelineWorker` (QThread) runs four sequential streaming requests:

| Stage | Job | Prompt scope |
|---|---|---|
| ① 规划大纲 Outline planning | Structure skeleton for the request, grounded in conversation context | template system prompt + stage instructions |
| ② 补充设定 Worldbuilding | Characters, motivations, timeline, style, logic-gap repair | ① output prepended as context |
| ③ 细化大纲 Detailed outline | Section-by-section execution plan with pacing and length budget | ① + ② prepended |
| ④ 生成文本 Draft | Final text; the only content treated as the actual reply | strict "follow the outline, no commentary" |

- Stages ①–③ emit `stage_started / stage_token / stage_done` signals rendered as collapsible blocks; stage ④ streams through the normal token channel into the message body.
- On completion the stage outputs are serialized into `messages.reasoning` as `【阶段N·name】` blocks, so the whole creative process survives restarts.
- A per-message toggle (`settings.pipeline`, default on) switches between pipeline mode and single-shot mode; stop and error handling work identically in both.

### 5.4 Template System

Built-ins: free chat / outline generation / continuation / polish / naming / worldbuilding / style mimicry. Each template is a JSON file (`id`, `name`, `system`) in `%APPDATA%\文墨\prompts\`; users can add their own and pick one when creating a session. The chosen template's system prompt is injected into every request in that session.

## 6. UI Layer

- **Chat page** — DeepSeek-style layout: centered 820 px reading column, avatar-driven identity (no role text labels), user messages as right-aligned rounded bubbles, assistant messages as full-width body text under a circular avatar.
- **Collapsible blocks** — one generic widget powers both "deep thinking" and pipeline stage blocks: auto-expanded while streaming, auto-collapsed when done, click to toggle.
- **Action bar** — per-message copy / regenerate / delete (context menus retained).
- **Input panel** — borderless editor inside a rounded panel; a single circular action button toggles send (blue ↑) / stop (red ■).
- **History page** — global message search with jump-to-session; per-session Markdown / TXT export.
- **Settings** — base URL, API key (password field + test connection), model, provider presets, temperature, context rounds, pipeline toggle. First launch without a key shows a hint instead of failing.
- **Startup** — auto-opens the most recent session; empty state shows a welcome hint. A global `sys.excepthook` writes `%APPDATA%\文墨\crash.log` (needed because the exe is built `--noconsole`).

## 7. Packaging (Windows)

```powershell
pyinstaller --onefile --noconsole --name 文墨 --hidden-import keyring.backends.Windows main.py
```

- Output `app/dist/文墨.exe`, ~50 MB (normal for PySide6).
- App data goes to `%APPDATA%\文墨\` (`wenmo.db`, `prompts/*.json`, `exports/`, `crash.log`), fully separate from the exe.
- Optional: Inno Setup wrapper for an installer; the single exe is distributable as-is.

## 8. Testing

- `tests/smoke_test.py` — 7 sections: DB round-trips & cascade delete, template loading, settings/keyring, real-API streaming, four-stage pipeline, export. Real-API sections auto-skip when no key is configured.
- `tests/ui_preview.py` — offline visual acceptance: injects fake messages, screenshots the window, asserts layout metrics (column width, body width, stage-block collapse state).

## 9. Risks & Mitigations

| Risk | Mitigation |
|---|---|
| SSE parsing differences across providers | single parser in `llm.py` + non-stream fallback path |
| Antivirus false positives on PyInstaller exes | distribute as portable exe; add version info/icon resources if needed |
| PySide6 bundle size | trim unused Qt modules with `--exclude-module` |
| Non-ASCII paths | data lives in `%APPDATA%\文墨\`, separate from the exe |
| Long sessions exceeding context | max-rounds setting; oldest rounds truncated automatically |
| Provider latency spikes (e.g. stage ④ slow) | 180 s read timeout per request; terminal-state-only persistence keeps partial output |
