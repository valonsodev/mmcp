import argparse
import asyncio
import base64
import logging
import os
from typing import Any, Iterable, Optional

import httpx
from mcp.server.fastmcp import FastMCP

from src.models import MarketplaceItem
from src.utils import get_app_version

LOG_FILE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "marketplace.log"
)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    filename=LOG_FILE,
    filemode="w",
)
logger = logging.getLogger("marketplace-server")

mcp = FastMCP("marketplace")

API_URL = base64.b64decode(
    "aHR0cHM6Ly9hcGkud2FsbGFwb3AuY29tL2FwaS92My9zZWFyY2g="
).decode()
USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64; rv:146.0) Gecko/20100101 Firefox/146.0"

# Output mode (configurable via CLI: -d / --descriptions / --no-descriptions)
# - True: `search` includes a short description snippet; `description` tool returns error.
# - False: `search` omits descriptions; `description` tool returns cached descriptions.
INCLUDE_DESCRIPTION_IN_SEARCH = True
# How many pages to fetch per query in `search` (configurable via CLI: -p / --pages)
SEARCH_PAGES_TO_FETCH = 5

APP_VERSION: Optional[str] = None

# Global caches
ITEM_WEB_SLUG_CACHE: dict[str, str] = {}  # item id -> web_slug
ITEM_DESCRIPTION_CACHE: dict[str, str] = {}  # item id -> description

# Default coordinates
DEFAULT_LAT = 43.3707332
DEFAULT_LON = -8.3958532


def format_item_markdown(item: MarketplaceItem) -> Optional[str]:
    if item.reserved.flag is True:
        return None

    title = " ".join(item.title.split())
    price = f"{item.price.amount}€" if item.price.amount is not None else "N/A"
    line = f"- `{item.id}` {title} - {price}"

    if INCLUDE_DESCRIPTION_IN_SEARCH and item.description:
        line += f"\n  {' '.join(item.description.split())}"

    return line


@mcp.tool()
async def link(item_ids: list[str]) -> str:
    """Return Marketplace URLs for the given item ids."""

    if not item_ids or not isinstance(item_ids, list):
        return "Invalid item_ids: provide a non-empty list of ids"

    lines: list[str] = []
    for item_id in item_ids:
        slug = ITEM_WEB_SLUG_CACHE.get(str(item_id))
        if not slug:
            lines.append(
                f"- `{item_id}`: Unknown id. Run `search` first to populate the cache."
            )
            continue

        item_base = base64.b64decode(
            "aHR0cHM6Ly9lcy53YWxsYXBvcC5jb20vaXRlbS8="
        ).decode()
        lines.append(f"- `{item_id}`: {item_base}{slug}")

    return "\n".join(lines)


@mcp.tool()
async def description(item_ids: list[str]) -> str:
    """Return descriptions for the given item ids."""

    if INCLUDE_DESCRIPTION_IN_SEARCH:
        return "Tool disabled: descriptions are already included in `search` results."

    if not item_ids or not isinstance(item_ids, list):
        return "Invalid item_ids: provide a non-empty list of ids"

    results: list[str] = []
    for item_id in item_ids:
        cached = ITEM_DESCRIPTION_CACHE.get(str(item_id))
        if cached and cached.strip():
            results.append(f"- `{item_id}`\n\n{cached.strip()}")
            continue

        results.append(f"- `{item_id}`: Description not in cache")

    return "\n\n---\n\n".join(results)


@mcp.tool()
async def search(query: list[str]) -> str:
    """Search marketplace listings by **keywords**.

    Use this tool when you want to discover items that match a product name, model,
    or a small set of descriptive terms.

    How to search (preferred patterns):
    - Prefer **specific keywords** over long sentences (brand + model + key specs).
    - The marketplace prefers Spanish keywords, but English may also work.
    - Use **multiple queries** (a list of strings) to try synonyms/variants.
    - Keep queries short: 2-6 words usually works best.

    Good query examples:
    - `"iphone 13 pro"`, `"pixel 8"`, `"macbook m1 16gb"`
    - `"bici gravel"`, `"sofa chaise longue"`, `"nintendo switch oled"`

    Multiple-query example (synonyms/variants):
    - `["airpods pro", "air pods pro", "airpods 2 pro"]`

    Returns:
        Markdown list of matching items (title, description, price) including each
        item `id`. Use that `id` with the `link` tool to get the link for the user.
    """

    return await _search(query)


