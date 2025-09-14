# NotebookLM MCP Server (Selenium + Cookies)

An MCP (Model Context Protocol) server exposing NotebookLM automation tools via Selenium WebDriver.
Supports cookie-based authentication, headless mode, and smooth integration with AutoGen's `McpWorkbench` over STDIO.

## Features

- MCP server over STDIO for compatibility with AutoGen
- Selenium (Chrome) with optional headless mode
- Cookie loading/saving from JSON file
- Basic NotebookLM tools (navigate, chat, list, upload, create, search, insights, export)
- Graceful shutdown and logging with `loguru`

## Requirements

- Python 3.10+
- Google Chrome or Chromium available on system
- `chromedriver` compatible with your Chrome version (Selenium Manager in recent Selenium installs can auto-manage)

Install deps:

```bash
pip install -r notebooklm-mcp/requirements.txt
```

## Cookie File Format
Provide a JSON file with an array of cookies in a Selenium-compatible format. Example:

```json
[
  {
    "name": "SID",
    "value": "xxxx",
    "domain": ".google.com",
    "path": "/",
    "secure": true,
    "httpOnly": true,
    "expiry": 1893456000
  }
]
```

- `domain` can be `.google.com` or `notebooklm.google.com` depending on origin
- `expiry` is optional; if present and expired, the cookie will be skipped

## Run the MCP Server

```bash
python notebooklm-mcp/notebooklm_mcp_server.py \
  --cookies path/to/cookies.json \
  --notebook https://notebooklm.google.com/notebook/4741957b-f358-48fb-a16a-da8d20797bc6 \
  --headless \
  --timeout 30 \
  --debug
```

The server communicates via STDIO and is intended to be launched by AutoGen.

## Use with AutoGen

```python
import asyncio
from autogen_ext.tools.mcp import McpWorkbench, StdioServerParams
from autogen_agentchat.agents import AssistantAgent

async def main():
    server_params = StdioServerParams(
        command="python",
    args=[
      "notebooklm-mcp/notebooklm_mcp_server.py",
      "--cookies", "cookies.json",
      "--notebook", os.environ.get("NOTEBOOKLM_NOTEBOOK", "4741957b-f358-48fb-a16a-da8d20797bc6"),
      "--headless",
    ],
        read_timeout_seconds=60,
    )
    async with McpWorkbench(server_params) as mcp:
        agent = AssistantAgent(
            name="notebooklm_assistant",
            model_client=None,  # your model client
            workbench=mcp,
        )
        # Example: call tools via agent or workbench.
        # This snippet focuses on server integration.

if __name__ == "__main__":
    asyncio.run(main())
```

## Exposed Tools

- `healthcheck()` -> str
- `navigate_to_notebook(notebook_id: str)` -> str (final URL)
- `send_chat_message(message: str)` -> str ("sent")
- `get_chat_response()` -> str
- `upload_document(file_path: str, document_type: str)` -> str
- `list_notebooks()` -> list[dict]
- `create_notebook(name: str, sources: list[str])` -> dict
- `get_notebook_insights(notebook_id: str)` -> dict
- `search_in_notebook(query: str, notebook_id: str)` -> list[str]
- `export_conversation(format: str)` -> str

Notes:

- The current selectors are placeholders. You may need to update Selenium selectors to match NotebookLM’s UI.
- For cookie auth to work, ensure cookies are valid for Google/NotebookLM domains.

## Troubleshooting

- Import errors for `mcp`/`selenium`/`loguru`: install via `pip install -r requirements.txt`
- Chrome/driver mismatch: upgrade Chrome or use Selenium Manager (Selenium 4.6+)
- Auth failing: verify cookie freshness and domain; re-export fresh cookies

## License

MIT
