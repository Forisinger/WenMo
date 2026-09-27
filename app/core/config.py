"""文墨 - 全局配置：数据目录、默认项、服务商预设。

应用数据（db / prompts / 导出）统一放 %APPDATA%/文墨/，与 exe 分离，升级不丢数据。
"""
import os

APP_NAME = "文墨"

# 首次启动预置的 API Key。开源发布不内置任何密钥：
# 留空 = 启动后到「设置」里填写自己的 Key（存 Windows 凭据管理器）。
DEFAULT_API_KEY = ""

# 默认配置（settings 表缺失时使用）
DEFAULTS = {
    "base_url": "https://api.deepseek.com/v1",
    "model": "deepseek-flash",       # DeepSeek v4.1 flash 档（2026-09 实测可用模型名）
    "temperature": "0.8",
    "max_rounds": "20",              # 上下文最大轮数（一轮 = 用户+助手各一条）
    "pipeline": "1",                 # 四阶段创作流水线开关（1=开）
}

# 服务商预设：选服务商自动填 BaseURL + 模型名
PROVIDER_PRESETS = [
    {"name": "DeepSeek",      "base_url": "https://api.deepseek.com/v1",                          "model": "deepseek-flash"},
    {"name": "DeepSeek(Pro)", "base_url": "https://api.deepseek.com/v1",                          "model": "deepseek-v4-pro"},
    {"name": "智谱 GLM",      "base_url": "https://open.bigmodel.cn/api/paas/v4",                 "model": "glm-4-flash"},
    {"name": "Kimi",          "base_url": "https://api.moonshot.cn/v1",                           "model": "moonshot-v1-8k"},
    {"name": "通义千问",       "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",    "model": "qwen-plus"},
    {"name": "自定义",         "base_url": "",                                                     "model": ""},
]


def data_dir() -> str:
    """应用数据目录：%APPDATA%/文墨/（无 APPDATA 时退回用户主目录）。"""
    base = os.environ.get("APPDATA") or os.path.expanduser("~")
    d = os.path.join(base, APP_NAME)
    os.makedirs(d, exist_ok=True)
    return d


def db_path() -> str:
    return os.path.join(data_dir(), "wenmo.db")


def prompts_dir() -> str:
    d = os.path.join(data_dir(), "prompts")
    os.makedirs(d, exist_ok=True)
    return d


def exports_dir() -> str:
    d = os.path.join(data_dir(), "exports")
    os.makedirs(d, exist_ok=True)
    return d
