from typing import Any

from gunicorn.app.base import BaseApplication
from gunicorn.util import import_app
from uvicorn.workers import UvicornWorker as BaseUvicornWorker

try:
    import uvloop  # (Found nested import)
except ImportError:
    uvloop = None  # type: ignore  # (variables overlap)


class UvicornWorker(BaseUvicornWorker):
    """
    Configuration for uvicorn workers.

    This class is subclassing UvicornWorker and defines
    some parameters class-wide, because it's impossible,
    to pass these parameters through gunicorn.
    """

    CONFIG_KWARGS: dict[str, Any] = {  # typing: ignore  # noqa: RUF012
        "loop": "uvloop" if uvloop is not None else "asyncio",
        "http": "httptools",
        "lifespan": "on",
        "factory": True,
        "proxy_headers": False,
    }


class GunicornApplication(BaseApplication):
    """
    Custom gunicorn application.

    This class is used to start guncicorn
    with custom uvicorn workers.
    """

    def __init__(  # (Too many args)
        self,
        app: str,
        host: str,
        port: int,
        workers: int,
        **kwargs: Any,
    ) -> None:
        self.options = {
            "bind": f"{host}:{port}",
            "workers": workers,
            "worker_class": "trae_api.core.gunicorn.UvicornWorker",
            **kwargs,
        }
        self.app = app
        super().__init__()

    def load_config(self) -> None:
        """
        Load config for web server.

        This function is used to set parameters to gunicorn
        main process. It only sets parameters that
        gunicorn can handle. If you pass unknown
        parameter to it, it crash with error.
        """
        for key, value in self.options.items():
            if key in self.cfg.settings and value is not None:
                self.cfg.set(key.lower(), value)

    def load(self) -> str:
        """
        Load actual application.

        Gunicorn loads application based on this
        function's returns. We return python's path to
        the app's factory.

        :returns: python path to app factory.
        """
        return import_app(self.app)
