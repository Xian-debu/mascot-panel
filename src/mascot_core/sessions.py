"""本地多会话存储（`sessions.json` 是唯一真源）。

旧实现只有一份 `history.json`（一段对话，跨重启保留）。B1 起改成多会话：
每个会话有独立的消息列表，面板顶部的会话抽屉负责新建/切换/重命名/删除。

纯逻辑：不碰文件系统、不读系统时钟（now 由调用方传入）。
任何坏数据都降级成"至少一个空会话"，绝不让桌宠因为聊天记录坏了起不来。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

from mascot_core.contract import Message
from mascot_core.history import parse_messages

VERSION = 1
DEFAULT_TITLE = "新的对话"
MAX_TITLE = 40
MAX_SESSIONS = 200


def auto_title(text: str) -> str:
    """用第一行非空文本当标题（按字符截断，中文 40 字已够面板显示）。"""
    for line in (text or "").splitlines():
        clean = " ".join(line.split())
        if clean:
            return clean[:MAX_TITLE]
    return DEFAULT_TITLE


@dataclass(slots=True)
class Session:
    sid: str
    title: str = DEFAULT_TITLE
    created_at: float = 0.0
    updated_at: float = 0.0
    messages: list[Message] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.sid,
            "title": self.title,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "messages": [m.to_dict() for m in self.messages],
        }

    def summary(self, *, current: bool) -> dict[str, object]:
        """抽屉里一行需要的全部信息（不含正文，快照不因会话多而膨胀）。"""
        last = self.messages[-1].text if self.messages else ""
        return {
            "id": self.sid,
            "title": self.title,
            "updated_at": self.updated_at,
            "count": len(self.messages),
            "preview": " ".join(last.split())[:60],
            "current": current,
        }


@dataclass(slots=True)
class SessionStore:
    sessions: list[Session] = field(default_factory=list)
    current_id: str = ""

    # ---- 读取 -------------------------------------------------------------

    def find(self, sid: str) -> Session | None:
        for session in self.sessions:
            if session.sid == sid:
                return session
        return None

    def current(self) -> Session:
        """当前会话；current_id 失效时退到最近更新的那个。"""
        found = self.find(self.current_id)
        if found is not None:
            return found
        newest = max(self.sessions, key=lambda s: s.updated_at)
        self.current_id = newest.sid
        return newest

    def summaries(self) -> list[dict[str, object]]:
        current = self.current_id
        rows = [(s.updated_at, s.summary(current=s.sid == current)) for s in self.sessions]
        rows.sort(key=lambda item: item[0], reverse=True)
        return [row for _, row in rows]

    # ---- 写入 -------------------------------------------------------------

    def create(self, now: float, title: str = "") -> Session:
        sid = new_sid({s.sid for s in self.sessions}, now)
        session = Session(
            sid=sid,
            title=(title.strip()[:MAX_TITLE] or DEFAULT_TITLE),
            created_at=now,
            updated_at=now,
        )
        self.sessions.append(session)
        self.current_id = sid
        # 会话再多也不让抽屉无限长：丢最久没动的（当前会话永不丢）
        if len(self.sessions) > MAX_SESSIONS:
            # 排序键把当前会话压到最后（True > False），再取尾 —— 当前会话永不被裁掉
            keep = sorted(self.sessions, key=lambda s: (s.sid == self.current_id, s.updated_at))
            self.sessions = keep[-MAX_SESSIONS:]
        return session

    def switch(self, sid: str) -> bool:
        if self.find(sid) is None:
            return False
        self.current_id = sid
        return True

    def rename(self, sid: str, title: str) -> bool:
        session = self.find(sid)
        clean = " ".join((title or "").split())[:MAX_TITLE]
        if session is None or not clean:
            return False
        session.title = clean
        return True

    def delete(self, sid: str, now: float) -> bool:
        """删会话；删掉的正好是当前会话就切到最近更新的一条。

        永远至少留一个会话：删掉最后一个时立刻补一个空白会话，
        避免面板出现"没有会话"的中间态。
        """
        session = self.find(sid)
        if session is None:
            return False
        self.sessions = [s for s in self.sessions if s.sid != sid]
        if not self.sessions:
            self.create(now)
        elif self.current_id == sid:
            self.current()  # current_id 已失效 → 自动落到最近更新的会话
        return True

    def touch(self, now: float) -> None:
        session = self.current()
        session.updated_at = max(now, session.updated_at)

    def title_from(self, text: str) -> None:
        """还没改过名的会话：用第一句用户消息当标题。"""
        session = self.current()
        if session.title == DEFAULT_TITLE and not session.messages:
            session.title = auto_title(text)


def new_sid(existing: set[str], now: float) -> str:
    base = f"s{int(now * 1000):x}"
    sid, n = base, 1
    while sid in existing:
        n += 1
        sid = f"{base}-{n}"
    return sid


def _as_session(item: object, now: float, seen: set[str]) -> Session | None:
    if not isinstance(item, dict):
        return None
    sid = item.get("id")
    if not isinstance(sid, str) or not sid or sid in seen:
        sid = new_sid(seen, now)
    raw_title = item.get("title")
    title = " ".join(raw_title.split())[:MAX_TITLE] if isinstance(raw_title, str) else ""
    created = _num(item.get("created_at"), now)
    updated = _num(item.get("updated_at"), created)
    return Session(
        sid=sid,
        title=title or DEFAULT_TITLE,
        created_at=created,
        updated_at=updated,
        messages=parse_messages(item.get("messages")),
    )


def _num(value: object, fallback: float) -> float:
    return float(value) if isinstance(value, (int, float)) else fallback


def parse_store(raw: str, now: float) -> SessionStore:
    """读盘：坏 JSON / 坏条目都跳过，最后保证"至少一个当前会话"。"""
    store = SessionStore()
    try:
        data = json.loads(raw)
    except (ValueError, TypeError):
        return ensure(store, now)
    if not isinstance(data, dict):
        return ensure(store, now)
    items = data.get("sessions")
    seen: set[str] = set()
    for item in items if isinstance(items, list) else []:
        session = _as_session(item, now, seen)
        if session is not None:
            store.sessions.append(session)
            seen.add(session.sid)
    current = data.get("current")
    if isinstance(current, str) and current in seen:
        store.current_id = current
    return ensure(store, now)


def ensure(store: SessionStore, now: float) -> SessionStore:
    if not store.sessions:
        store.create(now)
    elif store.find(store.current_id) is None:
        store.current()
    return store


def from_history(messages: list[Message], now: float) -> SessionStore:
    """迁移旧 history.json：整段对话变成第一个会话。"""
    store = SessionStore()
    session = store.create(now)
    session.messages = list(messages)
    first_user = next((m.text for m in messages if m.role == "user"), "")
    session.title = auto_title(first_user) if first_user else DEFAULT_TITLE
    return store


def dump_store(store: SessionStore) -> str:
    return json.dumps(
        {
            "version": VERSION,
            "current": store.current_id,
            "sessions": [s.to_dict() for s in store.sessions],
        },
        ensure_ascii=False,
        indent=2,
    )
