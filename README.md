# 文墨 — AI 写作助手

「写文 Agent」软件成品，Python + PySide6 单机版（仅 Windows）。
接入 DeepSeek（OpenAI 兼容协议），支持流式输出、思维链展示、对话历史持久化、搜索与导出。

## 快速开始

1. 双击 `app/dist/文墨.exe` 即可使用，无需安装 Python。
2. **首次启动请到「设置」里填写你自己的 API Key**（项目不内置任何密钥；Key 存 Windows 凭据管理器，界面只显示尾 4 位）。
3. 应用数据（数据库 / 模板 / 导出文件）存放在 `%APPDATA%\文墨\`，与 exe 分离，升级不丢数据。

## 功能一览

| 功能 | 说明 |
|---|---|
| 对话 | DeepSeek 风格界面：居中对话列、头像、可折叠「已深度思考」、消息下方操作栏（复制/重新生成/删除）；流式打字机、随时停止（保留已生成内容） |
| 创作流水线 | 默认开启：每次生成按「① 规划大纲 → ② 补充设定 → ③ 细化大纲 → ④ 生成文本」四阶段自主完成，过程可折叠查看；输入面板可一键关闭回到单发快速模式 |
| 会话管理 | 新建 / 重命名 / 删除（级联删消息，二次确认）/ 按最近排序 |
| 历史持久化 | 全部消息落 SQLite（`%APPDATA%\文墨\wenmo.db`），重启不丢 |
| 历史搜索 | 侧栏「历史记录」全局搜索消息内容，双击跳转定位 |
| 导出 | 会话右键 → 导出 Markdown / 纯文本 |
| 写作模板 | 自由对话 / 大纲生成 / 续写 / 润色 / 起名 / 世界观设定 / 文风模仿，共 7 个 |
| Key 安全存储 | API Key 存 Windows 凭据管理器（DPAPI），界面只显示尾 4 位 |
| 换服务商 | 设置页选预设（DeepSeek / 智谱 / Kimi / 通义）自动填地址和模型名，「测试连接」一键验证 |
| 上下文控制 | 可设上下文最大轮数，超限自动截断最早轮次 |

## 写作模板自定义

模板 JSON 在 `%APPDATA%\文墨\prompts\`，每个文件一个模板：

```json
{
  "id": "my-template",
  "name": "我的模板",
  "system": "你是一位……（系统提示词）"
}
```

放进去重启软件即可在「新建会话」里选用。

## 开发者指南

```bash
# 环境（项目内 venv，不污染全局）
cd app
python -m venv venv
venv/Scripts/python -m pip install --index-url https://pypi.org/simple -r requirements.txt

# 冒烟测试（含真实 API 流式验证）
venv/Scripts/python tests/smoke_test.py

# 运行（开发模式）
venv/Scripts/python main.py

# 打包 exe
venv/Scripts/python -m PyInstaller --onefile --noconsole --name 文墨 --hidden-import keyring.backends.Windows main.py
# 产物：app/dist/文墨.exe
```

> 注：本机 pip 全局配置指向的清华镜像解析不到 PySide6，安装依赖时需显式加
> `--index-url https://pypi.org/simple`（已写入 requirements 使用说明）。

## 目录结构

```
app/
├── main.py                  # 入口
├── core/
│   ├── config.py            # 数据目录 / 默认配置 / 服务商预设
│   ├── db.py                # SQLite（sessions/messages/settings）
│   ├── settings_store.py    # 配置存取 + keyring
│   ├── llm.py               # httpx SSE 流式 + QThread
│   ├── exporter.py          # 导出 md/txt
│   └── prompts_store.py     # 写作模板
├── ui/
│   ├── main_window.py       # 主窗口
│   ├── chat_widgets.py      # 消息气泡
│   ├── history_page.py      # 历史搜索页
│   ├── settings_dialog.py   # 设置对话框
│   └── theme.py             # 深色 QSS
└── tests/smoke_test.py      # 冒烟测试
```

## 技术要点

- 默认模型：`deepseek-flash`（DeepSeek v4.1 flash 档，实测支持流式与 `reasoning_content` 思维链）。
- 流式结束（done / stopped / error）时消息才落库，中断不掉已生成内容。
- 思维链内容随消息一并存库（messages.reasoning 列），重启后气泡里仍能看到。
