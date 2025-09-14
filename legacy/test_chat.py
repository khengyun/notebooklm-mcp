#!/usr/bin/env python3
"""
Test MCP server with real chat functionality
"""
import asyncio
import json
import sys
from pathlib import Path

# Add current directory to path
sys.path.insert(0, str(Path(__file__).parent))

from notebooklm_mcp_server import SeleniumManager, ServerConfig

async def test_mcp_chat():
    """Test MCP server chat functionality"""
    print("🚀 Testing NotebookLM MCP Server Chat...")
    
    # Config with persistent session
    config = ServerConfig(
        cookies_path=None,  # Don't use cookies, use persistent session
        headless=False,     # Show browser for debugging
        timeout=60,
        debug=True,
        default_notebook_id="4741957b-f358-48fb-a16a-da8d20797bc6"
    )
    
    selenium_mgr = SeleniumManager(config)
    
    try:
        # Start browser with persistent session
        print("1. 🌐 Starting browser with persistent session...")
        selenium_mgr.start()
        
        # Check authentication (should be auto with persistent session)
        print("2. 🔐 Checking authentication...")
        auth_success = selenium_mgr.ensure_authenticated()
        
        if not auth_success:
            print("⚠️  Need manual login - browser is open")
            print("   Please login and press Enter when ready...")
            input()
        
        # Test send message với streaming response
        print("\n3. 💬 Testing chat functionality với streaming response...")
        test_message = input("Enter message to send (or Enter for default): ").strip()
        if not test_message:
            test_message = "Xin chào! Bạn có thể tóm tắt nội dung chính của tài liệu này không?"
        
        print(f"📤 Sending: {test_message}")
        try:
            selenium_mgr.send_chat_message(test_message)
            print("✅ Message sent successfully!")
            
            # Wait for complete streaming response
            print("📥 Waiting for streaming response to complete...")
            response = selenium_mgr.get_chat_response(wait_for_completion=True, max_wait=60)
            print(f"🤖 Complete Response: {response}")
            
        except Exception as e:
            print(f"❌ Chat error: {e}")
        
        # Test quick response check
        print("\n4. ⚡ Testing quick response check...")
        try:
            quick_response = selenium_mgr.get_chat_response(wait_for_completion=False)
            print(f"⚡ Quick check: {quick_response[:200]}...")
        except Exception as e:
            print(f"❌ Quick response error: {e}")
        
        # Test additional messages với streaming
        while True:
            follow_up = input("\nSend another message (Enter to quit): ").strip()
            if not follow_up:
                break
                
            print(f"📤 Sending: {follow_up}")
            try:
                selenium_mgr.send_chat_message(follow_up)
                print("⏳ Waiting for streaming response...")
                response = selenium_mgr.get_chat_response(wait_for_completion=True, max_wait=45)
                print(f"🤖 Complete Response: {response}")
            except Exception as e:
                print(f"❌ Error: {e}")
        
        print("\n✅ Chat test completed!")
        
    finally:
        # Keep session alive, just close for now
        print("💾 Closing browser (session saved)...")
        selenium_mgr.stop()

if __name__ == "__main__":
    asyncio.run(test_mcp_chat())