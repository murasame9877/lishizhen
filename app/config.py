"""集中配置。所有可调参数走环境变量，避免写死在业务代码里（NFR-08）。"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from zoneinfo import ZoneInfo

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    wechat_token: str = "dev-token"
    wechat_appid: str = ""
    wechat_appsecret: str = ""
    wechat_encrypt_mode: str = "plain"  # plain | compatible | safe
    public_base_url: str = "http://localhost:8000"

    db_path: str = "data/sdg.sqlite3"
    tz: str = "Asia/Shanghai"
    confidence_threshold: float = 0.8
    sync_interval_min: int = 10

    worker_enabled: bool = True
    worker_poll_seconds: float = 1.0
    wechat_push_enabled: bool = True
    wechat_api_base: str = "https://api.weixin.qq.com"

    article_timeout: float = 15.0
    ocr_enabled: bool = True
    ocr_min_score: float = 0.3
    ocr_timeout: float = 90.0
    image_max_bytes: int = 10 * 1024 * 1024
    image_retention_days: int = 7
    article_max_chars: int = 12000
    article_user_agent: str = ""

    # 手机分享目标（HTTP Shortcuts / 自建 App）
    share_ingest_token: str = ""
    share_user_openid: str = ""

    # 企业微信「微信客服」：官方聊天对象，主动拉取消息
    wecom_kf_enabled: bool = False
    wecom_corp_id: str = ""
    wecom_kf_secret: str = ""
    wecom_kf_id: str = ""
    wecom_kf_user_openid: str = ""
    wecom_kf_poll_seconds: float = 2.0
    wecom_agent_id: str = ""

    radicale_enabled: bool = True
    radicale_internal_url: str = "http://127.0.0.1:5232"
    radicale_prefix: str = "/radicale"

    caldav_url: str = ""
    caldav_internal_url: str = "http://127.0.0.1:8000/radicale/"
    caldav_username: str = ""
    caldav_password: str = ""
    caldav_calendar_name: str = "日程Agent"
    caldav_timeout: float = 5.0
    sync_scheduler_enabled: bool = True

    llm_provider: str = "none"
    llm_api_key: str = ""
    llm_base_url: str = ""
    llm_model: str = ""

    # 现场演示：只有白名单 openid 会写入系统日历，观众只在微信内体验
    demo_mode: bool = False
    caldav_sync_openids: str = ""

    @property
    def image_dir(self) -> Path:
        return Path(self.db_path).resolve().parent / "images"

    @property
    def timezone(self) -> ZoneInfo:
        return ZoneInfo(self.tz)

    @property
    def caldav_sync_openid_set(self) -> set[str]:
        return {
            item.strip()
            for item in self.caldav_sync_openids.split(",")
            if item.strip()
        }


def is_calendar_enabled(settings: Settings, openid: str) -> bool:
    if not settings.demo_mode:
        return True
    return openid in settings.caldav_sync_openid_set


@lru_cache
def get_settings() -> Settings:
    return Settings()
