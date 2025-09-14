#!/usr/bin/env python3
"""
Session-based NotebookLM automation - maintains login session between runs
"""

import os
import json
from pathlib import Path
from dataclasses import dataclass
from typing import Optional, Dict, Any, List
import time

try:
    import undetected_chromedriver as uc
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.common.exceptions import TimeoutException
    USE_UNDETECTED = True
except ImportError:
    USE_UNDETECTED = False

@dataclass
class PersistentConfig:
    notebook_id: str
    profile_dir: str = "./chrome_profile"
    headless: bool = False
    timeout: int = 30

class PersistentNotebookLM:
    def __init__(self, config: PersistentConfig):
        self.config = config
        self.driver: Optional[Any] = None
        
    def start_persistent_session(self) -> bool:
        """Start Chrome với persistent profile"""
        if not USE_UNDETECTED:
            print("❌ Cần cài undetected-chromedriver: pip install undetected-chromedriver")
            return False
            
        # Tạo profile directory
        profile_path = Path(self.config.profile_dir).absolute()
        profile_path.mkdir(exist_ok=True)
        
        print(f"🔄 Starting Chrome với profile: {profile_path}")
        
        options = uc.ChromeOptions()
        options.add_argument(f"--user-data-dir={profile_path}")
        options.add_argument("--no-first-run")
        options.add_argument("--no-default-browser-check")
        
        if self.config.headless:
            options.add_argument("--headless=new")
            
        self.driver = uc.Chrome(options=options, version_main=None)
        self.driver.set_page_load_timeout(self.config.timeout)
        
        return True
        
    def check_login_status(self) -> bool:
        """Kiểm tra xem đã login chưa"""
        if not self.driver:
            return False
            
        try:
            self.driver.get(f"https://notebooklm.google.com/notebook/{self.config.notebook_id}")
            time.sleep(3)
            
            current_url = self.driver.current_url
            print(f"📍 Current URL: {current_url}")
            
            # Nếu không bị redirect về login page
            if "signin" not in current_url and "accounts.google.com" not in current_url:
                print("✅ Already logged in!")
                return True
            else:
                print("🔐 Need to login")
                return False
                
        except Exception as e:
            print(f"❌ Error checking login: {e}")
            return False
    
    def wait_for_manual_login(self) -> bool:
        """Đợi user login manual 1 lần duy nhất"""
        print("📋 ONE-TIME SETUP: Please login manually")
        print("   1. Login with your Google account")
        print(f"   2. Navigate to your notebook: https://notebooklm.google.com/notebook/{self.config.notebook_id}")
        print("   3. Wait until notebook loads completely")
        print("   4. Press Enter when done...")
        
        input("Press Enter khi đã login và vào được notebook...")
        
        # Verify login worked
        return self.check_login_status()
    
    def send_chat(self, message: str) -> str:
        """Gửi chat message"""
        if not self.driver:
            return "Driver not initialized"
            
        # Đảm bảo đang ở notebook page
        if not self.check_login_status():
            return "Not logged in or notebook not accessible"
        
        try:
            # Tìm chat input (placeholder - cần real selector)
            print(f"💬 Sending message: {message}")
            
            # TODO: Implement real chat selectors
            # chat_input = self.driver.find_element(By.CSS_SELECTOR, "[data-testid='chat-input']")
            # chat_input.send_keys(message)
            # chat_input.send_keys(Keys.RETURN)
            
            print("✅ Message sent (simulated)")
            return "Message sent successfully"
            
        except Exception as e:
            return f"Error sending message: {e}"
    
    def get_response(self) -> str:
        """Lấy response từ NotebookLM"""
        try:
            # TODO: Implement real response selector
            # response_element = WebDriverWait(self.driver, 10).until(
            #     EC.presence_of_element_located((By.CSS_SELECTOR, "[data-testid='chat-response']"))
            # )
            # return response_element.text
            
            return "Response placeholder - need real selectors"
            
        except Exception as e:
            return f"Error getting response: {e}"
    
    def close(self):
        """Đóng browser nhưng giữ session"""
        if self.driver:
            print("💾 Saving session...")
            self.driver.quit()

async def main():
    """Test persistent session"""
    config = PersistentConfig(
        notebook_id="4741957b-f358-48fb-a16a-da8d20797bc6",
        profile_dir="./chrome_profile_notebooklm",
        headless=False
    )
    
    nlm = PersistentNotebookLM(config)
    
    if not nlm.start_persistent_session():
        return
    
    try:
        # Kiểm tra đã login chưa
        if nlm.check_login_status():
            print("🎉 Already authenticated! No manual login needed.")
        else:
            # Chỉ cần login manual 1 lần duy nhất
            if not nlm.wait_for_manual_login():
                print("❌ Login failed")
                return
                
        # Từ lần sau sẽ auto
        print("\n🚀 Testing chat functionality...")
        
        # Test chat
        message = input("Enter message to send: ") or "Hello NotebookLM!"
        result = nlm.send_chat(message)
        print(f"📤 Send result: {result}")
        
        # Get response
        response = nlm.get_response()
        print(f"📥 Response: {response}")
        
        print("\n✅ Session saved! Next time sẽ không cần login manual.")
        
    finally:
        nlm.close()

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())