"""把 Radicale 以 WSGI 形式挂载到 FastAPI，共用同一个公网端口。

这样零预算方案只需要一条隧道：
    https://<tunnel>/wechat    微信回调
    https://<tunnel>/radicale/ 手机 CalDAV

Radicale 只有在第一次访问 /radicale 时才初始化，避免测试或只跑微信链路时
在磁盘上创建无关目录。
"""

from __future__ import annotations

import threading
from pathlib import Path

from app.config import Settings

_PROJECT_ROOT = Path(__file__).resolve().parents[2]


class LazyRadicale:
    def __init__(self, settings: Settings, config_path: Path | None = None) -> None:
        self._settings = settings
        self._config_path = config_path or (
            _PROJECT_ROOT / "deploy" / "radicale.conf"
        )
        self._app = None
        self._lock = threading.Lock()

    def _build(self):
        from radicale import config as radicale_config
        from radicale.app import Application

        data_dir = Path(self._settings.db_path).resolve().parent
        configuration = radicale_config.load([(str(self._config_path), False)])
        configuration.update(
            {
                "auth": {"htpasswd_filename": str(data_dir / "users")},
                "storage": {"filesystem_folder": str(data_dir / "radicale")},
            },
            "sdg app config",
        )
        return Application(configuration)

    def __call__(self, environ, start_response):
        if self._app is None:
            with self._lock:
                if self._app is None:
                    self._app = self._build()
        return self._app(environ, start_response)
