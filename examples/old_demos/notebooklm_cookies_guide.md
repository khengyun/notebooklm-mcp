# 🍪 Hướng dẫn lấy cookies từ trang NotebookLM cụ thể

## ⚠️ Quan trọng: Cookies phải từ đúng URL!

**URL cần lấy cookies:** `https://notebooklm.google.com/notebook/4741957b-f358-48fb-a16a-da8d20797bc6`

## 📋 Các bước chi tiết:

### **1. 🌐 Mở Edge và đăng nhập**
1. Mở Microsoft Edge
2. Truy cập: `https://notebooklm.google.com/notebook/4741957b-f358-48fb-a16a-da8d20797bc6`
3. **Đăng nhập Google account** nếu chưa đăng nhập
4. **Đợi cho đến khi notebook load hoàn toàn**

### **2. 🔧 Extract cookies bằng DevTools (Manual)**

#### **Cách 1: Chrome/Edge DevTools**
1. Nhấn **F12** để mở DevTools
2. Chuyển đến tab **"Application"** (hoặc **"Storage"** trong Firefox)
3. Trong sidebar trái, mở **"Cookies"** → **"https://notebooklm.google.com"**
4. **Copy TẤT CẢ cookies** (Ctrl+A → Ctrl+C)
5. Tạo file `cookies.json` theo format:

```json
[
  {
    "name": "cookie_name",
    "value": "cookie_value", 
    "domain": "notebooklm.google.com",
    "path": "/",
    "secure": true,
    "httpOnly": false
  }
]
```

#### **Cách 2: Browser Extension (Dễ nhất)**
1. Cài extension **"Cookie-Editor"** cho Edge
2. Vào trang NotebookLM (đã load xong)
3. Click icon Cookie-Editor
4. **Export** → **JSON format**
5. Lưu thành `cookies.json`

### **3. 🔄 Update extract script**
Tôi sẽ update script để chỉ lấy cookies từ domain NotebookLM:
