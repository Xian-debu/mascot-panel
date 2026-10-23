"""运行时：把状态机、追踪器、面板与球接成一个真的进程。

线程模型（M1 实测结论，D-15）：
    主线程      pywebview 消息循环（面板 = WebView2，必须由它驱动）
    工作线程    状态机 + 追踪 + 自绘球窗口 + 球自己的消息泵
    交叉点      只有 queue.Queue（工作线程 -> UI 由 JS 侧轮询 api.snapshot() 拿）
"""

from __future__ import annotations

import base64
import contextlib
import json
import logging
import math
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import webbrowser
from dataclasses import dataclass
from functools import lru_cache
from importlib import resources
from pathlib import Path
from typing import Any

from mascot_app import boot
from mascot_core import sessions as msgops
from mascot_core.click import DOUBLE, SINGLE, ClickGate
from mascot_core.config import Settings, load_settings, merge_hot
from mascot_core.contract import ChatProvider, Message, SendCancelled
from mascot_core.geometry import Rect, Screen, angle_for_time, follow_rect, orbit_layout
from mascot_core.history import filter_cleared, merge_history, parse_history
from mascot_core.paths import state_dir
from mascot_core.sessions import SessionStore, dump_store, from_history, parse_store
from mascot_core.state import (
    CLEAR_DEGRADED,
    HIDE_BALL,
    HIDE_PANEL,
    MARK_DEGRADED,
    SHOW_BALL,
    SHOW_PANEL,
    START_FRAMES,
    STOP_FRAMES,
    Event,
    Machine,
    State,
    Transition,
)
from mascot_core.tokens import css_variables

log = logging.getLogger(__name__)

PANEL_TITLE = "mascot-panel"
BALL_SIZE = 128
ALERT_S = 2.5  # 新消息提示环亮多久（秒，M30）


def _state_dir() -> Path:
    return state_dir()


def _flags_path() -> Path:
    return _state_dir() / "runtime.json"


def _read_runtime() -> dict[str, Any]:
    """读 runtime.json（上次运行状态）。文件坏了就当空的，绝不因此启动失败。"""
    try:
        raw = json.loads(_flags_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return raw if isinstance(raw, dict) else {}


def _write_runtime(data: dict[str, Any]) -> None:
    """原子写回 runtime.json；失败只记日志（写不了不应该影响桌宠本体）。"""
    path = _flags_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False) + chr(10), encoding="utf-8")
        tmp.replace(path)
    except OSError as exc:
        log.warning("flags: 写入失败 %s: %s", path, exc)


CLEARED_IDS_KEY = "cleared_history_ids"
MAX_CLEARED_IDS = 200


def load_cleared_ids() -> set[str]:
    """用户清空过的消息 id：后端 history 还回来的旧消息按它过滤掉。"""
    value = _read_runtime().get(CLEARED_IDS_KEY)
    if not isinstance(value, list):
        return set()
    return {str(item) for item in value if isinstance(item, str) and item}


def save_cleared_ids(ids: set[str]) -> None:
    raw = _read_runtime()
    if ids:
        raw[CLEARED_IDS_KEY] = sorted(ids)[-MAX_CLEARED_IDS:]
    else:
        raw.pop(CLEARED_IDS_KEY, None)
    _write_runtime(raw)


def load_flags() -> dict[str, bool]:
    """读上次退出时的开关（免打扰/暂停）。"""
    raw = _read_runtime()
    flags: dict[str, bool] = {}
    for key in ("dnd", "paused"):
        value = raw.get(key)
        if isinstance(value, bool):
            flags[key] = value
    return flags


def load_ball_pos() -> tuple[int, int] | None:
    """上次拖到的待机球位置；坏数据当没有。"""
    value = _read_runtime().get("ball_pos")
    if isinstance(value, list) and len(value) == 2 and all(isinstance(v, int) for v in value):
        return int(value[0]), int(value[1])
    return None


def save_ball_pos(pos: tuple[int, int] | None) -> None:
    """记住/清除待机球位置；None 表示回到默认的右下角。"""
    raw = _read_runtime()
    if pos is None:
        raw.pop("ball_pos", None)
    else:
        raw["ball_pos"] = [int(pos[0]), int(pos[1])]
    _write_runtime(raw)


def _load_pos(key: str) -> tuple[int, int] | None:
    value = _read_runtime().get(key)
    if isinstance(value, list) and len(value) == 2 and all(isinstance(v, int) for v in value):
        return int(value[0]), int(value[1])
    return None


def _save_pos(key: str, pos: tuple[int, int] | None) -> None:
    raw = _read_runtime()
    if pos is None:
        raw.pop(key, None)
    else:
        raw[key] = [int(pos[0]), int(pos[1])]
    _write_runtime(raw)


def load_panel_pos() -> tuple[int, int] | None:
    """用户自己拖到的面板位置；有值就不再自动跟随/贴角。"""
    return _load_pos("panel_pos")


def load_panel_offset() -> tuple[int, int] | None:
    """用户拖动时记下的「面板相对宠物窗口」偏移（M27）。"""
    return _load_pos("panel_offset")


def save_panel_offset(offset: tuple[int, int] | None) -> None:
    _save_pos("panel_offset", offset)


def save_panel_pos(pos: tuple[int, int] | None) -> None:
    """记住/清除面板位置；None 表示回到默认（待机右下角 / 跟随宠物）。"""
    _save_pos("panel_pos", pos)


def save_flags(*, dnd: bool, paused: bool) -> None:
    """写回开关，保留同一文件里的其它键（如 ball_pos）。"""
    raw = _read_runtime()
    raw["dnd"] = dnd
    raw["paused"] = paused
    _write_runtime(raw)


def _sessions_path() -> Path:
    return _state_dir() / "sessions.json"


def _history_path() -> Path:
    """旧版单会话文件：只读，一次性迁移到 sessions.json。"""
    return _state_dir() / "history.json"


def _draft_path() -> Path:
    """输入框草稿：WebView 的 localStorage 在 about:blank 源下不持久，只能落盘到状态目录。"""
    return _state_dir() / "draft.txt"


MAX_DRAFT = 4000


def load_draft() -> str:
    try:
        return _draft_path().read_text(encoding="utf-8")[:MAX_DRAFT]
    except OSError:
        return ""


def save_draft(text: str) -> None:
    body = str(text or "")[:MAX_DRAFT]
    path = _draft_path()
    try:
        if not body.strip():
            with contextlib.suppress(OSError):
                path.unlink(missing_ok=True)
            return
        tmp = path.with_suffix(".txt.tmp")
        tmp.write_text(body, encoding="utf-8")
        tmp.replace(path)
    except OSError as exc:
        log.warning("draft: 写入失败 %s: %s", path, exc)

# ---- 导出（C2） ---------------------------------------------------------

EXPORT_DIRNAME = "exports"


def _export_dir() -> Path:
    return _state_dir() / EXPORT_DIRNAME


def _slug(title: str) -> str:
    body = "".join(ch for ch in (title or "") if ch not in '\\/:*?"<>|').strip()
    return (body or "会话")[:30]


def session_markdown(session: msgops.Session, exported_at: float) -> str:
    """把会话导成 Markdown：标题 + 导出时间 + 每条消息（角色小标题）。"""
    stamp = time.strftime("%Y-%m-%d %H:%M", time.localtime(exported_at))
    lines = [f"# {session.title or msgops.DEFAULT_TITLE}", "", f"> 导出时间：{stamp}", ""]
    for msg in session.messages:
        who = "我" if msg.role == "user" else "天选姬"
        lines.append(f"### {who}")
        lines.append("")
        lines.append(msg.text or "")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def reveal_path(path: Path) -> None:
    """在资源管理器里选中导出文件（非 Windows 就打开所在目录）。"""
    try:
        if sys.platform == "win32":
            subprocess.Popen(["explorer", "/select,", str(path)])  # noqa: S603,S607
        else:
            webbrowser.open(str(path.parent))
    except OSError as exc:
        log.warning("export: 打开目录失败 %s: %s", path, exc)



def load_legacy_history() -> list[Message]:
    """旧版 history.json 里的对话；文件坏了当空，绝不因此启动失败。"""
    try:
        raw = _history_path().read_text(encoding="utf-8")
    except OSError:
        return []
    return parse_history(raw)


def load_session_store(now: float) -> SessionStore:
    """会话数据来源：sessions.json > （缺失/坏掉时）迁移旧 history.json > 空白会话。

    迁移是单向的：sessions.json 一旦存在就是唯一真源，history.json 不再参与，
    否则"用户清空的旧消息"会因为旧文件还在而重新复活。
    """
    try:
        raw = _sessions_path().read_text(encoding="utf-8")
    except OSError:
        raw = ""
    if raw.strip():
        try:
            json.loads(raw)
        except ValueError:
            log.warning("sessions: 文件损坏，改从 history.json 迁移")
        else:
            return parse_store(raw, now)
    legacy = load_legacy_history()
    if legacy:
        log.info("sessions: 从 history.json 迁移 %d 条消息", len(legacy))
        return from_history(legacy, now)
    return parse_store("", now)


def _rotate_session_backups(path: Path) -> None:
    """sessions.json → .bak → .bak1 → .bak2，最多留三份上一版。"""
    chain = [
        path.with_suffix(".json.bak"),
        path.with_suffix(".json.bak1"),
        path.with_suffix(".json.bak2"),
    ]
    with contextlib.suppress(OSError):
        for older, newer in reversed(list(zip(chain[1:], chain, strict=False))):
            if newer.exists():
                older.unlink(missing_ok=True)
                shutil.copy2(newer, older)
        chain[0].unlink(missing_ok=True)
        shutil.copy2(path, chain[0])


