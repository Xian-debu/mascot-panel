"""备忘录的纯逻辑层（M43）：分组 + 条目，不碰文件、不碰时间（now 由调用方传入）。

为什么独立成一个模块：和 sessions.py 一样，UI 只通过 runtime 的桥访问，
这里只做数据与排序规则，方便单独推演（也避免把面板 JS 的复杂度带进 runtime）。

数据形态（memos.json）:
    {"version": 1,
     "groups": [{"id": "g1a2b3", "name": "常用话术", "created_at": 1792...}],
     "memos":  [{"id": "m1a2b3", "text": "...", "title": "", "group": "g1a2b3",
                 "pinned": false, "created_at": ..., "updated_at": ...}]}
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

VERSION = 1
MAX_MEMOS = 500
MAX_GROUPS = 50
MAX_TITLE = 60
MAX_TEXT = 8000
PINNED_GROUP = "\x00pinned"


def _num(value: object, fallback: float = 0.0) -> float:
    if isinstance(value, (int, float)):
        return float(value)
    return fallback


def auto_title(text: str) -> str:
    """取第一行非空文本当标题（去掉行首的 # 和列表符号）。"""
    for raw in (text or "").splitlines():
        line = raw.strip().lstrip("#>-*+ ").strip()
        if line:
            return line[:MAX_TITLE]
    return ""


def new_id(now: float, prefix: str) -> str:
    return f"{prefix}{int(now * 1000):x}"


@dataclass(slots=True)
class MemoGroup:
    gid: str
    name: str
    created_at: float = 0.0

    def to_dict(self) -> dict[str, object]:
        return {"id": self.gid, "name": self.name, "created_at": self.created_at}


@dataclass(slots=True)
class Memo:
    mid: str
    text: str
    title: str = ""
    group: str = ""
    pinned: bool = False
    created_at: float = 0.0
    updated_at: float = 0.0

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.mid,
            "text": self.text,
            "title": self.title,
            "group": self.group,
            "pinned": self.pinned,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    def summary(self) -> dict[str, object]:
        """列表用：不带全文（面板一次拿全量，但条目多时首屏只画标题）。"""
        head = self.title or auto_title(self.text)
        return {
            "id": self.mid,
            "title": head,
            "text": self.text,
            "group": self.group,
            "pinned": self.pinned,
            "updated_at": self.updated_at,
        }


def _as_memo(item: object, now: float) -> Memo | None:
    if not isinstance(item, dict):
        return None
    text = item.get("text")
    if not isinstance(text, str) or not text.strip():
        return None
    mid = item.get("id")
    title = item.get("title")
    group = item.get("group")
    created = _num(item.get("created_at"), now)
    return Memo(
        mid=mid if isinstance(mid, str) and mid else new_id(created, "m"),
        text=text[:MAX_TEXT],
        title=(title if isinstance(title, str) else "")[:MAX_TITLE],
        group=group if isinstance(group, str) else "",
        pinned=bool(item.get("pinned", False)),
        created_at=created,
        updated_at=_num(item.get("updated_at"), created),
    )


def _as_group(item: object, now: float) -> MemoGroup | None:
    if not isinstance(item, dict):
        return None
    name = item.get("name")
    if not isinstance(name, str) or not name.strip():
        return None
    gid = item.get("id")
    created = _num(item.get("created_at"), now)
    return MemoGroup(
        gid=gid if isinstance(gid, str) and gid else new_id(created, "g"),
        name=name.strip()[:MAX_TITLE],
        created_at=created,
    )


