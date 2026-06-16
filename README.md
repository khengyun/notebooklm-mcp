# NotebookLM MCP

[![Tests](https://github.com/khengyun/notebooklm-mcp/actions/workflows/test.yml/badge.svg)](https://github.com/khengyun/notebooklm-mcp/actions) [![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

MCP server for Google NotebookLM: chat with your sources and manage notebooks/sources as MCP tools. Uses an RPC backend ([notebooklm-py](https://github.com/teng-lin/notebooklm-py)) — no browser at runtime.

## Setup

```bash
uv add notebooklm-mcp
uv run notebooklm login              # one-time Google login (saves a session)
notebooklm-mcp init <notebook-url>   # writes notebooklm-config.json
```

## Run

```bash
notebooklm-mcp -c notebooklm-config.json server          # MCP server (stdio | http | sse)
notebooklm-mcp -c notebooklm-config.json chat -m "..."   # quick chat from the CLI
```

## Tools (16)

- **Chat:** `send_chat_message`, `get_chat_response`, `chat_with_notebook`, `navigate_to_notebook`, `get`/`set_default_notebook`, `healthcheck`
- **Manage:** `list`/`create`/`rename`/`delete_notebook`, `get_notebook_summary`, `list_sources`, `add_source_url`/`add_source_text`/`delete_source`

MIT License
