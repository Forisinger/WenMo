"""文墨 - LLM 接入层：OpenAI 兼容协议 + httpx SSE 流式解析。

stream_request() 为同步流式请求的公共实现，供两类调用方复用：
  - LLMWorker：单次生成（QThread 包装）
  - PipelineWorker：四阶段创作流水线（core/pipeline.py）
"""
import json

import httpx
from PySide6.QtCore import QThread, Signal

_TIMEOUT = httpx.Timeout(180.0, connect=15.0)


def stream_request(base_url: str, api_key: str, model: str,
                   messages: list[dict], temperature: float,
                   on_token=None, on_reasoning=None,
                   stop_check=None, response_holder: dict | None = None):
    """同步执行一次流式对话请求。

    on_token/on_reasoning: 回调 fn(piece)，逐增量触发
    stop_check: 回调 fn() -> bool，为 True 时中止（已生成内容保留）
    response_holder: dict，用于外部在 stop() 时关闭进行中的响应
    返回 (status, content, reasoning, err)：status ∈ done/stopped/error
    """
    url = f"{base_url.rstrip('/')}/chat/completions"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    payload = {"model": model, "messages": messages, "stream": True, "temperature": temperature}

    content_parts: list[str] = []
    reasoning_parts: list[str] = []

    def _finish(status: str, err: str = ""):
        return status, "".join(content_parts), "".join(reasoning_parts), err

    try:
        client = httpx.Client(timeout=_TIMEOUT)
        stream = client.stream("POST", url, json=payload, headers=headers)
        resp = stream.__enter__()
        if response_holder is not None:
            response_holder["resp"] = resp
        try:
            if resp.status_code != 200:
                body = ""
                try:
                    body = resp.read().decode("utf-8", errors="replace")[:500]
                except Exception:
                    pass
                return _finish("error", f"HTTP {resp.status_code}：{body or '服务端返回异常'}")

            for line in resp.iter_lines():
                if stop_check and stop_check():
                    return _finish("stopped")
                if not line or not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if data == "[DONE]":
                    break
                try:
                    obj = json.loads(data)
                except json.JSONDecodeError:
                    continue
                if obj.get("error"):
                    return _finish("error", obj["error"].get("message", "服务端返回错误"))
                choices = obj.get("choices") or []
                if not choices:
                    continue
                delta = choices[0].get("delta") or {}
                r = delta.get("reasoning_content")
                if r:
                    reasoning_parts.append(r)
                    if on_reasoning:
                        on_reasoning(r)
                c = delta.get("content")
                if c:
                    content_parts.append(c)
                    if on_token:
                        on_token(c)
        finally:
            try:
                stream.__exit__(None, None, None)
            except Exception:
                pass
            try:
                client.close()
            except Exception:
                pass
        return _finish("done")
    except httpx.ConnectError:
        return _finish("error", "网络连接失败：请检查网络，或确认接口地址是否正确。")
    except httpx.TimeoutException:
        return _finish("error", "请求超时：服务响应过慢，可稍后重试。")
    except Exception as e:  # 兜底，不让线程静默死掉
        return _finish("error", f"未知错误：{e}")


class LLMWorker(QThread):
    """单次生成：流式跑一条请求（关闭创作流水线时的路径）。"""

    token = Signal(str)
    reasoning = Signal(str)
    finished_sig = Signal(str, str, str)  # status, content, extra

    def __init__(self, base_url: str, api_key: str, model: str,
                 messages: list[dict], temperature: float, parent=None):
        super().__init__(parent)
        self._args = (base_url, api_key, model, messages, temperature)
        self._stop = False
        self._holder: dict = {}

    def stop(self) -> None:
        self._stop = True
        resp = self._holder.get("resp")
        if resp is not None:
            try:
                resp.close()
            except Exception:
                pass

    def run(self) -> None:
        base_url, api_key, model, messages, temperature = self._args
        status, content, reasoning, err = stream_request(
            base_url, api_key, model, messages, temperature,
            on_token=self.token.emit,
            on_reasoning=self.reasoning.emit,
            stop_check=lambda: self._stop,
            response_holder=self._holder,
        )
        if status == "error":
            self.finished_sig.emit("error", content, err)
        else:
            self.finished_sig.emit(status, content, reasoning)


def test_connection(base_url: str, api_key: str, model: str) -> tuple[bool, str]:
    """设置页「测试连接」：非流式发一条极短请求，验证地址+Key+模型名。"""
    url = f"{base_url.rstrip('/')}/chat/completions"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    payload = {"model": model, "messages": [{"role": "user", "content": "hi"}], "max_tokens": 1}
    try:
        r = httpx.post(url, json=payload, headers=headers, timeout=30)
        if r.status_code == 200:
            return True, "连接成功，Key 与模型名均有效。"
        if r.status_code in (401, 403):
            return False, f"HTTP {r.status_code}：Key 无效或无权限。"
        try:
            msg = r.json().get("error", {}).get("message", r.text[:200])
        except Exception:
            msg = r.text[:200]
        return False, f"HTTP {r.status_code}：{msg}"
    except httpx.ConnectError:
        return False, "网络连接失败：请检查网络或接口地址。"
    except httpx.TimeoutException:
        return False, "请求超时。"
    except Exception as e:
        return False, f"未知错误：{e}"
