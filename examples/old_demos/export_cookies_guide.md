# Hướng dẫn xuất cookies.json cho NotebookLM

## Phương pháp 1: Sử dụng Browser Extension (Khuyên dùng)

### Chrome Extension: "Cookie-Editor"
1. Cài đặt extension "Cookie-Editor" từ Chrome Web Store
2. Truy cập https://notebooklm.google.com và đăng nhập
3. Click vào icon Cookie-Editor trên thanh toolbar
4. Click "Export" → chọn "JSON"
5. Lưu file với tên `cookies.json`

### Firefox Extension: "Cookie Quick Manager"
1. Cài đặt "Cookie Quick Manager" addon
2. Truy cập NotebookLM và đăng nhập  
3. Mở addon → chọn domain "google.com"
4. Export cookies as JSON

## Phương pháp 2: Chrome DevTools (Manual)

### Bước 1: Mở DevTools
1. Truy cập https://notebooklm.google.com và đăng nhập
2. Nhấn F12 hoặc Ctrl+Shift+I để mở DevTools
3. Chuyển đến tab "Application" (hoặc "Storage" trong Firefox)

### Bước 2: Xuất cookies
1. Trong sidebar trái, mở "Cookies" → "https://notebooklm.google.com"
2. Sao chép tất cả cookies quan trọng:
   - `SID`, `HSID`, `SSID`, `APISID`, `SAPISID`
   - `__Secure-1PSID`, `__Secure-3PSID`
   - `session_state`, `oauth_token`

### Bước 3: Tạo file JSON
Tạo file `cookies.json` với format:

```json
[
  {
    "name": "SID", 
    "value": "your_sid_value_here",
    "domain": ".google.com",
    "path": "/",
    "secure": true,
    "httpOnly": true,
    "expiry": 1893456000
  },
  {
    "name": "__Secure-1PSID",
    "value": "your_secure_psid_value", 
    "domain": ".google.com",
    "path": "/",
    "secure": true,
    "httpOnly": true
  }
]
```

## Phương pháp 3: Python Script (Automated)

Tạo script để tự động extract cookies từ trình duyệt:

```python
# extract_cookies.py
import json
import sqlite3
import os
from pathlib import Path

def get_chrome_cookies():
    # Chrome cookies database path
    if os.name == 'nt':  # Windows
        cookies_path = Path.home() / "AppData/Local/Google/Chrome/User Data/Default/Cookies"
    else:  # Linux/Mac
        cookies_path = Path.home() / ".config/google-chrome/Default/Cookies"
    
    if not cookies_path.exists():
        print("Chrome cookies database not found")
        return []
    
    conn = sqlite3.connect(str(cookies_path))
    cursor = conn.cursor()
    
    # Query for Google domain cookies
    cursor.execute("""
        SELECT name, value, host_key, path, expires_utc, is_secure, is_httponly
        FROM cookies 
        WHERE host_key LIKE '%google.com%'
        AND (name LIKE '%SID%' OR name LIKE '%session%' OR name LIKE '%auth%')
    """)
    
    cookies = []
    for row in cursor.fetchall():
        name, value, domain, path, expires, secure, httponly = row
        cookies.append({
            "name": name,
            "value": value, 
            "domain": domain,
            "path": path,
            "secure": bool(secure),
            "httpOnly": bool(httponly),
            "expiry": expires // 1000000 - 11644473600 if expires else None
        })
    
    conn.close()
    return cookies

# Usage
cookies = get_chrome_cookies()
with open("cookies.json", "w") as f:
    json.dump(cookies, f, indent=2)
print(f"Exported {len(cookies)} cookies to cookies.json")
```

## Cookies quan trọng cần có:

### Authentication cookies:
- `SID` - Session ID
- `HSID` - Host Session ID  
- `SSID` - Secure Session ID
- `APISID` - API Session ID
- `SAPISID` - Secure API Session ID
- `__Secure-1PSID` - Secure partition SID
- `__Secure-3PSID` - Cross-site secure SID

### NotebookLM specific:
- `session_state` - App session state
- `auth_user` - User authentication
- Any cookies starting with `notebook` or `ai_`

## Kiểm tra cookies hợp lệ:

```bash
# Test với MCP server
python notebooklm_mcp_server.py \
  --cookies cookies.json \
  --notebook 4741957b-f358-48fb-a16a-da8d20797bc6 \
  --headless \
  --debug
```

## Troubleshooting:

### Lỗi authentication:
1. Đảm bảo đã đăng nhập Google trước khi export cookies
2. Cookies phải từ cùng session đang hoạt động
3. Kiểm tra expiry time (cookies cũ sẽ bị reject)

### Refresh cookies:
- Cookies Google thường expire sau 1-2 tuần
- Cần export lại khi thấy authentication fail
- Sử dụng browser extension để auto-refresh

## Security Notes:
- **KHÔNG chia sẻ** file cookies.json (chứa session tokens)
- Add `cookies.json` vào `.gitignore`
- Xóa cookies cũ khi không dùng