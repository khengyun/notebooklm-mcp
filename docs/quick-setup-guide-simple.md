# 🚀 Quick Setup Guide for NotebookLM MCP Server

> **The simplest way to get NotebookLM MCP Server running**

## 🎯 **Super Simple Setup (2 Commands)**

### **Step 1: Initialize with your NotebookLM URL**

```bash
notebooklm-mcp init https://notebooklm.google.com/notebook/YOUR_NOTEBOOK_ID
```

**What happens:**

- ✅ Extracts notebook ID from URL automatically
- ✅ Creates `notebooklm-config.json` with optimal settings
- ✅ Sets up `chrome_profile_notebooklm/` directory
- ✅ Tests browser functionality and authentication
- ✅ Automatically switches to headless mode for production

### **Step 2: Start the server**

```bash
notebooklm-mcp --config notebooklm-config.json server
```

**That's it!** Your MCP server is ready for AutoGen, GitHub Copilot, or any MCP client.

---

## 📝 **Common Use Cases**

### **For AutoGen Users**

```python
from autogen_ext.tools.mcp import McpWorkbench, StdioServerParams

params = StdioServerParams(
    command="notebooklm-mcp",
    args=["--config", "notebooklm-config.json", "server", "--headless"]
)

workbench = McpWorkbench(params)
```

### **For GitHub Copilot Users**

Add to VS Code `settings.json`:

```json
{
  "github.copilot.advanced": {
    "mcp": {
      "servers": {
        "notebooklm": {
          "command": "notebooklm-mcp",
          "args": ["--config", "notebooklm-config.json", "server", "--headless"]
        }
      }
    }
  }
}
```

### **For Direct Chat Testing**

```bash
notebooklm-mcp --config notebooklm-config.json chat --message "Hello!"
```

---

## 🔧 **Troubleshooting**

### **Authentication Issues**

If you get authentication errors:

```bash
# Delete profile and re-run init
rm -rf chrome_profile_notebooklm
notebooklm-mcp init https://notebooklm.google.com/notebook/YOUR_NOTEBOOK_ID
```

### **Config Issues**

If config is corrupted:

```bash
# Re-generate config
rm notebooklm-config.json
notebooklm-mcp init https://notebooklm.google.com/notebook/YOUR_NOTEBOOK_ID
```

---

**✅ Result: From URL to working MCP server in under 2 minutes!**
