"""Test memory save functionality with Playwright."""
from playwright.sync_api import sync_playwright
import time

def test_memory_save():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        # Listen for console messages
        console_messages = []
        page.on("console", lambda msg: console_messages.append(f"[{msg.type}] {msg.text}"))

        print("Navigating to frontend...")
        page.goto('http://192.168.50.106:5173/')
        page.wait_for_load_state('networkidle')
        time.sleep(2)

        # Check page title
        title = page.title()
        print(f"Page title: {title}")

        # Check for any visible text or elements
        content = page.content()
        print(f"Page loaded, content length: {len(content)}")

        # Look for input elements or chat interface
        print("Looking for input elements...")
        textareas = page.locator('textarea').all()
        inputs = page.locator('input[type="text"]').all()
        buttons = page.locator('button').all()

        print(f"Found {len(textareas)} textareas, {len(inputs)} text inputs, {len(buttons)} buttons")

        # Take screenshot to see what's on screen
        page.screenshot(path='/tmp/frontend_test.png', full_page=True)
        print("Screenshot saved to /tmp/frontend_test.png")

        # Try to find and interact with the chat input
        try:
            # Try common selectors for chat inputs
            input_selector = 'textarea, input[type="text"], input[placeholder*="输入"], input[placeholder*="text"]'
            page.wait_for_selector(input_selector, timeout=5000)
            print("Found input element!")

            # Type a test message
            input_element = page.locator(input_selector).first
            input_element.fill("你好啊，肚肚")
            print("Filled input with test message")

            # Try to submit (usually Enter key or a button)
            input_element.press("Enter")
            print("Pressed Enter")

            # Wait for response
            time.sleep(3)

            # Check console for any errors
            errors = [m for m in console_messages if 'error' in m.lower() or 'exception' in m.lower()]
            if errors:
                print(f"Console errors: {errors}")

            # Take another screenshot
            page.screenshot(path='/tmp/frontend_after_chat.png', full_page=True)
            print("Screenshot after chat saved")

        except Exception as e:
            print(f"Could not interact with chat: {e}")

        # Close browser
        browser.close()
        print("Browser closed")

        # Now check if memory was saved
        print("\n--- Checking memory files ---")
        import subprocess
        result = subprocess.run(['ls', '-la', '/home/bo/projects/python/python_hub/memory/summaries/'], capture_output=True, text=True)
        print(f"Summaries dir:\n{result.stdout}")
        result = subprocess.run(['ls', '-la', '/home/bo/projects/python/python_hub/memory/global/'], capture_output=True, text=True)
        print(f"Global dir:\n{result.stdout}")

if __name__ == "__main__":
    test_memory_save()