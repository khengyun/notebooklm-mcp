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

```bash
# 1. Generate config + import existing Chrome profile
notebooklm-mcp quick-setup --config config.json --notebook YOUR_NOTEBOOK_ID --profile /path/to/chrome/profile --headless

# 2. Start server immediately (no manual login needed!)
notebooklm-mcp --config config.json server
```

### **Method 2: One-Time Setup with New Profile**

```bash
# 1. Generate config for first-time setup
python examples/quick_setup.py YOUR_NOTEBOOK_ID

# 2. Run with generated config
notebooklm-mcp --config notebooklm-config.json chat
# Manual login required ONCE

# 3. All future runs - zero setup!
notebooklm-mcp --config notebooklm-config.json server
```

---

## 📋 **Detailed Quick Setup Options**

### **🔧 Generate Config with Python Script**

```bash
# Basic config (manual login required)
python examples/quick_setup.py 4741957b-f358-48fb-a16a-da8d20797bc6

# With existing Chrome profile (zero manual login!)
python examples/quick_setup.py YOUR_ID /home/user/.config/google-chrome/Default

# GUI mode instead of headless
python examples/quick_setup.py YOUR_ID --gui

# With custom profile location
python examples/quick_setup.py YOUR_ID /custom/chrome/profile
```

**Generated config example:**
```json
{
  "headless": true,
  "default_notebook_id": "4741957b-f358-48fb-a16a-da8d20797bc6",
  "auth": {
    "profile_dir": "./chrome_profile_notebooklm",
    "import_profile_from": "/home/user/.config/google-chrome/Default",
    "skip_manual_login": true
  }
}
```

### **⚡ CLI Quick Setup Commands**

```bash
# Complete setup in one command
notebooklm-mcp quick-setup \
    --config ./my-config.json \
    --notebook 4741957b-f358-48fb-a16a-da8d20797bc6 \
    --profile /path/to/existing/chrome/profile \
    --headless

# Import existing Chrome profile
notebooklm-mcp import-profile \
    --from-profile ~/.config/google-chrome/Default \
    --to-profile ./notebooklm-chrome-profile

# Export current profile for sharing
notebooklm-mcp export-profile \
    --to ./shared-notebooklm-profile
```

### **📁 Profile Management Workflow**

```bash
# 1. Setup once on your main machine
notebooklm-mcp chat --notebook YOUR_ID  # Manual login once
notebooklm-mcp export-profile --to ./team-profile

# 2. Share profile with team/other machines
# Copy ./team-profile to other machines

# 3. Quick setup on any machine
notebooklm-mcp quick-setup \
    -c config.json \
    -n YOUR_ID \
    -p ./team-profile \
    --headless

# 4. Instant server start (no login needed!)
notebooklm-mcp server -c config.json
```

---

## 🎯 **Configuration Templates**

### **Template 1: Development Setup**
```json
{
  "headless": false,
  "debug": true,
  "timeout": 120,
  "default_notebook_id": "YOUR_NOTEBOOK_ID",
  "auth": {
    "profile_dir": "./dev-chrome-profile",
    "use_persistent_session": true,
    "auto_login": true
  }
}
```

### **Template 2: Production/Headless Setup**
```json
{
  "headless": true,
  "debug": false,
  "timeout": 30,
  "default_notebook_id": "YOUR_NOTEBOOK_ID",
  "auth": {
    "profile_dir": "./prod-chrome-profile",
    "import_profile_from": "./shared-team-profile",
    "skip_manual_login": true
  }
}
```

### **Template 3: Multi-Notebook Setup**
```json
{
  "headless": true,
  "default_notebook_id": "primary-notebook-id",
  "auth": {
    "profile_dir": "./multi-notebook-profile",
    "use_persistent_session": true
  },
  "notebooks": {
    "research": "notebook-id-1",
    "documentation": "notebook-id-2",
    "analysis": "notebook-id-3"
  }
}
```

---

## 💡 **Pro Tips**

### **🚀 Fastest Possible Setup**
1. Get Chrome profile from working machine
2. Use `quick-setup` command with profile
3. Start server immediately - **zero manual steps!**

### **👥 Team Collaboration**
1. One person does initial setup
2. Export profile with `export-profile`
3. Share profile folder with team
4. Everyone uses `quick-setup` with shared profile

### **🔄 Environment-Specific Configs**
```bash
# Development
notebooklm-mcp --config configs/dev.json server

# Staging
notebooklm-mcp --config configs/staging.json server

# Production
notebooklm-mcp --config configs/prod.json server
```

### **📦 Docker Quick Deploy**
```dockerfile
# Copy pre-configured profile and config
COPY ./team-chrome-profile /app/chrome-profile
COPY ./production.json /app/config.json

# Zero-setup container start
CMD ["notebooklm-mcp", "server", "-c", "/app/config.json"]
```

---

## 🛠️ **Troubleshooting Quick Setup**

| Issue | Solution |
|-------|----------|
| **Profile import fails** | Check source profile permissions: `chmod -R 755 /path/to/profile` |
| **Config validation error** | Use `notebooklm-mcp config-show -c config.json` to debug |
| **Authentication still required** | Ensure `skip_manual_login: true` and valid profile imported |
| **Chrome crashes** | Add `"timeout": 120` for slower systems |
| **Permission denied** | Run `sudo chown -R $USER:$USER ./chrome_profile*` |

---

## 📋 **Quick Setup Checklist**

- [ ] **Choose setup method**: New profile vs. existing profile
- [ ] **Generate config**: Use script or CLI command
- [ ] **Import profile** (if using existing)
- [ ] **Test connection**: `notebooklm-mcp test -c config.json`
- [ ] **Start server**: `notebooklm-mcp --config config.json server`
- [ ] **Export profile** (for future sharing)

**Result: From install to working server in under 2 minutes!** 🎉
