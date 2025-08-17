import uvicorn

from trae_api.core.config import settings
from trae_api.core.gunicorn import GunicornApplication


def main() -> None:
    """Entrypoint of the application."""
    if settings.reload:
        uvicorn.run(
            "trae_api.core.application:get_app",
            workers=settings.workers_count,
            host=settings.host,
            port=settings.port,
            reload=settings.reload,
            log_level=settings.log_level.value.lower(),
            factory=True,
        )
    else:
        # We choose gunicorn only if reload
        # option is not used, because reload
        # feature doesn't work with gunicorn workers.
        GunicornApplication(
            "trae_api.core.application:get_app",
            host=settings.host,
            port=settings.port,
            workers=settings.workers_count,
            factory=True,
            accesslog="-",
            loglevel=settings.log_level.value.lower(),
            access_log_format='%r "-" %s "-" %Tf',
        ).run()


if __name__ == "__main__":
    main()
