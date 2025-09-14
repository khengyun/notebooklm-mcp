#!/usr/bin/env python3
"""
Script để tự động extract cookies từ Edge hoặc Chrome browser cho NotebookLM MCP server.
Chạy script này sau khi đã đăng nhập NotebookLM trên Edge/Chrome.

Cookies từ Edge có thể sử dụng với Chrome driver vì chúng cùng format và compatible.
"""

import json
import sqlite3
import os
import sys
import shutil
import tempfile
from pathlib import Path
from typing import List, Dict, Any

def find_browser_cookies_path() -> tuple[Path, str]:
    """Tìm đường dẫn đến cookies database của Chrome hoặc Edge."""
    browsers = []
    
    if os.name == 'nt':  # Windows
        browsers = [
            (Path.home() / "AppData/Local/Microsoft/Edge/User Data", "Edge"),
            (Path.home() / "AppData/Local/Google/Chrome/User Data", "Chrome"),
        ]
    elif sys.platform == 'darwin':  # macOS
        browsers = [
            (Path.home() / "Library/Application Support/Microsoft Edge", "Edge"),
            (Path.home() / "Library/Application Support/Google/Chrome", "Chrome"),
        ]
    else:  # Linux
        browsers = [
            (Path.home() / ".config/microsoft-edge", "Edge"),
            (Path.home() / ".config/google-chrome", "Chrome"),
        ]
    
    # Thử tìm cookies trong từng browser
    for base_path, browser_name in browsers:
        # Thử Default profile trước
        cookies_path = base_path / "Default/Cookies"
        if cookies_path.exists():
            return cookies_path, browser_name
        
        # Nếu không có, tìm profile khác
        for profile_dir in base_path.glob("Profile */Cookies"):
            if profile_dir.exists():
                return profile_dir, browser_name
    
    raise FileNotFoundError("Browser cookies database not found. Make sure Edge or Chrome is installed and you've visited NotebookLM.")

def extract_google_cookies(cookies_db_path: Path) -> List[Dict[str, Any]]:
    """Extract Google cookies từ Chrome database."""
    # Tạo bản copy tạm vì Chrome lock file khi đang chạy
    with tempfile.NamedTemporaryFile(delete=False) as temp_file:
        shutil.copy2(cookies_db_path, temp_file.name)
        temp_db_path = temp_file.name
    
    try:
        conn = sqlite3.connect(temp_db_path)
        cursor = conn.cursor()
        
        # Query cho NotebookLM domain cookies (chỉ lấy từ notebooklm.google.com)
        cursor.execute("""
            SELECT name, value, host_key, path, expires_utc, is_secure, is_httponly
            FROM cookies 
            WHERE (
                host_key LIKE '%notebooklm.google.com%' OR
                host_key LIKE '%.google.com%'
            ) AND (
                name IN ('SID', 'HSID', 'SSID', 'APISID', 'SAPISID') OR
                name LIKE '__Secure-%PSID%' OR
                name LIKE 'session%' OR
                name LIKE 'auth%' OR
                name LIKE 'oauth%' OR
                name LIKE 'notebook%' OR
                name LIKE '_gid' OR
                name LIKE '_ga%' OR
                name LIKE 'CONSENT%'
            )
            ORDER BY host_key, name
        """)
        
        cookies = []
        for row in cursor.fetchall():
            name, value, domain, path, expires_utc, is_secure, is_httponly = row
            
            # Convert Chrome timestamp to Unix timestamp
            if expires_utc and expires_utc > 0:
                # Chrome uses microseconds since Jan 1, 1601
                # Unix timestamp is seconds since Jan 1, 1970
                unix_timestamp = (expires_utc / 1000000) - 11644473600
                expiry = int(unix_timestamp) if unix_timestamp > 0 else None
            else:
                expiry = None
            
            cookie = {
                "name": name,
                "value": value,
                "domain": domain,  # Keep original domain format
                "path": path,
                "secure": bool(is_secure),
                "httpOnly": bool(is_httponly)
            }
            
            if expiry:
                cookie["expiry"] = expiry
            
            cookies.append(cookie)
        
        conn.close()
        return cookies
    
    finally:
        # Xóa temp file
        os.unlink(temp_db_path)

def main():
    """Main function."""
    try:
        print("🔍 Đang tìm browser cookies database...")
        cookies_path, browser_name = find_browser_cookies_path()
        print(f"✅ Found {browser_name}: {cookies_path}")
        
        print("📥 Đang extract Google cookies...")
        cookies = extract_google_cookies(cookies_path)
        
        if not cookies:
            print("⚠️  Không tìm thấy cookies NotebookLM nào. Hãy đảm bảo bạn đã:")
            print("   1. Đăng nhập vào https://notebooklm.google.com/notebook/4741957b-f358-48fb-a16a-da8d20797bc6 trên Edge")
            print("   2. Đợi notebook load hoàn toàn")
            print("   3. Đóng tất cả tab browser trước khi chạy script")
            return
        
        # Lưu cookies
        output_file = "cookies.json"
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(cookies, f, indent=2, ensure_ascii=False)
        
        print(f"✅ Đã export {len(cookies)} cookies từ {browser_name} vào {output_file}")
        print("\n📋 Cookies đã extract:")
        for cookie in cookies:
            expiry_info = f" (expires: {cookie.get('expiry', 'session')})" if 'expiry' in cookie else ""
            print(f"  - {cookie['name']}: {cookie['value'][:20]}...{expiry_info}")
        
        print(f"\n🚀 Bây giờ bạn có thể chạy MCP server:")
        print(f"python notebooklm_mcp_server.py --cookies {output_file} --notebook YOUR_NOTEBOOK_ID --headless")
        
        if browser_name == "Edge":
            print(f"\n💡 Lưu ý: Cookies từ Edge sẽ hoạt động với Chrome driver trong MCP server!")
        
    except FileNotFoundError as e:
        print(f"❌ Error: {e}")
        print("\n💡 Hướng dẫn khắc phục:")
        print("1. Đảm bảo Edge hoặc Chrome đã được cài đặt")
        print("2. Đăng nhập vào NotebookLM trên Edge/Chrome ít nhất 1 lần")
        print("3. Đóng tất cả cửa sổ browser trước khi chạy script")
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        print("Hãy thử export cookies thủ công qua Browser Extension.")

if __name__ == "__main__":
    main()