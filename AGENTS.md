# MCP Development Guide

This repository contains an MCP (Model Context Protocol) server for interacting with the marketplace.

## 🛠 Commands

This project uses `uv` for dependency management and task execution.

| Task | Command |
|------|---------|
| **Run Server** | `uv run main.py` |
| **Install Dependencies** | `uv sync` |
| **Add Dependency** | `uv add <package>` |
| **Run Linting** | `uv run ruff check .` (if ruff is added) |
| **Run Tests** | `uv run pytest` (if pytest is added) |
| **Single Test** | `uv run pytest tests/test_file.py::test_name` |

*Note: As of now, `ruff` and `pytest` are not in `pyproject.toml`. Please add them if you implement tests or linting.*

## 📋 Code Style & Conventions

### 1. Imports
- Use absolute imports where possible.
- Group imports: Standard library, third-party packages, local modules.
- Use `from typing import ...` for type hints.

### 2. Naming Conventions
- **Variables/Functions:** `snake_case` (e.g., `search_marketplace`, `app_version`).
- **Constants:** `UPPER_SNAKE_CASE` (e.g., `API_URL`, `DEFAULT_LAT`).
- **Classes:** `PascalCase` (if added).

### 3. Type Hinting
- All function signatures **must** include type hints.
- Use `Optional` for values that can be `None`.
- Use `Annotated` if adding documentation to types.

### 4. Logging
- **CRITICAL:** Always use `logging` configured to `sys.stderr`.
- **DO NOT** use `print()` in the server logic as it corrupts the MCP STDIO transport.
- Format: `%(asctime)s - %(name)s - %(levelname)s - %(message)s`.

### 5. Error Handling
- Wrap external API calls in `try...except` blocks.
- Distinguish between `httpx.HTTPStatusError` and general `Exception`.
- Log errors to `stderr` before returning user-friendly messages via MCP.

### 6. Marketplace API Specifics
- **Headers:** Always include `User-Agent`, `x-appversion`, and `x-deviceos`.
- **Coordinates:** Default to `43.3707332`, `-8.3958532` (A Coruña) unless specified.
- **Source:** Use `source=recent_searches` for all search requests.

## 📦 MCP Tool: search_marketplace

- **Input:** `query` (string), optional `page` (int, default `1`).
- **Output:** A formatted Markdown string containing items (Title, Description, Price).
- **Pagination:**
    - Only the *next sequential page* can be requested.
    - Request page 1 first, then page 2, then page 3, etc.
    - The server caches the marketplaces real pagination token internally and never exposes it.
    - When a next page exists, the response footer includes: `Next page available: <N>. Request it with page=<N>.`
- **Behavior:**
    1. Fetches current app version.
    2. Constructs headers and parameters.
    3. Performs async GET request to `API_URL`
    4. Parses items from `data.section.payload.items` in the JSON response.
    5. Stores pagination state per query using `meta.next_page`.

## 🚀 Deployment (Claude Desktop)

To use this server in Claude Desktop, add the following to `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "marketplace": {
      "command": "uv",
      "args": [
        "--directory",
        "/home/valonso/code/wallai",
        "run",
        "main.py"
      ]
    }
  }
}
```

## 🔍 API Technical Reference (Legacy)

### Endpoint
`GET API_URL`

### Pagination
1. Perform initial search.
2. Retrieve `next_page` token from `meta.next_page` in the JSON body.
3. Subsequent requests must use `next_page` query parameter with that value.
