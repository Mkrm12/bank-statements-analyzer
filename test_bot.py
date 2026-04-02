from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    # headless=False so we can watch the ghost work
    browser = p.chromium.launch(headless=False) 
    page = browser.new_page()
    print("🌐 Visiting Pulse...")
    page.goto("https://mkrm-pulse.streamlit.app/")
    
    # 1. Handle Hibernation
    try:
        wake_btn = page.locator("text=Yes, get this app back up")
        if wake_btn.count() > 0:
            wake_btn.click()
            print("😴 App was asleep. Clicked wake up!")
            page.wait_for_timeout(15000) 
    except Exception:
        pass
        
    # 2. The Ghost Keyboard (Visible Interaction)
    print("⚡ App is live. Initiating keyboard navigation...")
    
    # Give Streamlit 5 seconds to load the UI
    page.wait_for_timeout(5000)
    
    # Click the top-left corner just to make sure the window is focused
    page.mouse.click(10, 10)
    page.wait_for_timeout(1000)
    
    # Press 'Tab' 4 times slowly 
    print("⌨️ Tabbing through the UI...")
    for _ in range(4):
        page.keyboard.press("Tab")
        page.wait_for_timeout(500) # Half-second pause between tabs
        
    # Slowly type a string into whatever it highlighted
    print("✍️ Typing fake access code...")
    page.keyboard.type("elyos_auto_ping_test", delay=150) # delay=150 makes it type letter-by-letter
    
    page.wait_for_timeout(1000)
    
    # Press Enter
    page.keyboard.press("Enter")
    print("✅ Hit Enter. Server activity locked in.")

    print("🎉 Automation complete.")
    page.wait_for_timeout(4000) # Wait 4 seconds 
    browser.close()