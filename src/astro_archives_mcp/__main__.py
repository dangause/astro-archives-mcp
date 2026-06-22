import sys

import uvicorn

from astro_archives_mcp.app import build_app, build_mcp
from astro_archives_mcp.config import Settings
from astro_archives_mcp.observability import configure_logging


def main() -> None:
    stdio = "--stdio" in sys.argv

    settings = Settings()
    configure_logging(settings.log_level)

    if stdio:
        build_mcp().run(transport="stdio")
    else:
        uvicorn.run(
            build_app(),
            host=settings.host,
            port=settings.port,
            log_config=None,
            access_log=False,
        )


if __name__ == "__main__":
    main()
