# 🤖 NotebookLM MCP Server

[![PyPI version](https://badge.fury.io/py/notebooklm-mcp.svg)](https://badge.fury.io/py/notebooklm-mcp)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)
[![Tests](https://github.com/notebooklm-mcp/notebooklm-mcp/workflows/Tests/badge.svg)](https://github.com/notebooklm-mcp/notebooklm-mcp/actions)

Professional **Model Context Protocol (MCP) server** for automating interactions with Google's **NotebookLM**. Features persistent browser sessions, streaming response support, and comprehensive automation capabilities.

## ✨ **Key Features**

### 🚀 **Advanced Automation**
- **Persistent Browser Sessions** - Login once, auto-authenticate forever
- **Streaming Response Support** - Proper handling of LLM streaming responses  
- **Multiple Chat Methods** - Send/receive individually or combined operations
- **Anti-Detection Bypassing** - Uses `undetected-chromedriver` for Google compatibility
- **Smart DOM Interaction** - Intelligent selectors with multiple fallbacks
- **Comprehensive Error Handling** - Robust fallbacks and detailed logging

### 💬 **Chat Operations**
| Method | Description | Streaming | Use Case |
|--------|-------------|-----------|----------|
| `send_message` | Send chat message | ❌ | Quick message sending |
| `get_response` | Get complete response | ✅ | Wait for full AI response |
| `get_quick_response` | Get current response | ⚡ | Immediate response check |
| `chat_with_notebook` | Combined send + receive | ✅ | One-shot conversations |

### 📚 **Notebook Management** 
- Navigate to specific notebooks
- Upload documents to notebooks  
- List available notebooks
- Create new notebooks
- Search within notebooks
- Export conversation history

## 🚀 **Quick Start**

### **Installation**

```bash
# Install from PyPI
pip install notebooklm-mcp

# Or install from source
git clone https://github.com/notebooklm-mcp/notebooklm-mcp.git
cd notebooklm-mcp
pip install -e .
```

### **One-Time Setup** 

```bash
# First run - opens browser for manual login
notebooklm-mcp chat --notebook YOUR_NOTEBOOK_ID

# Login manually when browser opens
# Session automatically saved for future runs ✨
```

### **Start MCP Server**

```bash
# Start server with your notebook
notebooklm-mcp server --notebook 4741957b-f358-48fb-a16a-da8d20797bc6 --headless

# Or use environment variables
export NOTEBOOKLM_NOTEBOOK_ID="your-notebook-id"
export NOTEBOOKLM_HEADLESS="true"
notebooklm-mcp server
```

### **Interactive Chat**

```bash
# Interactive chat session
notebooklm-mcp chat --notebook your-notebook-id

# Send single message
notebooklm-mcp chat --notebook your-notebook-id --message "Summarize this document"
```

## 📖 **Usage Examples**

### **Python API**

```python
import asyncio
from notebooklm_mcp import NotebookLMClient, ServerConfig

async def main():
    # Configure client
    config = ServerConfig(
        default_notebook_id="your-notebook-id",
        headless=True,
        debug=True
    )
    
    client = NotebookLMClient(config)
    
    try:
        # Start browser with persistent session
        await client.start()
        
        # Authenticate (automatic with saved session)
        await client.authenticate()
        
        # Send message and get streaming response
        await client.send_message("What are the key insights from this document?")
        response = await client.get_response(wait_for_completion=True)
        
        print(f"NotebookLM: {response}")
        
    finally:
        await client.close()

asyncio.run(main())
```

### **MCP Integration with AutoGen**

```python
from autogen_ext.tools.mcp import McpWorkbench, StdioServerParams

# Configure MCP server
params = StdioServerParams(
    command="notebooklm-mcp",
    args=["server", "--notebook", "your-notebook-id", "--headless"]
)

# Create MCP workbench
workbench = McpWorkbench(params)

# Use tools
await workbench.call_tool("chat_with_notebook", {
    "message": "Analyze the main themes in this research paper",
    "max_wait": 60
})
```

## 🛠️ **Advanced Configuration**

### **Environment Variables**

```bash
# Core settings
export NOTEBOOKLM_NOTEBOOK_ID="your-notebook-id"
export NOTEBOOKLM_HEADLESS="true"
export NOTEBOOKLM_DEBUG="false" 
export NOTEBOOKLM_TIMEOUT="60"

# Authentication
export NOTEBOOKLM_PROFILE_DIR="./chrome_profile"
export NOTEBOOKLM_PERSISTENT_SESSION="true"

# Streaming
export NOTEBOOKLM_STREAMING_TIMEOUT="60"
```

## 📊 **MCP Tools Reference**

| Tool | Arguments | Description |
|------|-----------|-------------|
| `healthcheck` | None | Server health status |
| `send_chat_message` | `message: str` | Send message to NotebookLM |
| `get_chat_response` | `wait_for_completion: bool`, `max_wait: int` | Get response with streaming support |
| `get_quick_response` | None | Get current response immediately |
| `chat_with_notebook` | `message: str`, `max_wait: int` | Combined send + receive operation |
| `navigate_to_notebook` | `notebook_id: str` | Navigate to specific notebook |
| `upload_document` | `file_path: str` | Upload document to notebook |
| `list_notebooks` | None | List available notebooks |
| `create_notebook` | `title: str` | Create new notebook |

## 🔧 **Development**

### **Setup Development Environment**

```bash
# Clone repository
git clone https://github.com/notebooklm-mcp/notebooklm-mcp.git
cd notebooklm-mcp

# Install development dependencies
pip install -e ".[dev]"

# Install pre-commit hooks
pre-commit install
```

### **Running Tests**

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=notebooklm_mcp

# Run only unit tests
pytest -m unit

# Run integration tests (requires browser)
pytest -m integration
```

## 📄 **License**

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🆘 **Support**

- **Issues**: [GitHub Issues](https://github.com/notebooklm-mcp/notebooklm-mcp/issues)
- **Discussions**: [GitHub Discussions](https://github.com/notebooklm-mcp/notebooklm-mcp/discussions)

---

**⭐ If this project helps you, please give it a star!**