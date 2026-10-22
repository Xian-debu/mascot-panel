"""运行时：把状态机、追踪器、面板与球接成一个真的进程。

线程模型（M1 实测结论，D-15）：
    主线程      pywebview 消息循环（面板 = WebView2，必须由它驱动）
    工作线程    状态机 + 追踪 + 自绘球窗口 + 球自己的消息泵
    交叉点      只有 queue.Queue（工作线程 -> UI 由 JS 侧轮询 api.snapshot() 拿）
"""

from __future__ import annotations

import contextlib
import json
import logging
import math
import os
import threading
import time
from dataclasses import dataclass
from importlib import resources
from pathlib import Path
from typing import Any

from mascot_app import boot
from mascot_core.config import Settings
from mascot_core.contract import ChatProvider, Message
from mascot_core.geometry import Rect, Screen, angle_for_time, follow_rect, orbit_layout
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


def _state_dir() -> Path:
    local = os.environ.get("LOCALAPPDATA")
    base = Path(local) if local else Path.home() / ".mascot"
    return base / "mascot" if local else base


TOKENS_PLACEHOLDER = "/*__TOKENS__*/"
CSS_PLACEHOLDER = "/*__CSS__*/"
JS_PLACEHOLDER = "//__JS__"
CSS_MODULES = ("base.css", "stream.css", "composer.css", "states.css")
JS_MODULES = ("state.js", "clock.js", "ui.js", "chat.js", "composer.js", "main.js")
MESSAGE_LIMIT = 50


def _pkg_text(rel: str) -> str:
    return resources.files("mascot_app").joinpath(rel).read_text(encoding="utf-8")


