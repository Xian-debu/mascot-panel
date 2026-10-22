"""配置文件的写回（mascot config set）。

读的方向由 pydantic-settings 负责；写回来只支持扁平键 = 标量 / 元组，
也就是 Settings 里真实存在的那些字段。读用 tomllib（3.11 内置）。

写回是**按行编辑**而不是整份重建：注释、空行、未知键、`[table]` 段都原样保留，
只改 `mascot config set` 点到的那一行（没有就补在扁平键区末尾，绝不到表之后）。
这样手工维护的配置不会因为一次 `config set` 被洗成默认模板。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from mascot_core.config import Settings, default_config_path

BACKSLASH = chr(92)
QUOTE = chr(34)
NEWLINE = chr(10)
HEADER = "# mascot 配置（由 mascot config set 维护，也可手工编辑）"


def known_keys() -> tuple[str, ...]:
    """Settings 支持的配置文件键（顺序稳定，便于 config show 输出）。"""
    return tuple(Settings.model_fields)


def coerce_value(key: str, raw: str) -> object:
    """把命令行字符串转成该字段的类型；不认识就抛 ValueError（带可读原因）。"""
    field = Settings.model_fields.get(key)
    if field is None:
        raise ValueError("unknown config key: " + key)
    text = raw.strip()
    annotation = field.annotation
    if annotation is bool:
        lowered = text.lower()
        if lowered in {"1", "true", "yes", "on"}:
            return True
        if lowered in {"0", "false", "no", "off"}:
            return False
        raise ValueError(key + " expects a boolean, got " + repr(raw))
    if annotation is int:
        try:
            return int(text)
        except ValueError as exc:
            raise ValueError(key + " expects an integer, got " + repr(raw)) from exc
    if annotation is float:
        try:
            return float(text)
        except ValueError as exc:
            raise ValueError(key + " expects a number, got " + repr(raw)) from exc
    if annotation is Path:
        return Path(text)
    if annotation is str:
        return text
    origin = getattr(annotation, "__origin__", None)
    if origin is tuple:
        parts = [part.strip() for part in text.split(",") if part.strip()]
        args = getattr(annotation, "__args__", ())
        elem = args[0] if args else str
        if elem is int:
            try:
                return tuple(int(part) for part in parts)
            except ValueError as exc:
                raise ValueError(key + " expects integers separated by commas, got " + repr(raw)) from exc
        return tuple(parts)
    return text


def _toml_literal(value: object) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return repr(value)
    if isinstance(value, (tuple, list)):
        return "[" + ", ".join(_toml_literal(item) for item in value) + "]"
    text = str(value).replace(BACKSLASH, BACKSLASH * 2).replace(QUOTE, BACKSLASH + QUOTE)
    return QUOTE + text + QUOTE


def read_config_file(path: Path | None = None) -> dict[str, object]:
    """读现有 TOML（不存在返回空 dict）。读不了抛 ValueError，调用方决定是否降级。"""
    import tomllib

    target = path or default_config_path()
    if not target.is_file():
        return {}
    try:
        with target.open("rb") as handle:
            data = tomllib.load(handle)
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise ValueError("cannot read " + str(target) + ": " + str(exc)) from exc
    return dict(data)


def _comment_index(line: str) -> int:
    """返回行内注释 `#` 的位置（引号里的不算），没有返回 -1。"""
    quote = ""
    escaped = False
    for index, char in enumerate(line):
        if escaped:
            escaped = False
            continue
        if char == BACKSLASH and quote:
            escaped = True
            continue
        if quote:
            if char == quote:
                quote = ""
            continue
        if char in {chr(34), chr(39)}:
            quote = char
            continue
        if char == "#":
            return index
    return -1


def _bare_key(line: str) -> str | None:
    """若该行是扁平键赋值（`key = ...`），返回键名；表头/注释/其它返回 None。"""
    body = line.strip()
    if not body or body.startswith("#") or body.startswith("["):
        return None
    cut = _comment_index(body)
    if cut >= 0:
        body = body[:cut]
    if "=" not in body:
        return None
    key = body.split("=", 1)[0].strip()
    if not key or not key.replace("_", "").replace("-", "").isalnum():
        return None
    return key


def _render(values: dict[str, object], existing: str | None) -> str:
    """按行改：替换已存在的已知键、删掉不在 values 里的已知键、补齐缺的键。"""
    if existing is None:
        lines = [HEADER, ""]
        for key in known_keys():
            if key in values:
                lines.append(key + " = " + _toml_literal(values[key]))
        return NEWLINE.join(lines) + NEWLINE

    out: list[str] = []
    seen: set[str] = set()
    in_table = False
    insert_at: int | None = None  # 扁平键区最后一个已知键之后的位置
    for line in existing.splitlines():
        body = line.strip()
        if body.startswith("["):
            in_table = True
        key = None if in_table else _bare_key(line)
        if key is None or key not in Settings.model_fields:
            out.append(line)
            continue
        if key in seen:  # 重复键：只留第一处，后面删掉
            continue
        seen.add(key)
        if key not in values:
            insert_at = len(out) - 1
            continue
        cut = _comment_index(line)
        comment = ""
        if cut >= 0:
            spaces = len(line[:cut]) - len(line[:cut].rstrip())
            comment = " " * max(1, spaces) + line[cut:]
        out.append(key + " = " + _toml_literal(values[key]) + comment)
        insert_at = len(out) - 1

    missing = [
        key + " = " + _toml_literal(values[key])
        for key in known_keys()
        if key in values and key not in seen
    ]
    if missing:
        # 必须插在第一个 `[table]` 之前，否则会被 TOML 当成表内的键
        pivot = len(out)
        for index, line in enumerate(out):
            if line.strip().startswith("["):
                pivot = index
                break
        at = insert_at + 1 if insert_at is not None and insert_at < pivot else pivot
        out = out[:at] + missing + out[at:]
    text = NEWLINE.join(out)
    return text if text.endswith(NEWLINE) else text + NEWLINE


def write_config_file(values: dict[str, object], path: Path | None = None) -> Path:
    """原子写回（tmp + replace）。保留注释、未知键与 `[table]` 段。"""
    target = path or default_config_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    existing: str | None = None
    if target.is_file():
        try:
            existing = target.read_text(encoding="utf-8")
        except OSError as exc:
            raise ValueError("cannot read " + str(target) + ": " + str(exc)) from exc
    text = _render(values, existing)
    tmp = target.with_suffix(".toml.tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(target)
    return target


def set_config_value(key: str, raw: str, path: Path | None = None) -> tuple[Path, object]:
    """写一个键并返回 (路径, 新值)。值先过 Settings 校验，非法就不落盘。"""
    value = coerce_value(key, raw)
    current = read_config_file(path)
    current[key] = value
    payload: dict[str, Any] = {key: value}
    Settings(**payload)
    return write_config_file(current, path), value


def unset_config_value(key: str, path: Path | None = None) -> bool:
    """删一个键；返回是否真的删掉了（键本来不在就返回 False）。"""
    if key not in Settings.model_fields:
        raise ValueError("unknown config key: " + key)
    current = read_config_file(path)
    if key not in current:
        return False
    current.pop(key)
    write_config_file(current, path)
    return True
