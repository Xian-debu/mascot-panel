"""本地聊天记录（跨重启保留）。

provider 的 history 只是后端给的（可能是空、可能每次启动重新生成欢迎语）；
用户真正看到过的对话在这里落盘，重启后接着显示。纯函数，无 IO、无平台依赖。
"""

from __future__ import annotations

import json

from mascot_core.contract import Message

MAX_TEXT = 4000


def _as_message(item: object) -> Message | None:
    if not isinstance(item, dict):
        return None
    role = item.get("role")
    text = item.get("text")
    if role not in ("user", "assistant") or not isinstance(text, str):
        return None
    text = text[:MAX_TEXT]
    if not text:
        return None
    ts = item.get("ts")
    ts = float(ts) if isinstance(ts, (int, float)) else 0.0
    mid = item.get("id")
    mid = mid if isinstance(mid, str) else ""
    return Message(role=role, text=text, ts=ts, msg_id=mid)


def parse_history(raw: str) -> list[Message]:
    """读坏的记录只跳过坏条目，绝不让启动失败。"""
    try:
        data = json.loads(raw)
    except (ValueError, TypeError):
        return []
    items = data.get("messages") if isinstance(data, dict) else data
    if not isinstance(items, list):
        return []
    out: list[Message] = []
    for item in items:
        msg = _as_message(item)
        if msg is not None:
            out.append(msg)
    return out


def dump_history(messages: list[Message]) -> str:
    return json.dumps(
        {"version": 1, "messages": [m.to_dict() for m in messages]},
        ensure_ascii=False,
        indent=2,
    )


def _keys(msg: Message) -> tuple[tuple[str, str, int], tuple[str, str, int] | None]:
    """一条消息最多两个身份：内容指纹（role+文本+秒级时间）+ 有 id 时的 id。

    只按 id 去重会漏掉"后端没给 id 的欢迎语"和"我们落盘的 offline-0"这种同一句话；
    只按内容去重又会把用户重复发的同一句话吞掉。两个都算，命中任一即视为重复。
    """
    content = (msg.role, msg.text, int(msg.ts))
    ident = (msg.role, msg.msg_id, -1) if msg.msg_id else None
    return content, ident


def merge_history(*groups: list[Message], limit: int = 50) -> list[Message]:
    """按时间排序合并多份记录，按内容/id 去重，只留最后 limit 条。

    同一条消息既来自本地落盘又来自后端历史时不会出现两遍；
    时间戳为 0 的（后端没给时间）保持组内顺序排在前面。
    """
    seen: set[tuple[str, str, int]] = set()
    merged: list[Message] = []
    for group in groups:
        for msg in group:
            content, ident = _keys(msg)
            if content in seen or (ident is not None and ident in seen):
                continue
            seen.add(content)
            if ident is not None:
                seen.add(ident)
            merged.append(msg)
    merged.sort(key=lambda m: m.ts)
    return merged[-limit:]
