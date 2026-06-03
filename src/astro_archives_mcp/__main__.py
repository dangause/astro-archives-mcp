import uvicorn

from astro_archives_mcp.app import build_app
from astro_archives_mcp.config import Settings
from astro_archives_mcp.observability import configure_logging


def main() -> None:
    settings = Settings()
    configure_logging(settings.log_level)
    uvicorn.run(
        build_app(),
        host=settings.host,
        port=settings.port,
        log_config=None,
        access_log=False,
    )


if __name__ == "__main__":
    main()
