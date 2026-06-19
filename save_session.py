import os
from playwright.sync_api import sync_playwright

PROFILE = "gc_profile"

with sync_playwright() as p:
    ctx = p.chromium.launch_persistent_context(PROFILE, headless=False)
    page = ctx.pages[0] if ctx.pages else ctx.new_page()
    page.goto("https://web.gc.com/")
    print("\n=========================================================")
    print(" Log in (email -> code -> password).")
    print(" When you SEE YOUR TEAMS, just CLOSE the browser window.")
    print("=========================================================\n")
    try:
        page.wait_for_event("close", timeout=0)
    except Exception:
        pass

print(">>> Saving your session...")
with sync_playwright() as p:
    ctx = p.chromium.launch_persistent_context(PROFILE, headless=True)
    page = ctx.pages[0] if ctx.pages else ctx.new_page()
    try:
        page.goto("https://web.gc.com/", wait_until="domcontentloaded", timeout=45000)
    except Exception:
        pass
    page.wait_for_timeout(4000)
    ctx.storage_state(path="gc_auth.json")
    ctx.close()

if os.path.exists("gc_auth.json") and os.path.getsize("gc_auth.json") > 50:
    print("\n[OK] Saved gc_auth.json -- logged in and remembered.")
else:
    print("\n[!] Session didn't save. Tell Claude what happened.")
