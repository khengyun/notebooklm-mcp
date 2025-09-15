# 🚀 Tích hợp NotebookLM MCP Server với GitHub Copilot

## 📋 Tổng quan

GitHub Copilot hỗ trợ **Model Context Protocol (MCP)** để mở rộng khả năng thông qua các MCP servers. NotebookLM MCP Server có thể được tích hợp vào GitHub Copilot để cung cấp khả năng tương tác với NotebookLM trực tiếp từ VS Code.

## 🎯 Lợi ích

✅ **Phân tích tài liệu thông minh** - Sử dụng NotebookLM để phân tích code, docs
✅ **Nghiên cứu nâng cao** - Hỏi đáp với kiến thức từ notebook sources
✅ **Tự động hóa workflow** - Copilot có thể sử dụng NotebookLM tools
✅ **Context-aware coding** - Kết hợp code với insights từ documents

## 🛠️ Cài đặt và Cấu hình

### **Bước 1: Cài đặt NotebookLM MCP Server**

```bash
# Cài đặt package
pip install notebooklm-mcp

# Hoặc từ source
git clone https://github.com/khengyun/notebooklm-mcp.git
cd notebooklm-mcp
pip install -e .
```

### **Bước 2: Cấu hình VS Code**

Tạo hoặc chỉnh sửa file cấu hình VS Code settings:

**📁 `.vscode/settings.json`**
```json
{
  "github.copilot.advanced": {
    "mcp": {
      "servers": {
        "notebooklm": {
          "command": "notebooklm-mcp",
          "args": ["server", "--headless"],
          "env": {
            "NOTEBOOKLM_NOTEBOOK_ID": "your-notebook-id-here",
            "NOTEBOOKLM_HEADLESS": "true",
            "NOTEBOOKLM_DEBUG": "false"
          }
        }
      }
    }
  }
}
```

### **Bước 3: Thiết lập môi trường**

Tạo file environment configuration:

**📁 `.env`**
```bash
# NotebookLM Configuration
NOTEBOOKLM_NOTEBOOK_ID=your-actual-notebook-id
NOTEBOOKLM_HEADLESS=true
NOTEBOOKLM_DEBUG=false
NOTEBOOKLM_TIMEOUT=60
NOTEBOOKLM_PROFILE_DIR=./chrome_profile_notebooklm
NOTEBOOKLM_PERSISTENT_SESSION=true
NOTEBOOKLM_STREAMING_TIMEOUT=60
```

### **Bước 4: Khởi tạo Profile (Chỉ cần làm một lần)**

```bash
# Khởi tạo browser profile và đăng nhập
notebooklm-mcp chat --notebook YOUR_NOTEBOOK_ID

# Làm theo hướng dẫn để đăng nhập Google
# Profile sẽ được lưu tự động
```

## 🎮 Cách sử dụng với GitHub Copilot

### **1. Chat Commands trong VS Code**

Sau khi cấu hình, bạn có thể sử dụng các lệnh sau trong Copilot Chat:

```
@copilot /notebooklm Phân tích file README.md này và đưa ra gợi ý cải thiện

@copilot /notebooklm Tóm tắt các best practices từ tài liệu này

@copilot /notebooklm Dựa trên notebook, code này có vấn đề gì?
```

### **2. Tích hợp với Code Actions**

GitHub Copilot có thể tự động gợi ý sử dụng NotebookLM tools:

```python
# Copilot sẽ hiểu context và gợi ý
def analyze_document(file_path):
    # Copilot có thể gợi ý: "Use NotebookLM to analyze this document"
    pass
```

### **3. Workflow Examples**

#### **📊 Document Analysis Workflow**
```python
# 1. Copilot phát hiện bạn đang làm việc với documents
# 2. Tự động gợi ý sử dụng NotebookLM để phân tích
# 3. Cung cấp insights từ notebook sources
# 4. Giúp viết code dựa trên findings
```

#### **🔍 Research Assistant Workflow**
```python
# 1. Đặt câu hỏi cho Copilot về domain specific knowledge
# 2. Copilot sử dụng NotebookLM để tìm relevant information
# 3. Kết hợp với code suggestions
# 4. Cung cấp complete solution với context
```