def load_panel_html() -> str:
    """把面板外壳、CSS 模块、JS 模块与设计 token 合成一张自包含 HTML。

    面板拆成多文件开发（好读好改），运行时合成单文件给 WebView（不依赖本地路径）。
    """
    html = _pkg_text("web/panel.html")
    css = "\n".join(_pkg_text(f"web/css/{name}") for name in CSS_MODULES)
    js = "\n".join(_pkg_text(f"web/js/{name}") for name in JS_MODULES)
    return (
        html.replace(TOKENS_PLACEHOLDER, css_variables())
        .replace(CSS_PLACEHOLDER, css)
        .replace(JS_PLACEHOLDER, js)
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

    def send(self, text: str) -> dict[str, Any]:
        return self._rt.send_text(text)



# 托盘菜单命令 id（只在进程内使用，不进协议）
CMD_TO_PANEL = 1001
CMD_TO_BALL = 1002
CMD_PAUSE = 1003
CMD_AUTOSTART = 1004
CMD_QUIT = 1005
CMD_DND = 1006

_STATE_LABEL = {
    "idle": "待机",
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
    ) -> None:
        self.settings = settings
        self.provider = provider
        self.panel_html = panel_html or load_panel_html()

        self._machine = Machine()
        self._events: list[Event] = []
        self._lock = threading.Lock()
        self._stop = threading.Event()

        self._panel: Any = None
        self._panel_hwnd = 0
        self._ball: Any = None
        self._pet: PetView | None = None
        self._last_panel_rect: Rect | None = None
        self._frames = False
        self._orbit_t0 = 0.0
        self._started = time.monotonic()
        self._reason = "START"
        self._degraded = False
        self._error: str = ""
        self._provider_detail: str = ""
        self._messages: list[Message] = []
        self._sending = False
        self._send_queue: list[str] = []
        self._paused = False
        self._dnd = False  # 免打扰：不自动弹出面板（仍跟随、仍可手动打开）
        self._commands: list[str] = []
        self._tray: Any = None

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
                "sending": self._sending,
                "paused": self._paused,
                "dnd": self._dnd,
                "autostart": _autostart_enabled(),
                "messages": [m.to_dict() for m in self._messages[-MESSAGE_LIMIT:]],
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

    # ---- 聊天 ---------------------------------------------------------------

    def send_text(self, text: str) -> dict[str, Any]:
        """JS 发来的消息只入队：真正的网络调用在工作线程里做，别卡住 UI。"""
        clean = (text or "").strip()
        if not clean:
            return {"ok": False, "reason": "EMPTY_TEXT"}
        with self._lock:
            self._send_queue.append(clean[:4000])
        return {"ok": True, "queued": True}

    def _load_history(self) -> None:
        try:
            history = self.provider.history(limit=MESSAGE_LIMIT)
        except Exception as exc:  # provider 是外部世界，绝不假设它守规矩
            self._provider_detail = str(exc)
            return
        with self._lock:
            self._messages = list(history)

    def _drain_sends(self) -> None:
        with self._lock:
            queue, self._send_queue = self._send_queue, []
        for text in queue:
            with self._lock:
                self._messages.append(
                    Message(role="user", text=text, ts=time.time(), msg_id=f"local-{len(self._messages)}")
                )
                self._sending = True
            try:
                reply = self.provider.send(text)
                if reply.role == "assistant" and reply.text:
                    with self._lock:
                        self._messages.append(reply)
                self._error = ""
                self._provider_detail = ""
            except Exception as exc:
                self._error = str(exc)
                self._provider_detail = str(exc)
                self.post(Event.PROVIDER_DOWN)
            finally:
                with self._lock:
                    self._sending = False

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
                self._render_frame(0.0)
            return
        if effect == HIDE_BALL:
            if self._ball is not None:
                self._ball.hide()
            return
        if effect == START_FRAMES:
            self._frames = True
            self._orbit_t0 = time.monotonic()
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
        elif cmd == "to_ball":
            self.post(Event.CLICK_CLOCK)
        elif cmd == "to_panel":
            self.post(Event.CLICK_BALL)
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

    def _hide_panel(self) -> None:
        from mascot_win import win32

        if self._panel_hwnd:
            with contextlib.suppress(Exception):
                win32.show_window(self._panel_hwnd, False)

    def _place_panel(self, *, force: bool = False) -> None:
        from mascot_win import win32

        if self._pet is None or not self._panel_hwnd:
            return
        width, height = self.settings.panel_size
        # 用宠物所在显示器的可用工作区（排除任务栏）；主屏尺寸会把面板从副屏拽回来
        wx, wy, ww, wh = win32.work_area(self._pet.x + self._pet.w // 2, self._pet.y + self._pet.h // 2)
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
        )
        cx, cy = pet_rect.center
        half = layout.window / 2
        self._ball.render(image)
        self._ball.set_hit_circle(
            round(half + layout.orbit_r * math.cos(angle)),
            round(half + layout.orbit_r * math.sin(angle)),
            layout.ball_r + 4,
        )
        self._ball.move(round(cx - half), round(cy - half))

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
            on_click=lambda: self.post(Event.CLICK_BALL),
        )
        boot.mark("ball_ready")
        self._create_tray()
        boot.mark("tray_ready")

        # 后端 I/O（history/health/send）已挪到独立线程：WSL 后端不可达时
        # 每次请求要等满超时（2s），放在工作线程里会拖住从宠物出现到面板出现。
        # 上一次异常退出可能留下 control.json：启动时先清掉，避免"幽灵消息"
        with contextlib.suppress(OSError):
            (_state_dir() / "control.json").unlink()

        interval = self.settings.poll_interval_ms / 1000.0
        frame_s = 1.0 / self.settings.fps
        next_poll = 0.0
        next_frame = 0.0
        last_state_write = 0.0

        try:
            while not self._stop.is_set():
                now = time.monotonic()
                self._ball.pump()
                self._drain_events()
                self._drain_commands()

                if now >= next_poll:
                    next_poll = now + interval
                    self._poll_control()
                    if not self._paused:
                        self._poll_pet(tracker)
                        if not self._degraded:
                            self._place_panel()

                if self._frames and now >= next_frame:
                    next_frame = now + frame_s
                    self._render_frame(now - self._orbit_t0)

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
                self._write_state()
            elif name == "toggle_dnd":
                self._dnd = not self._dnd
                log.info("dnd: %s", "on" if self._dnd else "off")
                if self._dnd:
                    self._hide_panel()
                self._update_tray_tip()
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
            if first_seen and self._machine.state is State.IDLE:
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
            self.post(Event.PROVIDER_DOWN)
        else:
            self._provider_detail = ""
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
