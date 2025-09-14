#!/usr/bin/env python3
"""
Test script để chat với NotebookLM qua MCP server
"""
import asyncio
import json
import sys
from pathlib import Path

# Add current directory to path để import server
sys.path.insert(0, str(Path(__file__).parent))

from notebooklm_mcp_server import SeleniumManager, ServerConfig

async def test_chat():
    """Test chat functionality với NotebookLM"""
    print("🚀 Testing NotebookLM Chat...")
    
    # Config
    config = ServerConfig(
        cookies_path="cookies.json",
        headless=False,  # Để xem browser behavior và login manual nếu cần
        timeout=60,      # Tăng timeout
        debug=True,
        default_notebook_id="4741957b-f358-48fb-a16a-da8d20797bc6"
    )
    
    selenium_mgr = SeleniumManager(config)
    
    try:
        # Start browser
        print("1. 🌐 Starting browser...")
        selenium_mgr.start()
        
        # Authenticate
        print("2. 🔐 Authenticating...")
        auth_success = selenium_mgr.ensure_authenticated()
        
        if not auth_success:
            print("⚠️  Auto-authentication failed, but browser is open")
            print("   Please login manually in the browser window")
            print("   Press Enter when you're logged in and see your notebook...")
            input()
            
            # Check if manual login worked
            current_url = selenium_mgr.driver.current_url if selenium_mgr.driver else ""
            if "notebooklm.google.com" in current_url and "signin" not in current_url:
                print("✅ Manual authentication successful!")
            else:
                print("❌ Still not authenticated. Continuing anyway for demo...")
        else:
            print("✅ Authentication successful!")
        
        # Navigate to notebook
        print("3. 📓 Navigating to notebook...")
        notebook_url = selenium_mgr.navigate_to_notebook("4741957b-f358-48fb-a16a-da8d20797bc6")
        print(f"   Current URL: {notebook_url}")
        
        # Wait for user input
        print("\n4. 💬 Ready to chat!")
        print("   Browser đang mở. Hãy kiểm tra NotebookLM UI.")
        print("   Nhấn Enter khi sẵn sàng gửi message...")
        input()
        
        # Send test message
        test_message = input("Nhập message để gửi: ") or "Hello, NotebookLM!"
        print(f"5. 📤 Sending message: '{test_message}'")
        
        try:
            selenium_mgr.send_chat_message(test_message)
            print("✅ Message sent!")
            
            # Wait and get response
            print("6. 📥 Getting response...")
            await asyncio.sleep(3)  # Wait for response
            
            response = selenium_mgr.get_chat_response()
            print(f"📨 Response: {response[:200]}...")
            
        except Exception as e:
            print(f"❌ Chat error: {e}")
            print("💡 This is expected - need to implement real DOM selectors")
        
        # Keep browser open for manual inspection
        print("\n7. 🔍 Browser kept open for inspection.")
        print("   Check if authentication worked and notebook loaded.")
        print("   Press Enter to close...")
        input()
        
    finally:
        selenium_mgr.stop()
        print("✅ Test completed!")

if __name__ == "__main__":
    asyncio.run(test_chat())