def save_session_store(store: SessionStore) -> None:
    """原子写盘，失败只记日志（聊天记录写不了也不该影响桌宠本体）。"""
    path = _sessions_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists() and path.stat().st_size > 2:
            # 上一版留三份（.bak/.bak1/.bak2）：一次坏写（比如空会话覆盖）不能把对话全带走
            _rotate_session_backups(path)
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(dump_store(store), encoding="utf-8")
        tmp.replace(path)
    except OSError as exc:
        log.warning("sessions: 写入失败 %s: %s", path, exc)


# ---- 设置（B3）：模型 + key -------------------------------------------

SETTING_MODELS = ("deepseek-chat", "deepseek-reasoner")
KEY_ENV = "DEEPSEEK_AUTH_TOKEN"


def _env_key() -> str:
    """当前进程能否拿到 key（env 或 HKCU\\Environment）。"""
    for name in (KEY_ENV, "DEEPSEEK_API_KEY", "MASCOT_DEEPSEEK_API_KEY"):
        value = os.environ.get(name, "").strip()
        if value:
            return value
    if sys.platform != "win32":
        return ""
    try:
        import winreg

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as handle:
            for name in (KEY_ENV, "DEEPSEEK_API_KEY", "MASCOT_DEEPSEEK_API_KEY"):
                try:
                    value, _ = winreg.QueryValueEx(handle, name)
                except FileNotFoundError:
                    continue
                if str(value).strip():
                    return str(value).strip()
    except OSError:
        pass
    return ""


def set_user_env(name: str, value: str) -> bool:
    """写 Windows 用户级环境变量（等价 setx），并广播 WM_SETTINGCHANGE。

    key 只走环境变量，不写 config.toml、不进日志 —— 和 setx 是同一份真源，
    面板里录入只是替用户省掉开终端敲 setx 的步骤。
    """
    if sys.platform != "win32":
        os.environ[name] = value
        return True
    try:
        import ctypes
        import winreg

        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, "Environment", 0, winreg.KEY_SET_VALUE
        ) as handle:
            winreg.SetValueEx(handle, name, 0, winreg.REG_SZ, value)
    except OSError as exc:
        log.warning("settings: 写用户环境变量失败 %s: %s", name, exc)
        return False
    os.environ[name] = value
    with contextlib.suppress(Exception):  # 广播失败不影响本次进程内生效
        hwnd_broadcast = 0xFFFF
        wm_settingchange = 0x001A
        smto_abortifhung = 0x0002
        result = ctypes.c_ulong()
        ctypes.windll.user32.SendMessageTimeoutW(  # type: ignore[attr-defined]
            hwnd_broadcast,
            wm_settingchange,
            0,
            "Environment",
            smto_abortifhung,
            3000,
            ctypes.byref(result),
        )
    return True


TOKENS_PLACEHOLDER = "/*__TOKENS__*/"
VENDOR_CSS_PLACEHOLDER = "/*__VENDOR_CSS__*/"
CSS_PLACEHOLDER = "/*__CSS__*/"
JS_PLACEHOLDER = "//__JS__"
CSS_MODULES = (
    "base.css",
    "stream.css",
    "markdown.css",
    "messages.css",
    "composer.css",
    "states.css",
    "sessions.css",
    "settings.css",
)
JS_MODULES = (
    "markdown.js",
    "state.js",
    "clock.js",
    "ui.js",
    "chat.js",
    "msgops.js",
    "composer.js",
    "sessions.js",
    "settings.js",
    "main.js",
)


def _pkg_text(rel: str) -> str:
    return resources.files("mascot_app").joinpath(rel).read_text(encoding="utf-8")


def _pkg_bytes(rel: str) -> bytes:
    return resources.files("mascot_app").joinpath(rel).read_bytes()


@lru_cache(maxsize=1)
def katex_css() -> str:
    """KaTeX 样式；字体以内联 data URI 塞进单文件 HTML。

    面板 HTML 是字符串喂给 WebView 的（about:blank），相对路径拿不到字体文件，
    所以只能把 woff2 转 base64；woff（老格式）引用删掉，省一半体积。
    """
    css = _pkg_text("web/vendor/katex/katex.min.css")

    def embed(match: re.Match[str]) -> str:
        name = match.group(1)
        data = base64.b64encode(_pkg_bytes(f"web/vendor/katex/fonts/{name}.woff2")).decode("ascii")
        return f'url(data:font/woff2;base64,{data}) format("woff2")'

    css = re.sub(r'url\(fonts/([A-Za-z0-9_-]+)\.woff2\)\s*format\("woff2"\)', embed, css)
    # woff / ttf 老格式不再随包发，去掉这些兜底 src，省体积也免 404
    return re.sub(r',\s*url\(fonts/[^)]+\)\s*format\("[^"]+"\)', "", css)


def katex_js() -> str:
    return _pkg_text("web/vendor/katex/katex.min.js")


def load_panel_html() -> str:
    """把面板外壳、CSS 模块、JS 模块与设计 token 合成一张自包含 HTML。

    面板拆成多文件开发（好读好改），运行时合成单文件给 WebView（不依赖本地路径）。
    """
    html = _pkg_text("web/panel.html")
    css = "\n".join(_pkg_text(f"web/css/{name}") for name in CSS_MODULES)
    js = "\n".join(_pkg_text(f"web/js/{name}") for name in JS_MODULES)
    return (
        html.replace(TOKENS_PLACEHOLDER, css_variables())
        .replace(VENDOR_CSS_PLACEHOLDER, katex_css())
        .replace(CSS_PLACEHOLDER, css)
        .replace(JS_PLACEHOLDER, katex_js() + "\n" + js)
    )


@dataclass(frozen=True, slots=True)
class PetView:
    x: int
    y: int
    w: int
    h: int
    process: str = ""
    class_name: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "x": self.x,
            "y": self.y,
            "w": self.w,
            "h": self.h,
            "process": self.process,
            "class": self.class_name,
        }


class JsApi:
    """暴露给面板 JS 的窄接口（pywebview 只暴露公共方法）。"""

    def __init__(self, runtime: Runtime) -> None:
        self._rt = runtime

    def snapshot(self) -> dict[str, Any]:
        return self._rt.snapshot()

    def to_ball(self) -> dict[str, Any]:
        return self._rt.to_ball()

    def to_panel(self) -> dict[str, Any]:
        self._rt.post(Event.CLICK_BALL)
        return {"ok": True}

    def open_url(self, url: str) -> dict[str, Any]:
        return self._rt.open_url(url)

    # 设置（B3）：模型 + key。key 只写用户环境变量，不落配置文件
    def get_settings(self) -> dict[str, Any]:
        return self._rt.get_settings()

    def save_settings(self, model: str, key: str) -> dict[str, Any]:
        return self._rt.save_settings(model, key)

    # 草稿（B3）：输入框内容落盘，重启/切会话都不丢
    def draft(self) -> dict[str, Any]:
        return {"ok": True, "text": load_draft()}

    def save_draft(self, text: str) -> dict[str, Any]:
        save_draft(text)
        return {"ok": True}

    def send(self, text: str) -> dict[str, Any]:
        return self._rt.send_text(text)

    def stop(self) -> dict[str, Any]:
        return {"ok": self._rt.cancel_send()}

    # 重试（C3）：上一条失败的用户消息重发一次
    def retry_send(self) -> dict[str, Any]:
        return self._rt.retry_send()

    # 会话抽屉（B1）：新建/切换/重命名/删除后 JS 继续轮询快照拿新列表
    def new_session(self) -> dict[str, Any]:
        return self._rt.new_session()

    def switch_session(self, sid: str) -> dict[str, Any]:
        return self._rt.switch_session(sid)

    def rename_session(self, sid: str, title: str) -> dict[str, Any]:
        return self._rt.rename_session(sid, title)

    def delete_session(self, sid: str) -> dict[str, Any]:
        return self._rt.delete_session(sid)

    # 搜索（C1）：标题或正文命中，返回抽屉行格式
    def search_sessions(self, query: str) -> dict[str, Any]:
        return self._rt.search_sessions(query)

    # 导出（C2）：当前会话导成 Markdown
    def export_session(self, sid: str = "") -> dict[str, Any]:
        return self._rt.export_session(sid)

    # 消息操作（B2）：冻结/折叠/编辑/换版本/上移下移/合并/批量冻结
    def freeze_message(self, msg_id: str) -> dict[str, Any]:
        return self._rt.freeze_message(msg_id)

    def bulk_freeze(self, ids: list[str], frozen: bool) -> dict[str, Any]:
        return self._rt.bulk_freeze(ids, frozen)

    def collapse_message(self, msg_id: str) -> dict[str, Any]:
        return self._rt.collapse_message(msg_id)

    def edit_message(self, msg_id: str, text: str) -> dict[str, Any]:
        return self._rt.edit_message(msg_id, text)

    def switch_version(self, msg_id: str) -> dict[str, Any]:
        return self._rt.switch_version(msg_id)

    def move_message(self, msg_id: str, direction: str) -> dict[str, Any]:
        return self._rt.move_message(msg_id, direction)

    def merge_messages(self, ids: list[str]) -> dict[str, Any]:
        return self._rt.merge_messages(ids)

    def summarize(self, ids: list[str]) -> dict[str, Any]:
        return self._rt.summarize(ids)

    def reorder(self, msg_id: str, index: int) -> dict[str, Any]:
        return self._rt.reorder(msg_id, index)