async def _search(query: list[str]) -> str:
    pages = SEARCH_PAGES_TO_FETCH
    if pages < 1:
        return "Invalid SEARCH_PAGES_TO_FETCH: must be >= 1"

    queries: list[str]
    if isinstance(query, str):
        queries = [query]
    else:
        queries = [q for q in query if isinstance(q, str) and q.strip()]

    if not queries:
        return "Invalid query: provide a non-empty string or list of strings"

    logger.info(
        "Searching marketplace for queries: %s (pages=%s)",
        queries,
        SEARCH_PAGES_TO_FETCH,
    )

    global APP_VERSION
    if APP_VERSION is None:
        APP_VERSION = await get_app_version()

    headers = {
        "User-Agent": USER_AGENT,
        "x-appversion": APP_VERSION,
        "x-deviceos": "0",
    }

    async with httpx.AsyncClient() as client:
        deduped_items: dict[str, MarketplaceItem] = {}

        def _iter_items_in_order(
            items_by_query: dict[str, list[MarketplaceItem]],
        ) -> Iterable[MarketplaceItem]:
            for q in queries:
                for item in items_by_query.get(q, []):
                    yield item

        items_by_query: dict[str, list[MarketplaceItem]] = {q: [] for q in queries}
        next_pages_by_query: dict[str, Optional[str]] = {q: None for q in queries}
        next_section_type_by_query: dict[str, Optional[str]] = {
            q: "organic_search_results" for q in queries
        }

        for current_query in queries:
            api_next_page: Optional[str] = None
            next_section_type: Optional[str] = "organic_search_results"

            logger.info("Starting query '%s'", current_query)

            # Start from page 1 every time; continue via next_page token.
            for page_number in range(1, pages + 1):
                params: dict[str, Any] = {
                    "source": "recent_searches",
                    "keywords": current_query,
                    # "latitude": DEFAULT_LAT,
                    # "longitude": DEFAULT_LON,
                }

                if page_number > 1:
                    if not api_next_page:
                        break
                    params["next_page"] = api_next_page

                try:
                    logger.info(
                        "Requesting query '%s' page %s with app-version %s",
                        current_query,
                        page_number,
                        APP_VERSION,
                    )
                    response = await client.get(API_URL, headers=headers, params=params)
                    response.raise_for_status()
                    data = response.json()

                    items = (
                        data.get("data", {})
                        .get("section", {})
                        .get("payload", {})
                        .get("items", [])
                    )
                    logger.info(
                        "Found %d raw items for query '%s' page %s",
                        len(items),
                        current_query,
                        page_number,
                    )

                    for raw_item in items:
                        try:
                            item = MarketplaceItem.model_validate(raw_item)
                        except Exception as exc:
                            logger.warning("Skipping invalid item payload: %s", exc)
                            continue

                        if item.id:
                            if item.web_slug:
                                ITEM_WEB_SLUG_CACHE[item.id] = item.web_slug
                            if item.description:
                                ITEM_DESCRIPTION_CACHE[item.id] = item.description

                        items_by_query[current_query].append(item)
                        if item.id:
                            deduped_items.setdefault(item.id, item)

                    api_next_page = data.get("meta", {}).get("next_page")
                    next_section_type = data.get("meta", {}).get("next_section_type")

                    logger.info(
                        "Query '%s' page %s meta: next_section_type=%s has_next_page=%s",
                        current_query,
                        page_number,
                        next_section_type,
                        bool(api_next_page),
                    )

                    if next_section_type != "organic_search_results":
                        logger.info(
                            "Stopping query '%s' early: next_section_type=%s",
                            current_query,
                            next_section_type,
                        )
                        break

                except httpx.HTTPStatusError as exc:
                    logger.error(
                        "API Error: %s - %s",
                        exc.response.status_code,
                        exc.response.text,
                    )
                    return (
                        f"API Error: {exc.response.status_code} - {exc.response.text}"
                    )
                except Exception as exc:
                    logger.error("Unexpected error: %s", exc)
                    return f"An error occurred: {str(exc)}"

            next_pages_by_query[current_query] = api_next_page
            next_section_type_by_query[current_query] = next_section_type

            logger.info(
                "Finished query '%s': pages_requested=%s items_collected=%s unique_so_far=%s",
                current_query,
                SEARCH_PAGES_TO_FETCH,
                len(items_by_query[current_query]),
                len(deduped_items),
            )

    logger.info(
        "Deduplicating merged results: queries=%s total_raw=%s unique_ids=%s",
        len(queries),
        sum(len(v) for v in items_by_query.values()),
        len(deduped_items),
    )

    ordered_unique_items: list[MarketplaceItem] = []
    seen_ids: set[str] = set()
    for item in _iter_items_in_order(items_by_query):
        if not item.id:
            continue
        if item.id in seen_ids:
            continue
        seen_ids.add(item.id)
        ordered_unique_items.append(deduped_items[item.id])

    blocks: list[str] = []
    for item in ordered_unique_items:
        block = format_item_markdown(item)
        if block is None:
            continue
        blocks.append(block)

    if not blocks:
        readable_queries = ", ".join(f"'{q}'" for q in queries)
        return f"No results found for {readable_queries}."

    logger.info(
        "Rendering response: items_returned=%s (reserved filtered later)",
        len(ordered_unique_items),
    )

    footer_parts: list[str] = []
    footer = f"\n\n" + "\n".join(footer_parts) if footer_parts else ""

    return "\n".join(blocks) + footer


def run() -> None:
    global SEARCH_PAGES_TO_FETCH, INCLUDE_DESCRIPTION_IN_SEARCH

    parser = argparse.ArgumentParser(description="Marketplace MCP server")
    parser.add_argument(
        "-p",
        "--pages",
        type=int,
        default=5,
        help="Number of pages to fetch per search query (default: 5)",
    )
    parser.add_argument(
        "-d",
        "--descriptions",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Include descriptions in search results (default: True). Use --no-descriptions to disable.",
    )
    args = parser.parse_args()

    SEARCH_PAGES_TO_FETCH = args.pages
    INCLUDE_DESCRIPTION_IN_SEARCH = args.descriptions

    logger.info(
        "Marketplace MCP server STARTED (pages=%s, descriptions=%s)",
        SEARCH_PAGES_TO_FETCH,
        INCLUDE_DESCRIPTION_IN_SEARCH,
    )

    async def _prefetch_app_version() -> None:
        global APP_VERSION
        if APP_VERSION is None:
            APP_VERSION = await get_app_version()

    asyncio.run(_prefetch_app_version())

    mcp.run(transport="stdio")
    logger.info("Marketplace MCP server STOPPED\n\n")
