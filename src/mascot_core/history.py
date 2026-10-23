"""旧版本地聊天记录（history.json）的解析与合并。

B1 起对话落在 sessions.json（mascot_core/sessions.py），这里只剩两件事：
读旧文件做一次性迁移，以及消息列表的合并/清理工具（states 移植过来的纯函数）。
纯函数，无 IO、无平台依赖。
"""

from __future__ import annotations

import json

from mascot_core.contract import Message

MAX_TEXT = 4000
MAX_VERSIONS = 10  # 编辑历史最多留 10 层（旧版上限，够回退又不至于撑爆记录）


def _as_message(item: object, idx: int) -> Message | None:
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
    mid = mid if isinstance(mid, str) and mid else f"mig-{idx}-{int(ts)}"
    raw_hist = item.get("history")
    history = (
        [h[:MAX_TEXT] for h in raw_hist if isinstance(h, str) and h][-MAX_VERSIONS:]
        if isinstance(raw_hist, list)
        else []
    )
    return Message(
        role=role,
        text=text,
        ts=ts,
        msg_id=mid,
        frozen=item.get("frozen") is True,
        collapsed=item.get("collapsed") is True,
        history=history,
    )


def parse_messages(items: object) -> list[Message]:
    """把任意 list 里像消息的条目转成 Message，其余跳过（迁移/多会话共用）。

    没 id 的条目补一个确定性的 id（消息操作全靠 id 定位，空 id 会互相串）。
    """
    if not isinstance(items, list):
        return []
    out: list[Message] = []
    for idx, item in enumerate(items):
        msg = _as_message(item, idx)
        if msg is not None:
            out.append(msg)
    return out


def parse_history(raw: str) -> list[Message]:
    """读坏的记录只跳过坏条目，绝不让启动失败。"""
    try:
        data = json.loads(raw)
    except (ValueError, TypeError):
        return []
    items = data.get("messages") if isinstance(data, dict) else data
    return parse_messages(items)


def _keys(msg: Message) -> tuple[tuple[str, str, int], tuple[str, str, int] | None]:
    """一条消息最多两个身份：内容指纹（role+文本+秒级时间）+ 有 id 时的 id。

    只按 id 去重会漏掉"后端没给 id 的欢迎语"和"我们落盘的 offline-0"这种同一句话；
    只按内容去重又会把用户重复发的同一句话吞掉。两个都算，命中任一即视为重复。
    """
    content = (msg.role, msg.text, int(msg.ts))
    ident = (msg.role, msg.msg_id, -1) if msg.msg_id else None
    return content, ident


def filter_cleared(messages: list[Message], cleared: set[str]) -> list[Message]:
    """去掉用户已经 clear-history 过的消息（按 msg_id）；没有 id 的保留。"""
    if not cleared:
        return list(messages)
    return [m for m in messages if not m.msg_id or m.msg_id not in cleared]


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
