"""配置文件的写回（mascot config set）。

读的方向由 pydantic-settings 负责；写回来只支持扁平键 = 标量 / 元组，
也就是 Settings 里真实存在的那些字段。读用 tomllib（3.11 内置），
写用本模块的极简序列化（每行 key = value），够人读、也够再读回来。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from mascot_core.config import Settings, default_config_path

BACKSLASH = chr(92)
QUOTE = chr(34)
NEWLINE = chr(10)


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


def write_config_file(values: dict[str, object], path: Path | None = None) -> Path:
    """原子写回（tmp + replace）。只写已知键，顺序按 Settings 字段顺序。"""
    target = path or default_config_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    lines = ["# mascot 配置（由 mascot config set 维护，也可手工编辑）", ""]
    for key in known_keys():
        if key in values:
            lines.append(key + " = " + _toml_literal(values[key]))
    tmp = target.with_suffix(".toml.tmp")
    tmp.write_text(NEWLINE.join(lines) + NEWLINE, encoding="utf-8")
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
