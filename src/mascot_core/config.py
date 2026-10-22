"""配置：TOML 文件 + `MASCOT_` 前缀环境变量 + 默认值，三级覆盖。

旧实现把 6 类值硬编码在代码里（发行版名、路径、端口、窗口类名、进程名、超时），
这里全部收进一个可 dump 的 Settings —— `mascot doctor` 会把它原样打印出来。
"""

from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
    TomlConfigSettingsSource,
)

from mascot_core.paths import state_dir


def default_config_path() -> Path:
    """状态目录（MASCOT_STATE_DIR / %LOCALAPPDATA%/mascot / ~/.mascot）下的 config.toml。"""
    return state_dir() / "config.toml"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="MASCOT_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # 窗口与跟随
    panel_size: tuple[int, int] = (340, 460)
    follow_offset: tuple[int, int] = (210, -130)
    poll_interval_ms: int = Field(default=300, ge=50, le=2000)
    lost_frames: int = Field(default=3, ge=1, le=10)

    # 宠物窗口（旧实现硬编码）
    pet_window_class: str = "TX Mascot"
    pet_process_names: tuple[str, ...] = ("TX Mascot.exe", "TXPet.exe", "TX Pets.exe")

    # 环绕球
    ball_ratio: float = Field(default=0.34, gt=0.05, lt=1.0)
    orbit_gap: int = 10
    orbit_period_s: float = Field(default=12.0, gt=1.0)
    orbit_speed: float = Field(default=1.0, gt=0.0, le=5.0)
    fps: int = Field(default=10, ge=1, le=60)

    # 跨环境
    # deepseek：直连 api.deepseek.com（key 只从环境变量 DEEPSEEK_AUTH_TOKEN 读，见 providers/deepseek.py）；
    # auto/legacy/wsl 保留给旧后端，null = 纯离线。
    provider: str = "deepseek"
    provider_base_url: str = "https://api.deepseek.com"
    provider_model: str = "deepseek-chat"
    provider_timeout_s: float = Field(default=120.0, gt=0.1)
    # health 是启动路径上的串行探测，要容忍公网抖动；仍比业务超时短得多
    health_timeout_s: float = Field(default=3.0, gt=0.05, le=10.0)
    allow_offline: bool = True

    # 日志
    log_level: str = "INFO"
    log_dir: Path | None = None

    # 历史
    history_limit: int = Field(default=50, ge=5, le=500)

    # 交互
    # 待机球双击时间窗（毫秒）：0 = 关闭双击手势，单击立即开面板（M28）
    click_window_ms: int = Field(default=350, ge=0, le=2000)

    # 功能开关（默认全关的开关必须在这里显式列出）
    notify_pulse: bool = True
    agent_inbox: bool = False

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        return (init_settings, env_settings, dotenv_settings, file_secret_settings)


# 能在运行中安全替换的字段：每次 tick / poll 都从 self.settings 重新读，换了立刻生效。
# 其余字段（panel_size、provider、pet_window_class …）牵涉窗口/后端重建，只能重启生效。
HOT_FIELDS = (
    "fps",
    "poll_interval_ms",
    "orbit_speed",
    "orbit_period_s",
    "ball_ratio",
    "orbit_gap",
    "follow_offset",
    "lost_frames",
    "notify_pulse",
    "history_limit",
    "click_window_ms",
)


def merge_hot(old: Settings, new: Settings) -> tuple[Settings, list[str]]:
    """把 new 里的热字段套到 old 上；返回 (合并结果, 需要重启才生效的字段名)。"""
    hot = {name: getattr(new, name) for name in HOT_FIELDS}
    merged = old.model_copy(update=hot)
    restart = sorted(
        name
        for name in type(old).model_fields
        if name not in HOT_FIELDS and getattr(old, name) != getattr(new, name)
    )
    return merged, restart


def load_settings(config_file: Path | None = None) -> Settings:
    """显式传入路径时读该 TOML；否则读默认位置（不存在则用默认值）。"""
    path = config_file or default_config_path()
    if path.is_file():
        class _WithToml(Settings):
            @classmethod
            def settings_customise_sources(cls, settings_cls, init_settings, env_settings,
                                           dotenv_settings, file_secret_settings):
                return (
                    init_settings,
                    env_settings,
                    dotenv_settings,
                    file_secret_settings,
                    TomlConfigSettingsSource(settings_cls, toml_file=path),
                )

        return _WithToml()
    return Settings()
