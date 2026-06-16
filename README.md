# NotebookLM MCP

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/) [![DeepWiki](https://img.shields.io/badge/DeepWiki-View%20Docs-blueviolet?logo=gitbook)](https://deepwiki.com/khengyun/notebooklm-mcp) [![Tests](https://github.com/khengyun/notebooklm-mcp/actions/workflows/test.yml/badge.svg)](https://github.com/khengyun/notebooklm-mcp/actions) [![codecov](https://codecov.io/gh/khengyun/notebooklm-mcp/branch/main/graph/badge.svg)](https://codecov.io/gh/khengyun/notebooklm-mcp) [![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

**MCP server for Google NotebookLM — chat with your sources and manage notebooks/sources as MCP tools.** Driven by an RPC backend ([notebooklm-py](https://github.com/teng-lin/notebooklm-py)), so there's **no browser at runtime**.

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

## Tools (28)

- **Chat:** `send_chat_message`, `get_chat_response`, `chat_with_notebook`, `navigate_to_notebook`, `get`/`set_default_notebook`, `healthcheck`
- **Manage:** `list`/`create`/`rename`/`delete_notebook`, `get_notebook_summary`, `list_sources`, `add_source_url`/`add_source_text`/`delete_source`
- **Compose:** `copy_source`, `create_notebook_from_sources` (merge sources across notebooks)
- **Studio:** `generate_audio_overview`/`list_audio_overviews`, `generate_video_overview`/`list_video_overviews`, `generate_mind_map`/`list_mind_maps`/`get_mind_map`
- **Share:** `get_share_status`, `set_notebook_public`, `share_notebook_with_user`

MIT License
