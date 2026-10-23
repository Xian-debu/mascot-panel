"""会话回收站（C4）：删掉的会话先扔这里，能恢复，也能彻底删。

为什要单独一个文件：`sessions.json` 是"当前会话"的唯一真源，回收站是另一份
低风险的存档（写坏了也不会影响主数据）；删掉的会话正文不留在主文件里，
避免"删了还占着"和回滚备份混淆。

纯逻辑：不碰文件系统、不读时钟（now 由调用方传入）。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

from mascot_core.sessions import (
    DEFAULT_TITLE,
    MAX_TITLE,
    Session,
    _as_session,
)

VERSION = 1
MAX_ITEMS = 30


@dataclass(slots=True)
class TrashItem:
    session: Session
    deleted_at: float = 0.0

    def to_dict(self) -> dict[str, object]:
        data = self.session.to_dict()
        data["deleted_at"] = self.deleted_at
        return data

    def summary(self) -> dict[str, object]:
        """回收站一行：会话名 + 条数 + 删除时间（不带正文）。"""
        return {
            "id": self.session.sid,
            "title": self.session.title,
            "count": len(self.session.messages),
            "deleted_at": self.deleted_at,
            "updated_at": self.session.updated_at,
        }


@dataclass(slots=True)
class Trash:
    items: list[TrashItem] = field(default_factory=list)

    def find(self, sid: str) -> TrashItem | None:
        for item in self.items:
            if item.session.sid == sid:
                return item
        return None

    def add(self, session: Session, now: float, limit: int = MAX_ITEMS) -> None:
        """放进回收站；同一个会话重复删只留一条。超过上限丢最旧的。"""
        self.items = [it for it in self.items if it.session.sid != session.sid]
        self.items.append(TrashItem(session=session, deleted_at=now))
        if len(self.items) > limit:
            self.items = self.items[-limit:]

    def restore(self, sid: str) -> Session | None:
        """取出会话本体（从回收站移除）；找不到返回 None。"""
        for idx, item in enumerate(self.items):
            if item.session.sid == sid:
                del self.items[idx]
                return item.session
        return None

    def purge(self, sid: str) -> bool:
        before = len(self.items)
        self.items = [it for it in self.items if it.session.sid != sid]
        return len(self.items) != before

    def summaries(self) -> list[dict[str, object]]:
        """最近删的排前面。"""
        return [it.summary() for it in sorted(self.items, key=lambda i: i.deleted_at, reverse=True)]


def parse_trash(raw: str, now: float) -> Trash:
    """读盘：坏 JSON / 坏条目一律跳过（回收站坏了不影响主会话）。"""
    trash = Trash()
    try:
        data = json.loads(raw)
    except (ValueError, TypeError):
        return trash
    if not isinstance(data, dict):
        return trash
    items = data.get("items")
    seen: set[str] = set()
    for item in items if isinstance(items, list) else []:
        session = _as_session(item, now, seen)
        if session is None:
            continue
        seen.add(session.sid)
        deleted = item.get("deleted_at") if isinstance(item, dict) else 0.0
        trash.items.append(
            TrashItem(
                session=session,
                deleted_at=float(deleted) if isinstance(deleted, (int, float)) else session.updated_at,
            )
        )
    return trash


def dump_trash(trash: Trash) -> str:
    return json.dumps(
        {
            "version": VERSION,
            "items": [it.to_dict() for it in trash.items],
        },
        ensure_ascii=False,
        separators=(",", ":"),
    )


__all__ = [
    "DEFAULT_TITLE",
    "MAX_ITEMS",
    "MAX_TITLE",
    "Trash",
    "TrashItem",
    "VERSION",
    "dump_trash",
    "parse_trash",
]