@dataclass(slots=True)
class MemoStore:
    groups: list[MemoGroup] = field(default_factory=list)
    memos: list[Memo] = field(default_factory=list)

    # ---- 读取 -------------------------------------------------------------

    def find(self, mid: str) -> Memo | None:
        for memo in self.memos:
            if memo.mid == mid:
                return memo
        return None

    def find_group(self, gid: str) -> MemoGroup | None:
        for group in self.groups:
            if group.gid == gid:
                return group
        return None

    def group_ids(self) -> set[str]:
        return {g.gid for g in self.groups}

    def grouped(self) -> dict[str, Any]:
        """面板要的结构：置顶区 + 每个分组 + 未分组。

        排序规则：置顶按更新时间倒序；组内按更新时间倒序；组按创建顺序（新组在后）。
        """
        known = self.group_ids()
        pinned = sorted((m for m in self.memos if m.pinned), key=lambda m: m.updated_at, reverse=True)
        sections: list[dict[str, Any]] = []
        if pinned:
            sections.append(
                {
                    "id": PINNED_GROUP,
                    "name": "置顶",
                    "pinned": True,
                    "items": [m.summary() for m in pinned],
                }
            )
        for group in self.groups:
            items = [m for m in self.memos if not m.pinned and m.group == group.gid]
            items.sort(key=lambda m: m.updated_at, reverse=True)
            sections.append(
                {
                    "id": group.gid,
                    "name": group.name,
                    "pinned": False,
                    "items": [m.summary() for m in items],
                }
            )
        loose = [m for m in self.memos if not m.pinned and (m.group not in known)]
        loose.sort(key=lambda m: m.updated_at, reverse=True)
        sections.append({"id": "", "name": "未分组", "pinned": False, "items": [m.summary() for m in loose]})
        return {"sections": sections, "total": len(self.memos)}

    # ---- 写入 -------------------------------------------------------------

    def add(self, text: str, *, title: str = "", group: str = "", now: float) -> Memo | None:
        body = (text or "").strip()
        if not body:
            return None
        if group and group not in self.group_ids():
            group = ""
        memo = Memo(
            mid=new_id(now, "m"),
            text=body[:MAX_TEXT],
            title=((title or "").strip() or auto_title(body))[:MAX_TITLE],
            group=group,
            pinned=False,
            created_at=now,
            updated_at=now,
        )
        # id 撞车（同一毫秒连续新建）时加后缀，保证唯一
        while self.find(memo.mid) is not None:
            memo.mid += "x"
        self.memos.append(memo)
        self._trim()
        return memo

    def edit(self, mid: str, *, text: str | None = None, title: str | None = None, now: float) -> bool:
        memo = self.find(mid)
        if memo is None:
            return False
        changed = False
        if text is not None:
            body = text.strip()
            if body and body[:MAX_TEXT] != memo.text:
                memo.text = body[:MAX_TEXT]
                changed = True
        if title is not None:
            head = title.strip()[:MAX_TITLE]
            if head != memo.title:
                memo.title = head
                changed = True
        if changed:
            memo.updated_at = now
        return changed

    def delete(self, mid: str) -> bool:
        for idx, memo in enumerate(self.memos):
            if memo.mid == mid:
                del self.memos[idx]
                return True
        return False

    def toggle_pin(self, mid: str) -> bool | None:
        memo = self.find(mid)
        if memo is None:
            return None
        memo.pinned = not memo.pinned
        return memo.pinned

    def move(self, mid: str, group: str) -> bool:
        memo = self.find(mid)
        if memo is None:
            return False
        target = group if group in self.group_ids() else ""
        if target == memo.group:
            return False
        memo.group = target
        return True

    def add_group(self, name: str, now: float) -> MemoGroup | None:
        clean = (name or "").strip()[:MAX_TITLE]
        if not clean:
            return None
        for group in self.groups:
            if group.name == clean:
                return group
        if len(self.groups) >= MAX_GROUPS:
            return None
        group = MemoGroup(gid=new_id(now, "g"), name=clean, created_at=now)
        while self.find_group(group.gid) is not None:
            group.gid += "x"
        self.groups.append(group)
        return group

    def rename_group(self, gid: str, name: str) -> bool:
        group = self.find_group(gid)
        clean = (name or "").strip()[:MAX_TITLE]
        if group is None or not clean:
            return False
        if any(g.gid != gid and g.name == clean for g in self.groups):
            return False
        group.name = clean
        return True

    def delete_group(self, gid: str) -> bool:
        """删组不删条目：组里的备忘退回「未分组」。"""
        for idx, group in enumerate(self.groups):
            if group.gid == gid:
                del self.groups[idx]
                for memo in self.memos:
                    if memo.group == gid:
                        memo.group = ""
                return True
        return False

    def _trim(self) -> None:
        """超出上限时丢最旧的未置顶条目，置顶永不丢。"""
        if len(self.memos) <= MAX_MEMOS:
            return
        ordered = sorted(self.memos, key=lambda m: (m.pinned, m.updated_at))
        drop = len(self.memos) - MAX_MEMOS
        removed: set[str] = set()
        for memo in ordered:
            if drop <= 0:
                break
            if memo.pinned:
                continue
            removed.add(memo.mid)
            drop -= 1
        if removed:
            self.memos = [m for m in self.memos if m.mid not in removed]


def parse_store(raw: str, now: float) -> MemoStore:
    try:
        data = json.loads(raw)
    except ValueError:
        return MemoStore()
    if not isinstance(data, dict):
        return MemoStore()
    groups: list[MemoGroup] = []
    for item in data.get("groups") or []:
        group = _as_group(item, now)
        if group is not None:
            groups.append(group)
    memos: list[Memo] = []
    for item in data.get("memos") or []:
        memo = _as_memo(item, now)
        if memo is not None:
            memos.append(memo)
    store = MemoStore(groups=groups, memos=memos)
    # 指向已删分组的条目退回未分组
    known = store.group_ids()
    for memo in store.memos:
        if memo.group and memo.group not in known:
            memo.group = ""
    return store


def dump_store(store: MemoStore) -> str:
    return json.dumps(
        {
            "version": VERSION,
            "groups": [g.to_dict() for g in store.groups],
            "memos": [m.to_dict() for m in store.memos],
        },
        ensure_ascii=False,
        indent=2,
    )