## 🔧 Advanced Configuration

### **Cấu hình Multiple Notebooks**

```json
{
  "github.copilot.advanced": {
    "mcp": {
      "servers": {
        "notebooklm-research": {
          "command": "notebooklm-mcp",
          "args": ["server", "--notebook", "research-notebook-id", "--headless"]
        },
        "notebooklm-docs": {
          "command": "notebooklm-mcp",
          "args": ["server", "--notebook", "docs-notebook-id", "--headless"]
        }
      }
    }
  }
}
```

### **Custom MCP Tools cho Copilot**

```json
{
  "github.copilot.advanced": {
    "mcp": {
      "servers": {
        "notebooklm": {
          "command": "notebooklm-mcp",
          "args": ["server", "--headless"],
          "tools": [
            "chat_with_notebook",
            "analyze_code_with_notebook",
            "get_research_insights",
            "upload_and_analyze"
          ]
        }
      }
    }
  }
}
```

## 🚀 Use Cases thực tế

### **1. Code Review với Context**
```bash
# Copilot sử dụng NotebookLM để review code
@copilot /review Dựa trên documentation trong notebook, code này có follow best practices không?
```

### **2. Documentation Generation**
```bash
# Tự động tạo docs dựa trên notebook knowledge
@copilot /document Tạo documentation cho function này dựa trên style guide trong notebook
```

### **3. Research-Driven Development**
```bash
# Phát triển features dựa trên research
@copilot /implement Implement feature X dựa trên research findings trong notebook
```

## 🔍 Troubleshooting

### **Lỗi thường gặp:**

#### **1. MCP Server không khởi động**
```bash
# Kiểm tra installation
notebooklm-mcp --version

# Test server manually
notebooklm-mcp server --notebook YOUR_ID --debug
```

#### **2. Authentication issues**
```bash
# Reset profile
rm -rf ./chrome_profile_notebooklm

# Re-initialize
notebooklm-mcp chat --notebook YOUR_ID
```

#### **3. VS Code không nhận diện MCP server**
- Restart VS Code sau khi thay đổi settings
- Kiểm tra VS Code logs: `View > Output > GitHub Copilot`
- Verify MCP server path trong settings

### **Debug Commands:**

```bash
# Test MCP server
notebooklm-mcp server --notebook YOUR_ID --debug

# Test specific tool
notebooklm-mcp chat --notebook YOUR_ID --message "test message"

# Check configuration
notebooklm-mcp config-show
```

## 📈 Monitoring và Performance

### **Health Checks**
```bash
# Check server health
curl -X POST http://localhost:3000/tools/healthcheck

# Monitor logs
tail -f ~/.local/share/notebooklm-mcp/logs/server.log
```

### **Performance Tuning**
```json
{
  "NOTEBOOKLM_TIMEOUT": "30",
  "NOTEBOOKLM_STREAMING_TIMEOUT": "45",
  "NOTEBOOKLM_RESPONSE_STABILITY_CHECKS": "2"
}
```

## 🎯 Best Practices

### **1. Notebook Organization**
- Tạo notebook riêng cho từng project
- Upload relevant documentation và code examples
- Maintain clean, organized sources

### **2. Prompt Engineering**
- Sử dụng specific, contextual prompts
- Leverage notebook sources trong câu hỏi
- Combine code context với document insights

### **3. Workflow Integration**
- Setup automated upload của project docs
- Regular sync với latest documentation
- Use consistent naming conventions

## 🔗 Resources

- **NotebookLM MCP Server**: [GitHub Repository](https://github.com/khengyun/notebooklm-mcp)
- **GitHub Copilot MCP Docs**: [Official Documentation](https://docs.github.com/copilot/mcp)
- **Model Context Protocol**: [Specification](https://spec.modelcontextprotocol.io/)

---

**🎉 Với tích hợp này, GitHub Copilot sẽ có thể sử dụng NotebookLM như một research assistant mạnh mẽ, giúp bạn code thông minh hơn với context từ documents và knowledge base!**