# 托盘菜单命令 id（只在进程内使用，不进协议）
CMD_TO_PANEL = 1001
CMD_TO_BALL = 1002
CMD_PAUSE = 1003
CMD_AUTOSTART = 1004
CMD_QUIT = 1005
CMD_DND = 1006
CMD_RESET_BALL = 1007
CMD_RESET_PANEL = 1008

_STATE_LABEL = {
    "idle": "待机",
    "idle_open": "待机（面板）",
    "tracking": "跟随中",
    "orbital": "小球",
    "degraded": "降级",
}


def _autostart_enabled() -> bool:
    try:
        from mascot_win import autostart

        return autostart.is_enabled()
    except Exception:
        return False


class Runtime:
    """一个进程一份：面板 + 球 + 状态机。"""

    def __init__(
        self,
        settings: Settings,
        provider: ChatProvider,
        *,
        panel_html: str | None = None,
        config_path: Path | None = None,
        pinned: set[str] | None = None,
    ) -> None:
        self.settings = settings
        # 热重载：记住配置文件路径与上次 mtime/size，循环里每秒比一次
        self._config_path = config_path
        self._config_stamp: tuple[int, int] | None = self._config_mtime()
        self._config_reloads = 0
        self._restart_required: list[str] = []
        # 命令行显式覆盖过的字段（如 --provider null）不算"配置文件里没写"，不报重启；
        # 环境变量 MASCOT_* 同理（env 优先级高于 TOML，文件里的值本来就不生效）
        self._pinned = set(pinned or ()) | {
            name for name in Settings.model_fields if f"MASCOT_{name.upper()}" in os.environ
        }
        self.provider = provider
        self.panel_html = panel_html or load_panel_html()

        self._machine = Machine()
        self._events: list[Event] = []
        self._lock = threading.Lock()
        self._stop = threading.Event()

        self._panel: Any = None
        self._panel_hwnd = 0
        # 状态机是否要求面板可见；pywebview 的 hidden=True 并不保证启动后真的隐藏窗口
        # （实测启动 6s 时 WS_VISIBLE 仍为真），所以 GUI 线程起来后再按这个标志兜一次。
        self._panel_shown = False
        self._panel_recheck = 0.0
        self._ball: Any = None
        self._pet: PetView | None = None
        self._last_panel_rect: Rect | None = None
        self._frames = False
        self._orbit_t0 = 0.0
        self._started = time.monotonic()
        self._reason = "START"
        self._degraded = False
        self._error: str = ""
        self._failed_text: str = ""
        self._failed_msg_id: str = ""
        self._provider_detail: str = ""
        # 先挂上本次运行前落盘的多会话数据，后端历史稍后由 _load_history 合并进当前会话
        self._store = load_session_store(time.time())
        self._sending = False
        self._send_queue: list[str] = []
        self._stream_text = ""
        self._stream_active = False
        # 总结选中消息是一次后台补全：期间禁止切换/重复触发（B2）
        self._summarizing = False
        self._cancel = threading.Event()
        flags = load_flags()
        self._paused = bool(flags.get("paused", False))
        # 环绕球公转可暂停（M29）：暂停时角度冻结，恢复时从同一角度接着转
        self._orbit_paused = False
        self._orbit_frozen_t = 0.0
        # 环绕球当前可见命中圆（屏幕坐标）：验收/排障要能知道球此刻在哪（M29）
        self._ball_circle: tuple[int, int, int] | None = None
        # 待机球位置：用户拖过就记住（宠物不在时也不回角落）
        self._ball_pos: tuple[int, int] | None = load_ball_pos()
        self._alert_until = 0.0  # 新消息提示环的截止时刻（M30，monotonic）
        self._panel_pos: tuple[int, int] | None = load_panel_pos()
        # 跟随态拖出来的面板记偏移（跟着宠物走）；待机态拖出来记绝对位置
        self._panel_offset: tuple[int, int] | None = load_panel_offset()
        self._panel_dirty = False
        # 待机球单击/双击：单击开面板、双击回右下角（靠 350ms 时间窗区分，见 click.py）
        self._click_gate = ClickGate(self.settings.click_window_ms)
        self._cleared_ids: set[str] = load_cleared_ids()
        # 免打扰：不自动弹出面板（仍跟随、仍可手动打开）；跨重启记住
        self._dnd = bool(flags.get("dnd", False))
        self._commands: list[str] = []
        self._tray: Any = None

    @property
    def _messages(self) -> list[Message]:
        """当前会话的消息列表（与 store 持有同一个 list，追加即生效）。"""
        return self._store.current().messages

    # ---- 状态读取（JS 轮询） -------------------------------------------------

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            state = self._machine.state.value
            pet = self._pet
            return {
                "state": state,
                "reason": self._reason,
                "degraded": self._degraded,
                "provider": self.provider.name,
                "pet": pet.to_dict() if pet else None,
                "uptime_s": round(time.monotonic() - self._started, 1),
                "error": self._error,
                "provider_detail": self._provider_detail,
                "retry_available": bool(self._failed_text),
                "sending": self._sending,
                "summarizing": self._summarizing,
                "streaming": {"active": self._stream_active, "text": self._stream_text},
                "paused": self._paused,
                "orbit_paused": self._orbit_paused,
                "ball_circle": list(self._ball_circle) if self._ball_circle else None,
                "alert": self._alert_active(),
                "dnd": self._dnd,
                "autostart": _autostart_enabled(),
                "messages": [m.to_dict() for m in self._messages[-self.settings.history_limit :]],
                # 会话抽屉：只给摘要，不给每个会话的正文（快照不随会话数膨胀）
                "sessions": self._store.summaries(),
                "current_session": self._store.current_id,
                "current_title": self._store.current().title,
                "settings": {
                    "fps": self.settings.fps,
                    "history_limit": self.settings.history_limit,
                    "health_timeout_s": self.settings.health_timeout_s,
                    "poll_interval_ms": self.settings.poll_interval_ms,
                    "orbit_speed": self.settings.orbit_speed,
                    "click_window_ms": self.settings.click_window_ms,
                },
                "config": {
                    "path": str(self._config_path) if self._config_path else None,
                    "reloads": self._config_reloads,
                    "restart_required": self._restart_required,
                },
                "boot": boot.marks(),
            }

    # ---- 事件投递 -----------------------------------------------------------

    def post(self, event: Event) -> None:
        with self._lock:
            self._events.append(event)

    def command(self, name: str) -> None:
        """托盘/ctl 的命令入口：只入队，工作线程执行。"""
        with self._lock:
            self._commands.append(name)

    def to_ball(self) -> dict[str, Any]:
        """面板按钮：把面板收进小球（只在跟随态有效）。"""
        self.post(Event.CLICK_CLOCK)
        return {"ok": True}

    def open_url(self, url: str) -> dict[str, Any]:
        """面板里点 Markdown 链接：交给系统默认浏览器，别让 WebView 自己导航走。"""
        target = str(url or "").strip()
        if not re.match(r"^(https?://|mailto:)", target, re.I):
            return {"ok": False, "reason": "BAD_URL"}
        try:
            webbrowser.open(target, new=2)
        except Exception as exc:  # noqa: BLE001 - 打不开就算了，不影响聊天
            log.warning("open_url 失败 %s: %s", target, exc)
            return {"ok": False, "reason": "OPEN_FAILED"}
        return {"ok": True}

    # ---- 设置（B3）：模型 + key ---------------------------------------------

    def get_settings(self) -> dict[str, Any]:
        model = str(getattr(self.provider, "model", "") or self.settings.provider_model)
        return {
            "ok": True,
            "model": model,
            "models": list(SETTING_MODELS),
            "has_key": bool(_env_key()),
        }

    def save_settings(self, model: str, key: str) -> dict[str, Any]:
        """改模型（写 config.toml，当前 provider 立即生效）与 key（写用户环境变量）。"""
        new_model = str(model or "").strip()
        new_key = str(key or "").strip()
        if new_model and new_model not in SETTING_MODELS:
            return {"ok": False, "reason": "BAD_MODEL"}
        if new_key and len(new_key) < 10:
            return {"ok": False, "reason": "BAD_KEY"}

        if new_model:
            try:
                from mascot_core.configfile import set_config_value

                set_config_value("provider_model", new_model)
            except (OSError, ValueError) as exc:
                log.warning("settings: 写 config.toml 失败 %s", exc)
                return {"ok": False, "reason": "CONFIG_WRITE_FAILED"}
            if hasattr(self.provider, "model"):
                self.provider.model = new_model

        if new_key and not set_user_env(KEY_ENV, new_key):
            return {"ok": False, "reason": "ENV_WRITE_FAILED"}

        if new_key or new_model:
            # 立刻探一次，面板状态灯/在线提示不用等下一轮轮询
            threading.Thread(
                target=self._poll_provider, name="mascot-settings-probe", daemon=True
            ).start()
        return {"ok": True, "model": new_model or None, "has_key": bool(_env_key())}

    # ---- 聊天 ---------------------------------------------------------------

    def send_text(self, text: str) -> dict[str, Any]:
        """JS 发来的消息只入队：真正的网络调用在工作线程里做，别卡住 UI。"""
        clean = (text or "").strip()
        if not clean:
            return {"ok": False, "reason": "EMPTY_TEXT"}
        with self._lock:
            self._send_queue.append(clean[:4000])
            self._cancel.clear()
        return {"ok": True, "queued": True}

    def cancel_send(self) -> bool:
        """面板/ctl 的「停止」：置位取消标志，provider 下一次回调时抛 SendCancelled。"""
        with self._lock:
            active = self._stream_active
            self._cancel.set()
        return active

    def retry_send(self) -> dict[str, Any]:
        """重发上一条失败的用户消息：先把它从会话里摘掉，避免重试后出现两条一样的。"""
        with self._lock:
            text = self._failed_text
            if not text:
                return {"ok": False, "reason": "NOTHING"}
            msg_id = self._failed_msg_id
            idx = msgops.find_index(self._messages, msg_id) if msg_id else None
            if idx is not None:
                del self._messages[idx]
            self._failed_text = ""
            self._failed_msg_id = ""
            self._error = ""
            self._send_queue.append(text)
        self._persist_sessions()
        return {"ok": True}

    def _on_delta(self, piece: str) -> None:
        """provider 每收到一个分片调一次。持锁追加，取消时抛 SendCancelled 中止读取。"""
        with self._lock:
            if self._cancel.is_set():
                raise SendCancelled
            self._stream_text += piece

    def _load_history(self) -> None:
        try:
            history = self.provider.history(limit=self.settings.history_limit)
        except Exception as exc:  # provider 是外部世界，绝不假设它守规矩
            self._provider_detail = str(exc)
            return
        # 用户 clear-history 过的消息：后端 history 还会还回来，按 id 过滤
        history = filter_cleared(history, self._cleared_ids)
        with self._lock:
            local = list(self._messages)
            merged = merge_history(history, local, limit=self.settings.history_limit)
            # 后端还回来的消息常常没 id；补上，否则面板操作找不到它
            for idx, msg in enumerate(merged):
                if not msg.msg_id:
                    msg.msg_id = f"h-{time.time_ns()}-{idx}"
            self._messages[:] = merged
        self._persist_sessions()

    def _persist_sessions(self) -> None:
        limit = self.settings.history_limit
        with self._lock:
            # 内存也别无上限地长：每个会话盘上只留 limit 条，内存同样只留 limit 条
            messages = self._store.current().messages
            if len(messages) > limit:
                messages[:] = messages[-limit:]
            self._store.touch(time.time())
            store = self._store
        save_session_store(store)
        # 顺手刷新 state.json：`ctl status` 才看得到新消息（面板自己走 JS API，不依赖它）
        self._write_state()

    # ---- 会话抽屉（B1） -----------------------------------------------------

    def _chat_busy(self) -> bool:
        """收发中途不许切会话：流式文本和队列都属于当前会话。"""
        return self._sending or self._stream_active or bool(self._send_queue)

    def new_session(self) -> dict[str, Any]:
        with self._lock:
            if self._chat_busy():
                return {"ok": False, "reason": "BUSY"}
            session = self._store.create(time.time())
        self._persist_sessions()
        return {"ok": True, "id": session.sid}

    def switch_session(self, sid: str) -> dict[str, Any]:
        with self._lock:
            if self._chat_busy():
                return {"ok": False, "reason": "BUSY"}
            if not self._store.switch(sid):
                return {"ok": False, "reason": "NOT_FOUND"}
        self._persist_sessions()
        return {"ok": True}

    def rename_session(self, sid: str, title: str) -> dict[str, Any]:
        with self._lock:
            if not self._store.rename(sid, title):
                return {"ok": False, "reason": "INVALID"}
        self._persist_sessions()
        return {"ok": True}

    def delete_session(self, sid: str) -> dict[str, Any]:
        with self._lock:
            if self._chat_busy():
                return {"ok": False, "reason": "BUSY"}
            if self._store.find(sid) is None:
                return {"ok": False, "reason": "NOT_FOUND"}
            self._store.delete(sid, time.time())
        self._persist_sessions()
        return {"ok": True}

    def search_sessions(self, query: str) -> dict[str, Any]:
        """只读搜索：标题或消息正文命中，结果按最近更新排序。"""
        with self._lock:
            return {"ok": True, "results": self._store.search(query)}

    def export_session(self, sid: str = "") -> dict[str, Any]:
        """把会话导成 Markdown 存到 <状态目录>/exports/，并在资源管理器里选中。"""
        with self._lock:
            session = self._store.find(sid) if sid else self._store.current()
            if session is None:
                return {"ok": False, "reason": "NOT_FOUND"}
            if not session.messages:
                return {"ok": False, "reason": "EMPTY"}
            body = session_markdown(session, time.time())
            title = session.title
        directory = _export_dir()
        try:
            directory.mkdir(parents=True, exist_ok=True)
            stamp = time.strftime("%Y%m%d-%H%M%S")
            path = directory / f"{_slug(title)}-{stamp}.md"
            path.write_text(body, encoding="utf-8")
        except OSError as exc:
            log.warning("export: 写入失败 %s", exc)
            return {"ok": False, "reason": "WRITE"}
        reveal_path(path)
        return {"ok": True, "name": path.name, "path": str(path)}

    # ---- 消息操作（B2） -----------------------------------------------------
    # 全部按 msg_id 定位；改完立刻落盘（面板下一次快照就能看到新状态）

    def freeze_message(self, msg_id: str) -> dict[str, Any]:
        with self._lock:
            state = msgops.toggle_freeze(self._messages, msg_id)
        if state is None:
            return {"ok": False, "reason": "NOT_FOUND"}
        self._persist_sessions()
        return {"ok": True, "frozen": state}

    def bulk_freeze(self, ids: list[str], frozen: bool) -> dict[str, Any]:
        with self._lock:
            changed = msgops.bulk_freeze(self._messages, list(ids or []), bool(frozen))
        self._persist_sessions()
        return {"ok": True, "changed": changed}

    def collapse_message(self, msg_id: str) -> dict[str, Any]:
        with self._lock:
            state = msgops.toggle_collapse(self._messages, msg_id)
        if state is None:
            return {"ok": False, "reason": "NOT_FOUND"}
        self._persist_sessions()
        return {"ok": True, "collapsed": state}

    def edit_message(self, msg_id: str, text: str) -> dict[str, Any]:
        with self._lock:
            changed = msgops.edit_message(self._messages, msg_id, text)
        if not changed:
            return {"ok": False, "reason": "NO_CHANGE"}
        self._persist_sessions()
        return {"ok": True}

    def switch_version(self, msg_id: str) -> dict[str, Any]:
        with self._lock:
            changed = msgops.switch_version(self._messages, msg_id)
        if not changed:
            return {"ok": False, "reason": "NO_VERSION"}
        self._persist_sessions()
        return {"ok": True}

    def move_message(self, msg_id: str, direction: str) -> dict[str, Any]:
        with self._lock:
            changed = msgops.move_message(self._messages, msg_id, direction)
        if not changed:
            return {"ok": False, "reason": "NO_MOVE"}
        self._persist_sessions()
        return {"ok": True}

    def reorder(self, msg_id: str, index: int) -> dict[str, Any]:
        """拖动排序：把消息放到第 index 位。"""
        try:
            at = int(index)
        except (TypeError, ValueError):
            return {"ok": False, "reason": "BAD_INDEX"}
        with self._lock:
            changed = msgops.move_to(self._messages, msg_id, at)
        if not changed:
            return {"ok": False, "reason": "NO_MOVE"}
        self._persist_sessions()
        return {"ok": True}

    def merge_messages(self, ids: list[str]) -> dict[str, Any]:
        with self._lock:
            index = msgops.merge_messages(self._messages, list(ids or []))
        if index is None:
            return {"ok": False, "reason": "NEED_TWO"}
        self._persist_sessions()
        return {"ok": True, "index": index}

    SUMMARY_SYSTEM = (
        "你是对话摘要助手。用中文把用户给的消息压缩成一段摘要，"
        "保留关键事实、结论与待办，去掉寒暄和重复。不要加评论，不要用 Markdown 标题。"
    )

    def summarize(self, ids: list[str]) -> dict[str, Any]:
        """把选中消息交给模型总结，再用一条摘要消息替换它们（后台线程跑）。"""
        if self._chat_busy() or self._summarizing:
            return {"ok": False, "reason": "BUSY"}
        wanted = {str(i) for i in (ids or [])}
        with self._lock:
            picked = [m for m in self._messages if m.msg_id in wanted]
        if len(picked) < 2:
            return {"ok": False, "reason": "NEED_TWO"}
        self._summarizing = True
        threading.Thread(
            target=self._summarize_worker, args=(picked,), name="mascot-summary", daemon=True
        ).start()
        return {"ok": True, "queued": True}

    def _summarize_worker(self, picked: list[Message]) -> None:
        try:
            body = "\n\n".join(
                ("我：" if m.role == "user" else "天选姬：") + m.text for m in picked
            )
            text = self._summarize_text(body)
            with self._lock:
                wanted = {m.msg_id for m in picked}
                idxs = [i for i, m in enumerate(self._messages) if m.msg_id in wanted]
                if not idxs:
                    return
                first = min(idxs)
                merged = Message(
                    role="assistant",
                    text=f"**摘要（{len(idxs)} 条）：**\n\n{text}",
                    ts=time.time(),
                    msg_id=f"sum-{time.time_ns()}",
                )
                kept = [m for i, m in enumerate(self._messages) if i not in set(idxs)]
                at = min(first, len(kept))
                kept.insert(at, merged)
                self._messages[:] = kept
            self._error = ""
            self._persist_sessions()
        except Exception as exc:  # noqa: BLE001 - 总结失败不该拖垮面板
            with self._lock:
                self._error = f"总结失败：{exc}"
            log.warning("summarize_failed", extra={"detail": str(exc)})
        finally:
            self._summarizing = False

    def _summarize_text(self, body: str) -> str:
        complete = getattr(self.provider, "complete", None)
        if callable(complete):
            return str(complete(self.SUMMARY_SYSTEM, f"请总结以下对话：\n\n{body}")).strip()
        # 没有模型能力（离线/null provider）时退化为摘录，不让按钮点了没反应
        lines = []
        for line in body.splitlines():
            line = line.strip()
            if line and line not in lines:
                lines.append(line[:120])
        if not lines:
            raise RuntimeError("没有可总结的内容")
        return "（未连接模型，以下为摘录）\n" + "\n".join(lines[:12])

    def clear_history(self) -> None:
        """清空当前会话的对话（下一次写盘即落定），其它会话不受影响。

        后端 history 是另一回事：它会把旧消息再还回来。这里记下被清消息的 id，
        `_load_history` 合并前按 id 过滤，避免「清完重启又复活」。
        """
        with self._lock:
            messages = self._store.current().messages
            cleared = {m.msg_id for m in messages if m.msg_id}
            messages.clear()
        if cleared:
            self._cleared_ids |= cleared
            save_cleared_ids(self._cleared_ids)
        self._persist_sessions()

    def _drain_sends(self) -> None:
        with self._lock:
            queue, self._send_queue = self._send_queue, []
        for text in queue:
            with self._lock:
                # 第一条用户消息顺手当会话标题（用户改过名就不再覆盖）
                self._store.title_from(text)
                sent = Message(
                    role="user",
                    text=text,
                    ts=time.time(),
                    msg_id=f"local-{self._store.current_id}-{time.time_ns()}",
                )
                self._messages.append(sent)
                self._sending = True
                self._stream_text = ""
                self._stream_active = True
                self._cancel.clear()
            try:
                reply = self._send_streaming(text)
                if reply.role == "assistant" and reply.text:
                    if not reply.msg_id:
                        # 消息操作全靠 id 定位：provider 没给 id 的回复自己补一个
                        reply.msg_id = f"ai-{time.time_ns()}"
                    with self._lock:
                        self._messages.append(reply)
                    self._mark_alert()
                self._error = ""
                self._provider_detail = ""
                self._failed_text = ""
                self._failed_msg_id = ""
            except SendCancelled:
                # 用户点了停止：把已收到的部分文本落成一条消息，标注被截断
                with self._lock:
                    partial = self._stream_text.strip()
                if partial:
                    with self._lock:
                        self._messages.append(
                            Message(
                                role="assistant",
                                text=partial,
                                ts=time.time(),
                                msg_id=f"partial-{int(time.time() * 1000)}",
                            )
                        )
                    self._mark_alert()
                log.info("send 已取消")
            except Exception as exc:
                self._error = str(exc)
                self._provider_detail = str(exc)
                # 记住这条没发出去的用户消息（原文 + id），面板上给「重试」
                self._failed_text = text
                self._failed_msg_id = sent.msg_id
                self.post(Event.PROVIDER_DOWN)
            finally:
                with self._lock:
                    self._sending = False
                    self._stream_active = False
                    self._stream_text = ""
                self._persist_sessions()

    def _send_streaming(self, text: str) -> Message:
        """有 send_stream 就用流式（面板能看到逐字增长），否则退回一次性 send。"""
        stream = getattr(self.provider, "send_stream", None)
        # 直连公网的 provider 无后端会话：发送前把面板时间线注入，保证多轮上下文
        setter = getattr(self.provider, "set_context", None)
        if callable(setter):
            with self._lock:
                # 冻结 = 这条不发给 AI（旧版语义）：进上下文前过滤掉
                context = [m for m in self._messages if not m.frozen]
            setter(context)
        if callable(stream):
            return stream(text, self._on_delta)  # type: ignore[no-any-return]
        return self.provider.send(text)

    # ---- 副作用 -------------------------------------------------------------

    def _apply(self, tr: Transition) -> None:
        with self._lock:
            self._reason = tr.reason
        boot.mark(f"state_{tr.state.value}")
        log.info("state", extra={"state": tr.state.value, "detail": tr.reason})
        for effect in tr.effects:
            if effect == SHOW_PANEL and self._dnd:
                log.info("dnd: 跳过自动弹面板")
                continue
            try:
                self._effect(effect)
            except Exception as exc:  # noqa: BLE001 - 单个副作用失败不该拖垮循环
                self._error = f"{effect}: {exc}"
                log.warning("effect_failed", extra={"event": effect, "detail": str(exc)})
        # 副作用先落地再落盘：否则 state.json 会短暂记录"已降级但 degraded=false"这种自相矛盾状态
        self._update_tray_tip()
        self._write_state()

    def _effect(self, effect: str) -> None:
        from mascot_win import win32

        if effect in (SHOW_PANEL, HIDE_PANEL):
            self._panel_shown = effect == SHOW_PANEL
            hwnd = self._ensure_panel_hwnd()
            if hwnd:
                if effect == SHOW_PANEL:
                    self._place_panel(force=True)
                    win32.show_window(hwnd, True)
                else:
                    win32.show_window(hwnd, False)
            return
        if effect == SHOW_BALL:
            if self._ball is not None:
                self._ball.show()
                if self._pet is None:
                    self._render_idle_ball()
                else:
                    self._render_frame(0.0)
            return
        if effect == HIDE_BALL:
            if self._ball is not None:
                self._ball.hide()
            return
        if effect == START_FRAMES:
            self._frames = True
            self._orbit_t0 = time.monotonic()
            self._orbit_paused = False
            self._orbit_frozen_t = 0.0
            if self._ball is not None:
                self._ball.disable_drag()
                self._ball.enable_context_menu(lambda: [], lambda _cmd: None)
            return
        if effect == STOP_FRAMES:
            self._frames = False
            return
        if effect in (MARK_DEGRADED, CLEAR_DEGRADED):
            self._degraded = effect == MARK_DEGRADED
            return

    def _write_state(self) -> None:
        """state.json：给 `mascot ctl status` 与验收脚本看的只读快照。"""
        path = _state_dir() / "state.json"
        with contextlib.suppress(OSError):
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix(".tmp")
            tmp.write_text(
                json.dumps(self.snapshot(), ensure_ascii=False, indent=2), encoding="utf-8"
            )
            tmp.replace(path)

    def _config_mtime(self) -> tuple[int, int] | None:
        """配置文件当前 mtime/size；文件不存在返回 None。"""
        if self._config_path is None:
            return None
        try:
            st = self._config_path.stat()
        except OSError:
            return None
        return (st.st_mtime_ns, st.st_size)

    def _maybe_reload_config(self) -> None:
        """配置被改过就热重载：热字段立刻生效，其余记进 restart_required。"""
        stamp = self._config_mtime()
        if stamp is None or stamp == self._config_stamp:
            return
        self._config_stamp = stamp
        if self._config_path is None:
            return
        try:
            fresh = load_settings(self._config_path)
        except Exception as exc:  # noqa: BLE001 - 坏配置不能把运行中的实例搞崩
            log.warning("config reload skipped: %s", exc)
            self._restart_required = []
            return
        merged, restart = merge_hot(self.settings, fresh)
        restart = [name for name in restart if name not in self._pinned]
        self.settings = merged
        # 后端/窗口相关字段变了：不重建，但要让用户知道得重启
        self._restart_required = restart
        self._config_reloads += 1
        # 双击时间窗是构造期参数：变了就换一个新 gate（挂起的单击也就自然作废）
        if self._click_gate.window_ms != float(self.settings.click_window_ms):
            self._click_gate = ClickGate(self.settings.click_window_ms)
        # history_limit 调小了：内存与磁盘一起裁，别让旧消息在下次写盘前复活
        trimmed = len(self._messages) > self.settings.history_limit
        if trimmed:
            with self._lock:
                self._messages[:] = self._messages[-self.settings.history_limit :]
        log.info("config reloaded (hot fields applied); restart required: %s", restart or "none")
        if trimmed:
            self._persist_sessions()
        self._write_state()

    def _poll_control(self) -> None:
        """控制文件 IPC：ctl 写 cmd，运行中的实例从这里取（M2 最小实现）。"""
        path = _state_dir() / "control.json"
        try:
            raw = path.read_text(encoding="utf-8")
        except OSError:
            return
        with contextlib.suppress(OSError):
            path.unlink()
        try:
            cmd = str(json.loads(raw).get("cmd", ""))
        except (ValueError, AttributeError):
            return
        if cmd == "send":
            with contextlib.suppress(ValueError, AttributeError):
                self.send_text(str(json.loads(raw).get("text", "")))
        elif cmd == "cancel_send":
            self.cancel_send()
        elif cmd == "clear_history":
            self.clear_history()
        elif cmd == "to_ball":
            self.post(Event.CLICK_CLOCK)
        elif cmd == "to_panel":
            self.post(Event.CLICK_BALL)
        elif cmd == "reset_panel":
            self._reset_panel_pos()
        elif cmd == "pause":
            if not self._paused:
                self.command("toggle_pause")
        elif cmd == "resume":
            if self._paused:
                self.command("toggle_pause")
        elif cmd == "dnd_on":
            if not self._dnd:
                self.command("toggle_dnd")
        elif cmd == "dnd_off":
            if self._dnd:
                self.command("toggle_dnd")
        elif cmd == "quit":
            self._stop.set()
            with contextlib.suppress(Exception):
                if self._panel is not None:
                    self._panel.destroy()

    # ---- 面板定位 -----------------------------------------------------------

    def _ensure_panel_hwnd(self) -> int:
        if self._panel_hwnd:
            return self._panel_hwnd
        from mascot_win import win32

        hwnd = win32.find_window(PANEL_TITLE, timeout_s=10.0)
        if hwnd:
            win32.add_toolwindow(hwnd)
            self._panel_hwnd = hwnd
            boot.mark("panel_hwnd")
        return hwnd

    def _enforce_panel_hidden(self, now: float) -> None:
        """状态机不要面板时，每秒最多纠正一次「窗口又被显示出来」。"""
        from mascot_win import win32

        if self._machine.state is not State.IDLE or not self._panel_hwnd:
            return
        if now - self._panel_recheck < 0.3:
            return
        self._panel_recheck = now
        if win32.is_visible(self._panel_hwnd):
            with contextlib.suppress(Exception):
                win32.show_window(self._panel_hwnd, False)

    def _hide_panel(self) -> None:
        from mascot_win import win32

        if self._panel_hwnd:
            with contextlib.suppress(Exception):
                win32.show_window(self._panel_hwnd, False)

    def _idle_anchor(self, size: tuple[int, int]) -> tuple[int, int]:
        """待机（宠物不在）时的定位：光标所在显示器的右下角，留 24px 边距。"""
        from mascot_win import win32

        width, height = size
        if self._ball_pos is not None:
            # 用户拖过：只要还在某块屏幕的工作区内就尊重它（否则回落到右下角）
            bx, by = self._ball_pos
            wx, wy, ww, wh = win32.work_area(bx + width // 2, by + height // 2)
            if wx <= bx <= wx + ww - 8 and wy <= by <= wy + wh - 8:
                return bx, by
        return self._bottom_right((width, height))

    def _bottom_right(self, size: tuple[int, int]) -> tuple[int, int]:
        """光标所在显示器的工作区右下角，留 24px 边距。"""
        from mascot_win import win32

        cx, cy = win32.cursor_pos()
        wx, wy, ww, wh = win32.work_area(cx, cy)
        width, height = size
        x = wx + ww - width - 24
        y = wy + wh - height - 24
        return max(wx, x), max(wy, y)

    def _mark_alert(self) -> None:
        """有新消息到达：小球亮 2.5s 提示环（M30 状态灯，不改状态机）。"""
        self._alert_until = time.monotonic() + ALERT_S

    def _alert_active(self) -> bool:
        return time.monotonic() < self._alert_until

    def _render_idle_ball(self) -> None:
        """待机小球：固定在右下角，不绕轨道；点击即可展开面板。"""
        from mascot_render.clock import render_clock

        if self._ball is None:
            return
        # 与轨道球同一套像素时钟（M14）：待机不该是"另一种球"
        image = render_clock(
            BALL_SIZE,
            now_ts=time.time(),
            stuck=self._degraded,
            hover=False,
            alert=self._alert_active(),
        )
        self._ball.render(image)
        half = BALL_SIZE // 2
        self._ball.set_hit_circle(half, half, half + 2)
        self._ball_circle = None
        self._ball.enable_drag(self._on_ball_drag, self._on_ball_drag_end)
        self._ball.enable_context_menu(self._build_tray_menu, self._on_tray_command)
        x, y = self._idle_anchor((BALL_SIZE, BALL_SIZE))
        self._ball.move(x, y)

    def _reset_ball_to_corner(self) -> None:
        """忘掉拖过的位置，回到光标所在屏幕的右下角（托盘菜单/双击待机球共用）。"""
        self._ball_pos = None
        save_ball_pos(None)
        self._render_idle_ball()
        log.info("ball_reset", extra={"via": "menu_or_double_click"})

    def _on_ball_click(self) -> None:
        """球被单击（抬起且未拖动）。

        - 待机态：单击开面板，双击把球送回右下角；
        - 环绕态：单击回到面板，双击暂停/恢复公转（M29）；
        - 其余状态：直接开面板。
        """
        state = self._machine.state
        if state is State.ORBITAL:
            result = self._click_gate.click(time.monotonic() * 1000.0)
            if result == DOUBLE:
                self._toggle_orbit_pause()
            elif result == SINGLE:
                self.post(Event.CLICK_BALL)
            return
        if state is not State.IDLE:
            self.post(Event.CLICK_BALL)
            return
        result = self._click_gate.click(time.monotonic() * 1000.0)
        if result == DOUBLE:
            # 双击：不打开面板，把球送回右下角
            self._reset_ball_to_corner()
        elif result == SINGLE:
            # click_window_ms=0（关掉双击手势）：没有待确认的单击，立刻开面板
            self.post(Event.CLICK_BALL)

    def _toggle_orbit_pause(self) -> None:
        """暂停/恢复环绕球公转：冻结角度，恢复时从同一角度接着转（避免瞬移）。"""
        now = time.monotonic()
        if self._orbit_paused:
            self._orbit_t0 = now - self._orbit_frozen_t
            self._orbit_paused = False
        else:
            self._orbit_frozen_t = now - self._orbit_t0
            self._orbit_paused = True
        log.info("orbit_pause", extra={"paused": self._orbit_paused})
        self._write_state()

    def _on_ball_drag(self, x: int, y: int) -> None:
        """拖动回调：夹到工作区内，并记住位置（下一帧重渲染不会弹回角落）。"""
        from mascot_win import win32

        wx, wy, ww, wh = win32.work_area(x + BALL_SIZE // 2, y + BALL_SIZE // 2)
        x = min(max(wx, x), wx + ww - BALL_SIZE)
        y = min(max(wy, y), wy + wh - BALL_SIZE)
        # 开始拖动说明这不是点击：丢掉挂起的单击，免得松手后 350ms 突然弹出面板
        self._click_gate.reset()
        self._ball_pos = (x, y)
        if self._ball is not None:
            self._ball.move(x, y)

    def _on_ball_drag_end(self, x: int, y: int, moved: bool) -> None:
        if not moved:
            return
        # 拖到屏幕边缘附近就贴边（留 8px 缝），避免球悬在边缘外几像素
        from mascot_win import win32

        wx, wy, ww, wh = win32.work_area(x + BALL_SIZE // 2, y + BALL_SIZE // 2)
        snap = 12
        if abs(x - wx) <= snap:
            x = wx + 8
        elif abs((wx + ww) - (x + BALL_SIZE)) <= snap:
            x = wx + ww - BALL_SIZE - 8
        if abs(y - wy) <= snap:
            y = wy + 8
        elif abs((wy + wh) - (y + BALL_SIZE)) <= snap:
            y = wy + wh - BALL_SIZE - 8
        self._ball_pos = (x, y)
        if self._ball is not None:
            self._ball.move(x, y)
        save_ball_pos((x, y))

    def _move_panel_from_js(self, logical_x: float, logical_y: float) -> None:
        """接住 pywebview 的拖动回调（window.move 被我们换掉了，绕开它的 bug）。"""
        from mascot_win import win32

        hwnd = self._panel_hwnd or self._ensure_panel_hwnd()
        if not hwnd:
            return
        scale = win32.window_dpi(hwnd) / 96.0
        win32.move_window(hwnd, int(round(logical_x * scale)), int(round(logical_y * scale)))

    def _place_panel(self, *, force: bool = False) -> None:
        from mascot_win import win32

        if not self._panel_hwnd:
            return
        width, height = self.settings.panel_size
        # 先量真实窗口：WebView 的物理尺寸会被 DPI 放大（settings 是逻辑尺寸），
        # 直接用逻辑尺寸锚定会溢出屏幕右下角；顺带用它发现“用户自己拖过面板”（M24）。
        try:
            px, py, real_w, real_h = win32.get_window_rect(self._panel_hwnd)
        except Exception:
            real_w = real_h = 0
        if real_w > 0 and real_h > 0:
            width, height = real_w, real_h
        if real_w > 0 and self._last_panel_rect is not None:
            last = self._last_panel_rect
            if abs(px - last.x) > 2 or abs(py - last.y) > 2:
                # 位置不是我们放的：用户拖了标题栏（.pywebview-drag-region）
                self._adopt_panel_pos((px, py), (width, height))
                return
        if self._panel_dirty and self._panel_pos is not None:
            # 拖完稳定了再落盘：拖动过程中每帧写盘太吵
            save_panel_pos(self._panel_pos)
            save_panel_offset(self._panel_offset)
            self._panel_dirty = False
        if self._pet is not None and self._panel_offset is not None:
            # 跟随态拖出来的面板：跟着宠物一起走，保持用户选好的相对位置（M27）
            x, y = self._clamp_panel(
                (width, height),
                (self._pet.x + self._panel_offset[0], self._pet.y + self._panel_offset[1]),
            )
            rect = Rect(x, y, width, height)
            if force or rect != self._last_panel_rect:
                win32.move_window_below(self._panel_hwnd, rect.x, rect.y)
                self._last_panel_rect = rect
            return
        if self._panel_pos is not None:
            # 用户钉住的位置：只要还落在某块屏的工作区里就尊重它
            x, y = self._clamp_panel((width, height), self._panel_pos)
            rect = Rect(x, y, width, height)
            if force or rect != self._last_panel_rect:
                win32.move_window_below(self._panel_hwnd, rect.x, rect.y)
                self._last_panel_rect = rect
            return
        if self._pet is None:
            # 待机面板：钉在右下角（宠物没开也要能用）
            x, y = self._bottom_right((width, height))
            rect = Rect(x, y, width, height)
            if force or rect != self._last_panel_rect:
                win32.move_window_below(self._panel_hwnd, rect.x, rect.y)
                self._last_panel_rect = rect
            return
        # 用宠物所在显示器的可用工作区（排除任务栏）；主屏尺寸会把面板从副屏拽回来
        wx, wy, ww, wh = win32.work_area(
            self._pet.x + self._pet.w // 2, self._pet.y + self._pet.h // 2
        )
        rect = follow_rect(
            Rect(self._pet.x, self._pet.y, self._pet.w, self._pet.h),
            self.settings.follow_offset,
            (width, height),
            Screen(ww, wh, wx, wy),
        )
        if rect is None:
            return
        if force or rect != self._last_panel_rect:
            win32.move_window_below(self._panel_hwnd, rect.x, rect.y)
            self._last_panel_rect = rect

    def _adopt_panel_pos(self, pos: tuple[int, int], size: tuple[int, int]) -> None:
        """把用户拖出来的位置记下来（落盘延到拖动停下），并停止自动跟随/贴角。"""
        if self._panel_pos != pos:
            if not self._panel_dirty:
                log.info("panel_moved", extra={"detail": f"{pos[0]},{pos[1]}"})
            self._panel_pos = (int(pos[0]), int(pos[1]))
            self._panel_dirty = True
        pet = self._pet
        if pet is not None:
            # 宠物在：记相对偏移，之后宠物移动面板跟着走
            offset = (int(pos[0]) - pet.x, int(pos[1]) - pet.y)
            if offset != self._panel_offset:
                log.info("panel_offset", extra={"detail": f"{offset[0]},{offset[1]}"})
                self._panel_offset = offset
        elif self._panel_offset is not None:
            # 待机态拖出来的是绝对位置：清掉偏移，等宠物回来用默认跟随位置
            log.info("panel_offset_cleared")
            self._panel_offset = None
        width, height = size
        self._last_panel_rect = Rect(pos[0], pos[1], width, height)

    def _clamp_panel(self, size: tuple[int, int], pos: tuple[int, int]) -> tuple[int, int]:
        """面板位置夹进它所在显示器的工作区，避免拖到屏幕外找不回来。"""
        from mascot_win import win32

        width, height = size
        wx, wy, ww, wh = win32.work_area(pos[0] + width // 2, pos[1] + height // 2)
        x = min(max(wx, pos[0]), max(wx, wx + ww - width))
        y = min(max(wy, pos[1]), max(wy, wy + wh - height))
        return x, y

    def _reset_panel_pos(self) -> None:
        """取消拖动记忆：回到默认位置（待机右下角 / 跟随宠物）。"""
        self._panel_pos = None
        save_panel_pos(None)
        self._panel_offset = None
        save_panel_offset(None)
        self._last_panel_rect = None
        self._place_panel(force=True)
        log.info("panel_reset")

    # ---- 帧 ---------------------------------------------------------------

    def _render_frame(self, t: float) -> None:
        """环绕态整帧：彗尾 + 像素时钟球，窗口盖住整个轨道，只有球可点。"""
        from mascot_render.clock import render_orbit_frame

        if self._ball is None:
            return
        pet = self._pet
        if pet is None:
            return
        pet_rect = Rect(pet.x, pet.y, pet.w, pet.h)
        angle = angle_for_time(t, self.settings.orbit_period_s, self.settings.orbit_speed)
        layout = orbit_layout(pet_rect, self.settings.ball_ratio, self.settings.orbit_gap)
        image = render_orbit_frame(
            layout.window,
            ball_r=layout.ball_r,
            orbit_r=layout.orbit_r,
            angle_deg=math.degrees(angle),
            stuck=self._machine.state is State.DEGRADED,
            alert=self._alert_active(),
        )
        cx, cy = pet_rect.center
        half = layout.window / 2
        self._ball.render(image)
        bx = round(half + layout.orbit_r * math.cos(angle))
        by = round(half + layout.orbit_r * math.sin(angle))
        self._ball.set_hit_circle(bx, by, layout.ball_r + 4)
        left, top = round(cx - half), round(cy - half)
        self._ball.move(left, top)
        self._ball_circle = (left + bx, top + by, layout.ball_r + 4)

    # ---- 工作线程 -----------------------------------------------------------

    def _worker(self) -> None:
        from mascot_win import win32
        from mascot_win.layered import LayeredWindow
        from mascot_win.tracker import PetTracker

        boot.mark("worker_start")
        win32.enable_dpi_awareness()
        tracker = PetTracker(
            class_names=(self.settings.pet_window_class,),
            process_names=self.settings.pet_process_names,
            lost_frames=self.settings.lost_frames,
        )
        boot.mark("worker_dpi")
        self._ball = LayeredWindow(
            BALL_SIZE,
            BALL_SIZE,
            click_through=False,
            start_hidden=True,
            on_click=self._on_ball_click,
        )
        boot.mark("ball_ready")
        self._create_tray()
        boot.mark("tray_ready")

        # 待机也要"看得见"：宠物不在时右下角常驻一颗小球，点它展开面板。
        # 宠物一出现，PET_FOUND 会把它收起（见 state.py）。
        boot_ball = self._ball
        if self._machine.state is State.IDLE and boot_ball is not None:
            with contextlib.suppress(Exception):
                boot_ball.show()
                self._render_idle_ball()

        # 后端 I/O（history/health/send）已挪到独立线程：WSL 后端不可达时
        # 每次请求要等满超时（2s），放在工作线程里会拖住从宠物出现到面板出现。
        # 上一次异常退出可能留下 control.json：启动时先清掉，避免"幽灵消息"
        with contextlib.suppress(OSError):
            (_state_dir() / "control.json").unlink()

        next_poll = 0.0
        next_frame = 0.0
        last_state_write = 0.0
        last_config_check = 0.0

        try:
            while not self._stop.is_set():
                now = time.monotonic()
                self._ball.pump()
                self._drain_events()
                self._drain_commands()
                # 待机球的单击要等双击窗口过去才确认（见 click.py）
                if self._click_gate.tick(now * 1000.0) == SINGLE:
                    self.post(Event.CLICK_BALL)

                # 面板窗口在状态机不需要它时必须真的不可见：pywebview 的 hidden=True
                # 只是 Opacity=0 + Show + Hide，WebView2 建好之后还会再 Show 一次。
                self._enforce_panel_hidden(now)

                # 配置文件每秒查一次：改了热重载（否则用户得重启才看到 fps 变化）
                if now - last_config_check >= 1.0:
                    last_config_check = now
                    self._maybe_reload_config()
                interval = self.settings.poll_interval_ms / 1000.0
                frame_s = 1.0 / self.settings.fps

                if now >= next_poll:
                    next_poll = now + interval
                    self._poll_control()
                    if not self._paused:
                        self._poll_pet(tracker)
                        # 降级也要跟随：后端不可达只影响发消息，不影响面板定位（A1）
                        self._place_panel()

                ball_now = self._ball
                if (
                    not self._frames
                    and self._machine.state is State.IDLE
                    and ball_now is not None
                    and now >= next_frame
                ):
                    next_frame = now + 1.0
                    with contextlib.suppress(Exception):
                        self._render_idle_ball()

                if self._frames and now >= next_frame:
                    next_frame = now + frame_s
                    frame_t = self._orbit_frozen_t if self._orbit_paused else now - self._orbit_t0
                    self._render_frame(frame_t)

                # 状态文件每秒刷新：ctl status / 验收脚本才能看到 uptime、消息与 sending
                if now - last_state_write >= 1.0:
                    last_state_write = now
                    self._write_state()

                time.sleep(0.005)
        finally:
            with contextlib.suppress(Exception):  # 退出路径尽力而为
                if self._tray is not None:
                    self._tray.destroy()
                self._tray = None
                self._ball.destroy()
            self._ball = None

    # ---- 托盘 ---------------------------------------------------------------

    def _create_tray(self) -> None:
        try:
            from mascot_win.tray import TrayIcon

            self._tray = TrayIcon(
                tip=self._tray_tip(),
                build_menu=self._build_tray_menu,
                on_command=self._on_tray_command,
                on_double_click=self._toggle_panel,
            )
            log.info("tray: 已创建")
        except Exception as exc:  # 托盘失败不该拖垮主程序
            log.warning("tray: 创建失败（%s）", exc)
            self._tray = None

    def _tray_tip(self) -> str:
        state = self._machine.state.value
        label = _STATE_LABEL.get(state, state)
        if self._paused:
            label += "（已暂停跟随）"
        if self._dnd:
            label += "（免打扰）"
        return f"天选姬 · {label}"

    def _build_tray_menu(self) -> list[tuple[int, str, bool]]:
        return [
            (CMD_TO_PANEL, "显示面板", False),
            (CMD_TO_BALL, "收进小球", False),
            (0, "", False),
            (CMD_PAUSE, "暂停跟随", self._paused),
            (CMD_DND, "免打扰", self._dnd),
            (CMD_AUTOSTART, "开机自启", _autostart_enabled()),
            (0, "", False),
            (CMD_RESET_BALL, "小球回到右下角", False),
            (CMD_RESET_PANEL, "面板回到默认位置", False),
            (CMD_QUIT, "退出", False),
        ]

    def _on_tray_command(self, cmd: int) -> None:
        if cmd == CMD_TO_PANEL:
            self.command("to_panel")
        elif cmd == CMD_TO_BALL:
            self.command("to_ball")
        elif cmd == CMD_PAUSE:
            self.command("toggle_pause")
        elif cmd == CMD_DND:
            self.command("toggle_dnd")
        elif cmd == CMD_AUTOSTART:
            self.command("toggle_autostart")
        elif cmd == CMD_RESET_BALL:
            self._reset_ball_to_corner()
        elif cmd == CMD_RESET_PANEL:
            self._reset_panel_pos()
        elif cmd == CMD_QUIT:
            self.command("quit")

    def _toggle_panel(self) -> None:
        if self._machine.state is State.ORBITAL:
            self.command("to_panel")
        else:
            self.command("to_ball")

    def _update_tray_tip(self) -> None:
        if self._tray is not None:
            with contextlib.suppress(Exception):
                self._tray.update_tip(self._tray_tip())

    def _drain_commands(self) -> None:
        with self._lock:
            commands, self._commands = self._commands, []
        for name in commands:
            if name == "to_ball":
                self.post(Event.CLICK_CLOCK)
            elif name == "to_panel":
                self.post(Event.CLICK_BALL)
            elif name == "toggle_pause":
                self._paused = not self._paused
                log.info("pause: %s", "on" if self._paused else "off")
                self._update_tray_tip()
                save_flags(dnd=self._dnd, paused=self._paused)
                self._write_state()
            elif name == "toggle_dnd":
                self._dnd = not self._dnd
                log.info("dnd: %s", "on" if self._dnd else "off")
                if self._dnd:
                    self._hide_panel()
                self._update_tray_tip()
                save_flags(dnd=self._dnd, paused=self._paused)
                self._write_state()
            elif name == "toggle_autostart":
                self._toggle_autostart()
            elif name == "quit":
                self._stop.set()

    def _toggle_autostart(self) -> None:
        import sys

        if not getattr(sys, "frozen", False):
            log.warning("autostart: 开发态（非打包 exe）不写注册表，请用 mascot autostart on --exe")
            return
        try:
            from mascot_win import autostart

            if autostart.is_enabled():
                autostart.disable()
                log.info("autostart: off")
            else:
                autostart.enable(sys.executable)
                log.info("autostart: on")
        except Exception as exc:
            log.warning("autostart: 切换失败（%s）", exc)
        self._write_state()

    def _drain_events(self) -> None:
        with self._lock:
            events, self._events = self._events, []
        for event in events:
            self._apply(self._machine.push(event))

    def _poll_pet(self, tracker: Any) -> None:
        found = tracker.poll()
        if found is not None:
            first_seen = self._pet is None
            self._pet = PetView(
                x=found.rect.x,
                y=found.rect.y,
                w=found.rect.w,
                h=found.rect.h,
                process=found.process,
                class_name=found.class_name,
            )
            if first_seen and self._machine.state in (State.IDLE, State.IDLE_OPEN):
                boot.mark("pet_found")
                self.post(Event.PET_FOUND)
            return
        # 丢失：跟随态立刻收起面板；环绕态保留最后位置，避免球突然消失
        if self._pet is not None and self._machine.state is State.TRACKING:
            self._pet = None
            self.post(Event.PET_LOST)

    def _poll_provider(self) -> None:
        """后端健康探测：无论 allow_offline 与否都要探测并如实展示降级。

        allow_offline 的语义是“后端不可用时仍让桌宠继续工作”，
        不是“装作后端没问题”——早期实现反了，默认配置下永远看不到降级横幅。

        例外：显式 `--provider null` 表示“本次就是不要后端”，此时探测只会把
        自己标成降级，属于自欺欺人的噪声（2026-10-22 截图里 null 演示全变降级）。
        """
        if self.provider.name == "null":
            self._provider_detail = "null provider（显式离线模式）"
            return
        health = self.provider.health()
        if not health.ok:
            self._provider_detail = health.detail or health.reason_code
            # 只在状态真的翻转时推事件：否则每 5s 一次 IGNORED:PROVIDER_DOWN 刷爆日志
            if not self._degraded:
                self.post(Event.PROVIDER_DOWN)
        else:
            self._provider_detail = ""
            if self._degraded:
                self.post(Event.PROVIDER_READY)

    # ---- 入口 ---------------------------------------------------------------

    def run(
        self,
        *,
        duration_s: float = 0.0,
        demo: bool = False,
        screenshot: str | None = None,
        gui: str | None = None,
    ) -> int:
        import webview

        width, height = self.settings.panel_size
        self._panel = webview.create_window(
            PANEL_TITLE,
            html=self.panel_html,
            width=width,
            height=height,
            transparent=True,
            frameless=True,
            on_top=True,
            resizable=False,
            easy_drag=False,
            hidden=True,
            js_api=JsApi(self),
        )
        # pywebview 6.2.1 的 WinForms move() 有 bug：SetWindowPos 把 None 传给 int 参数
        # 会抛 ctypes.ArgumentError（实测拖动时 js_bridge_call 报错、窗口不动）。
        # 拖动回调是我们自己的窗口，直接接管：JS 给逻辑像素，这里换算成物理像素再移。
        self._panel.move = self._move_panel_from_js  # type: ignore[method-assign]

        threading.Thread(target=self._worker, name="mascot-runtime", daemon=True).start()
        threading.Thread(target=self._history_loop, name="mascot-history", daemon=True).start()
        threading.Thread(target=self._sender_loop, name="mascot-sender", daemon=True).start()
        threading.Thread(target=self._provider_loop, name="mascot-provider", daemon=True).start()
        if demo:
            threading.Thread(target=self._demo_script, name="mascot-demo", daemon=True).start()
        if duration_s > 0 or screenshot:
            threading.Thread(
                target=self._auto_exit,
                args=(duration_s, screenshot),
                name="mascot-timer",
                daemon=True,
            ).start()

        webview.start(gui=gui, func=self._on_gui_start)  # type: ignore[arg-type]  # 主线程，阻塞到窗口关闭
        self._stop.set()
        return 0

    # ---- 后端 I/O 线程 ------------------------------------------------------

    def _history_loop(self) -> None:
        self._load_history()

    def _sender_loop(self) -> None:
        """发消息串行化：一次只有一个 send 在飞，网络等待不占工作线程。"""
        while not self._stop.is_set():
            with self._lock:
                pending = bool(self._send_queue) and not self._sending
            if pending:
                self._drain_sends()
            else:
                time.sleep(0.01)

    def _provider_loop(self) -> None:
        while not self._stop.is_set():
            self._poll_provider()
            deadline = time.monotonic() + 5.0
            while not self._stop.is_set() and time.monotonic() < deadline:
                time.sleep(0.05)

    def _on_gui_start(self) -> None:
        boot.mark("webview_started")
        # 兜底：pywebview 的 hidden=True 走的是 Opacity=0 + Show + Hide，WebView2 建好
        # 之后窗口可能又被显示出来（启动探针实测 WS_VISIBLE 为真、覆盖 228,228 488×634）。
        # 状态机此刻不要面板，就显式再藏一次；要面板（宠物在）则不动。
        if self._machine.state is State.IDLE:
            hwnd = self._ensure_panel_hwnd()
            if hwnd:
                from mascot_win import win32

                with contextlib.suppress(Exception):
                    win32.show_window(hwnd, False)
                boot.mark("panel_hidden_at_start")

    def _demo_script(self) -> None:
        """自动化验收用：2s 收进小球，6s 回到面板。"""
        time.sleep(2.0)
        log.info("demo_to_ball")
        self.post(Event.CLICK_CLOCK)
        time.sleep(4.0)
        log.info("demo_to_panel")
        self.post(Event.CLICK_BALL)

    def _auto_exit(self, duration_s: float, screenshot: str | None) -> None:
        if screenshot:
            time.sleep(max(1.0, duration_s - 1.5 if duration_s > 0 else 4.0))
            self._grab(screenshot)
        if duration_s > 0:
            time.sleep(1.5 if screenshot else duration_s)
            self._stop.set()
            try:
                if self._panel is not None:
                    self._panel.destroy()
            except Exception as exc:  # noqa: BLE001 - 关闭窗口失败也要退出
                log.warning("destroy_failed", extra={"detail": str(exc)})

    def _grab(self, path: str) -> None:
        try:
            from PIL import ImageGrab

            ImageGrab.grab(all_screens=True).save(path)
            log.info("screenshot", extra={"detail": path})
        except Exception as exc:  # noqa: BLE001 - 截图只是证据，失败不影响运行
            log.warning("screenshot_failed", extra={"detail": str(exc)})


def make_runtime(settings: Settings, provider: ChatProvider) -> Runtime:
    return Runtime(settings, provider)
