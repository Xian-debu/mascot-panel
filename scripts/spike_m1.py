"""M1 平台 spike：DPI / 单实例 / 目标发现 / 自绘球窗口 / WebView2 面板共存。

在 Windows Python 上运行：
    venv/Scripts/python.exe scripts/spike_m1.py --seconds 8
输出：stdout 一个 JSON；stderr 人类可读进度。
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import threading
import time
from pathlib import Path


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seconds", type=float, default=8.0, help="GUI 存活秒数")
    ap.add_argument("--fps", type=float, default=12.0)
    ap.add_argument("--no-webview", action="store_true")
    ap.add_argument("--no-ball", action="store_true")
    ap.add_argument("--screenshot", default="", help="存活期间抓一张全屏 PNG（证据）")
    args = ap.parse_args()

    report: dict = {"ok": False, "steps": {}, "env": {"platform": sys.platform, "python": sys.version.split()[0]}}
    if sys.platform != "win32":
        report["code"] = "NOT_WINDOWS"
        print(json.dumps(report, ensure_ascii=False))
        return 3

    from mascot_win import win32
    from mascot_win.single import SingleInstance
    from mascot_win.tracker import PetTracker

    level = win32.enable_dpi_awareness()
    sw, sh = win32.screen_metrics()
    dpi = win32.window_dpi(0)
    report["steps"]["dpi"] = {
        "ok": level != "none",
        "level": level,
        "screen_physical": [sw, sh],
        "dpi": dpi,
        "scale": round(dpi / 96, 3),
    }

    a = SingleInstance("Local\\MascotSpike")
    first = a.acquire()
    b = SingleInstance("Local\\MascotSpike")
    second = b.acquire()
    b.release()
    a.release()
    report["steps"]["single_instance"] = {"ok": first and not second, "first": first, "second": second}

    tracker = PetTracker(class_names=("TX Mascot",), process_names=("TXPet.exe", "TX Pets.exe"))
    found = tracker.poll()
    visible = win32.candidates()
    report["steps"]["tracker"] = {
        "ok": True,
        "found": None
        if found is None
        else {
            "class": found.class_name,
            "process": found.process,
            "rect": [found.rect.x, found.rect.y, found.rect.w, found.rect.h],
        },
        "visible_windows": len(visible),
        "sample": [
            {"class": c["class"][:40], "process": c["process"][:30], "rect": list(c["rect"])}
            for c in visible[:10]
        ],
    }

    stop = threading.Event()
    ball_ok = {"done": False}

    def ball_worker() -> None:
        from mascot_render.ball import render_ball
        from mascot_win.layered import LayeredWindow

        size = 96
        frames = 0
        error = ""
        win = None
        try:
            win = LayeredWindow(size, size, click_through=True)
            screen_w, screen_h = win32.screen_metrics()
            cx, cy = screen_w // 2, screen_h // 2
            t0 = time.monotonic()
            while not stop.is_set():
                t = time.monotonic() - t0
                win.render(render_ball(size, phase=(t * 0.5) % 1.0))
                ang = t * 2 * math.pi / 6
                win.move(
                    int(cx + math.cos(ang) * 150 - size / 2),
                    int(cy + math.sin(ang) * 150 - size / 2),
                )
                win.pump()
                frames += 1
                time.sleep(0.01)
        except Exception as exc:  # noqa: BLE001 - spike 必须带回错误而不是崩溃
            error = f"{type(exc).__name__}: {exc}"
        finally:
            if win is not None:
                win.destroy()
            ball_ok["done"] = True
            ball_ok["frames"] = frames
            ball_ok["error"] = error

    ball_thread = None
    if not args.no_ball:
        ball_thread = threading.Thread(target=ball_worker, name="ball", daemon=True)
        ball_thread.start()

    webview_ok: dict = {"skipped": args.no_webview}
    if not args.no_webview:
        try:
            import webview

            from mascot_app.runtime import load_panel_html

            html = load_panel_html()
            window = webview.create_window(
                "mascot",
                html=html,
                width=340,
                height=460,
                frameless=True,
                transparent=True,
                on_top=True,
                resizable=False,
                easy_drag=False,
            )

            def close_later() -> None:
                if args.screenshot:
                    time.sleep(max(0.5, args.seconds / 2))
                    try:
                        from PIL import ImageGrab

                        shot = ImageGrab.grab()
                        Path(args.screenshot).parent.mkdir(parents=True, exist_ok=True)
                        shot.save(args.screenshot)
                        report["screenshot"] = args.screenshot
                    except Exception as shot_exc:  # noqa: BLE001
                        report["screenshot_error"] = f"{type(shot_exc).__name__}: {shot_exc}"
                time.sleep(max(0.0, args.seconds - args.seconds / 2))
                stop.set()
                window.destroy()

            threading.Thread(target=close_later, name="closer", daemon=True).start()
            started = time.monotonic()
            webview.start()
            webview_ok = {"ok": True, "alive_s": round(time.monotonic() - started, 2)}
        except Exception as exc:  # noqa: BLE001
            stop.set()
            webview_ok = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
    else:
        time.sleep(args.seconds)
        stop.set()

    if ball_thread is not None:
        ball_thread.join(timeout=5)
    report["steps"]["ball"] = {
        "ok": bool(ball_ok.get("frames")) and not ball_ok.get("error"),
        "frames": ball_ok.get("frames"),
        "error": ball_ok.get("error", ""),
        "skipped": args.no_ball,
    }
    report["steps"]["webview"] = webview_ok
    report["ok"] = all(s.get("ok", True) for s in report["steps"].values() if isinstance(s, dict))
    print(json.dumps(report, ensure_ascii=False))
    return 0 if report["ok"] else 5


if __name__ == "__main__":
    raise SystemExit(main())
