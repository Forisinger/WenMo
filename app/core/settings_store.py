"""文墨 - 配置存取：非敏感项走 settings 表，API Key 走 Windows 凭据管理器（keyring）。

keyring 不可用时降级存 settings 表（保证软件始终可用），并在 get 时回读。
首次启动把预置 Key 写入凭据管理器。
"""
from core import db
from core.config import DEFAULTS

_KEYRING_SERVICE = "文墨"
_KEYRING_ACCOUNT = "api_key"
_FALLBACK_KEY = "api_key_fallback"   # settings 表里的降级键名


def _keyring_ok() -> bool:
    try:
        import keyring  # noqa
        return keyring.get_keyring() is not None
    except Exception:
        return False


def get_api_key() -> str:
    if _keyring_ok():
        try:
            import keyring
            v = keyring.get_password(_KEYRING_SERVICE, _KEYRING_ACCOUNT)
            if v:
                return v
        except Exception:
            pass
    return db.get_setting(_FALLBACK_KEY, "") or ""


def set_api_key(value: str) -> bool:
    """返回 True 表示已存入凭据管理器；False 表示降级存了本地 settings 表。"""
    if _keyring_ok():
        try:
            import keyring
            keyring.set_password(_KEYRING_SERVICE, _KEYRING_ACCOUNT, value)
            db.set_setting(_FALLBACK_KEY, "")  # 清降级键
            return True
        except Exception:
            pass
    db.set_setting(_FALLBACK_KEY, value)
    return False


def get(key: str) -> str:
    v = db.get_setting(key)
    if v is None or v == "":
        return DEFAULTS.get(key, "")
    return v


def set(key: str, value: str) -> None:
    db.set_setting(key, value)


def all_config() -> dict:
    return {
        "base_url": get("base_url"),
        "model": get("model"),
        "temperature": get("temperature"),
        "max_rounds": get("max_rounds"),
        "api_key": get_api_key(),
        "key_in_keyring": _keyring_ok(),
    }


def seed_first_run() -> None:
    """首次启动：落地默认配置项。Key 不内置，由用户在设置页填写。"""
    db.init_db()
    for k, v in DEFAULTS.items():
        if db.get_setting(k) is None:
            db.set_setting(k, v)
