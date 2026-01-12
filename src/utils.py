import base64
import logging
import re

import httpx

# API Constants from AGENTS.md
BASE_URL = base64.b64decode("aHR0cHM6Ly9lcy53YWxsYXBvcC5jb20v").decode()
USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64; rv:146.0) Gecko/20100101 Firefox/146.0"

logger = logging.getLogger("marketplace-server")


async def get_app_version() -> str:
    """Fetch the current app version from marketplace website using regex."""

    logger.info("Fetching app version from %s", BASE_URL)
    headers = {"User-Agent": USER_AGENT}

    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(BASE_URL, headers=headers)
            response.raise_for_status()

            match = re.search(r'data-app-version="([^"]+)"', response.text)
            if match:
                version = match.group(1)
                formatted_version = version.replace(".", "")
                logger.info(
                    "Detected app version: %s (formatted: %s)",
                    version,
                    formatted_version,
                )
                return formatted_version

            logger.warning("App version not found in HTML, using fallback")
            return "814910"  # Fallback
        except Exception as exc:
            logger.error("Failed to fetch app version: %s", exc)
            return "814910"  # Fallback
