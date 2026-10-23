"""DeepSeek provider：直连 api.deepseek.com，不再依赖本机 Flask / 8890。

设计约束（docs/14-product-roadmap.md 阶段 A2）：
- key 只从环境变量读（DEEPSEEK_AUTH_TOKEN / DEEPSEEK_API_KEY），绝不落盘、不写日志；
- OpenAI 兼容 /chat/completions + SSE 流式，面板能逐字增长；
- 会话上下文由本 provider 记住最近若干轮（set_context 由 runtime 在发送前注入），
  不依赖后端会话；本地 history.json 仍是消息真源。
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request
from collections import deque
from collections.abc import Callable, Iterator

from mascot_core.contract import HealthState, Message, ProviderHealth

DEFAULT_BASE_URL = "https://api.deepseek.com"
DEFAULT_MODEL = "deepseek-chat"
CONTEXT_TURNS = 20
_KEY_VARS = ("DEEPSEEK_AUTH_TOKEN", "DEEPSEEK_API_KEY", "MASCOT_DEEPSEEK_API_KEY")


class DeepSeekProvider:
    name = "deepseek"

    def __init__(
        self,
        base_url: str = "",
        model: str = DEFAULT_MODEL,
        timeout_s: float = 60.0,
        health_timeout_s: float | None = None,
    ) -> None:
        base = (base_url or "").strip().rstrip("/")
        # 用户把 .bashrc 的 DEEPSEEK_BASE_URL 指到 /anthropic 时也能用：只认域名，路径固定走 OpenAI 兼容端点
        if base.endswith("/anthropic"):
            base = base[: -len("/anthropic")]
        self.base_url = base or DEFAULT_BASE_URL
        self.model = model or DEFAULT_MODEL
        self.timeout_s = timeout_s
        self.health_timeout_s = health_timeout_s if health_timeout_s is not None else 3.0
        self._convo: deque[dict[str, str]] = deque(maxlen=CONTEXT_TURNS * 2)

    # ---- key ---------------------------------------------------------

    @staticmethod
    def _key() -> str:
        for name in _KEY_VARS:
            value = os.environ.get(name, "").strip()
            if value:
                return value
        # 从开始菜单/桌面快捷方式启动时，进程可能仍带着 Explorer 的旧 env 块
        # （setx 写入用户变量后 Explorer 不一定已刷新），所以再读一次用户环境变量注册表。
        # 只读取，不复制、不写文件、不进日志。
        if sys.platform == "win32":
            try:
                import winreg

                with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as key_handle:
                    for name in _KEY_VARS:
                        try:
                            value, _ = winreg.QueryValueEx(key_handle, name)
                        except FileNotFoundError:
                            continue
                        if str(value).strip():
                            return str(value).strip()
            except OSError:
                pass
        return ""

    def _headers(self) -> dict[str, str]:
        key = self._key()
        if not key:
            raise RuntimeError("缺少 DeepSeek key：请设置 DEEPSEEK_AUTH_TOKEN 环境变量（不写进配置文件）")
        return {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}

    # ---- 上下文 ------------------------------------------------------

    def set_context(self, messages: list[Message]) -> None:
        """用面板当前时间线重建上下文（只取最近 CONTEXT_TURNS 轮，assistant 空文本跳过）。"""
        convo: list[dict[str, str]] = []
        for m in messages[-CONTEXT_TURNS * 2 :]:
            if m.role in ("user", "assistant") and m.text.strip():
                convo.append({"role": m.role, "content": m.text})
        self._convo = deque(convo, maxlen=CONTEXT_TURNS * 2)

    # ---- 健康 --------------------------------------------------------

    def health(self) -> ProviderHealth:
        if not self._key():
            return ProviderHealth(
                state=HealthState.DOWN,
                detail="未设置 DEEPSEEK_AUTH_TOKEN（key 只从环境变量读）",
                reason_code="NO_API_KEY",
            )
        started = time.monotonic()
        try:
            req = urllib.request.Request(
                f"{self.base_url}/models",
                headers={"Authorization": self._headers()["Authorization"]},
            )
            with urllib.request.urlopen(req, timeout=self.health_timeout_s) as resp:  # noqa: S310
                resp.read(1)
            ms = int((time.monotonic() - started) * 1000)
            return ProviderHealth(state=HealthState.UP, latency_ms=ms)
        except urllib.error.HTTPError as exc:
            code = "AUTH_REJECTED" if exc.code in (401, 403) else "PROVIDER_HTTP"
            return ProviderHealth(
                state=HealthState.DOWN, detail=f"HTTP {exc.code}", reason_code=code
            )
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            return ProviderHealth(
                state=HealthState.DOWN, detail=str(exc), reason_code="PROVIDER_UNREACHABLE"
            )

    def history(self, limit: int = 50) -> list[Message]:
        """本地 history.json 才是消息真源；这里返回空，避免与本地记录重复。"""
        return []

    # ---- 发送 --------------------------------------------------------

    def send(self, text: str) -> Message:
        return self.send_stream(text, lambda _delta: None)

    def send_stream(self, text: str, on_delta: Callable[[str], None]) -> Message:
        payload = {
            "model": self.model,
            "messages": [*self._convo, {"role": "user", "content": text}],
            "stream": True,
        }
        req = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers=self._headers(),
            method="POST",
        )
        chunks: list[str] = []
        with urllib.request.urlopen(req, timeout=self.timeout_s) as resp:  # noqa: S310
            for raw in _iter_lines(resp):
                line = raw.decode("utf-8", "replace").strip()
                if not line or not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if data == "[DONE]":
                    break
                try:
                    obj = json.loads(data)
                except json.JSONDecodeError:
                    continue
                choices = obj.get("choices") or []
                if not choices:
                    continue
                delta = choices[0].get("delta") or {}
                piece = delta.get("content") or ""
                if piece:
                    chunks.append(piece)
                    on_delta(piece)
        reply = "".join(chunks).strip()
        if not reply:
            raise RuntimeError("DeepSeek 返回空回复")
        self._convo.append({"role": "user", "content": text})
        self._convo.append({"role": "assistant", "content": reply})
        return Message(
            role="assistant",
            text=reply,
            ts=time.time(),
            msg_id=f"ds-{int(time.time() * 1000)}",
        )

    def complete(self, system: str, user: str) -> str:
        """一次性补全（非流式）：给「总结选中消息」用，不污染会话上下文。"""
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "stream": False,
            "temperature": 0.3,
            "max_tokens": 900,
        }
        req = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers=self._headers(),
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=self.timeout_s) as resp:  # noqa: S310
            obj = json.loads(resp.read().decode("utf-8", "replace"))
        choices = obj.get("choices") or []
        if not choices:
            raise RuntimeError("DeepSeek 返回空补全")
        content = str((choices[0].get("message") or {}).get("content") or "").strip()
        if not content:
            raise RuntimeError("DeepSeek 返回空摘要")
        return content

    def stop(self) -> None:
        return None


def _iter_lines(resp: object) -> Iterator[bytes]:
    """urllib 的 HTTPResponse 逐行迭代（SSE 行以 \n 分隔，兼容 \r\n）。"""
    yield from resp  # type: ignore[attr-defined]
