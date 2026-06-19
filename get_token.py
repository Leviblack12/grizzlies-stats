"""
Capture a fresh gc-token from a live GameChanger web session.

Local mode (default):  uses the saved Chromium profile (gc_profile/) in a
  VISIBLE window so GC's headless-bot detection doesn't fire.

CI mode (GC_AUTH env var set):  restores session from gc_auth.json and runs
  headless; the valid session cookies let the page load without being blocked.
"""
import os
import sys
from playwright.sync_api import sync_playwright

PROFILE  = os.environ.get("GC_PROFILE", "gc_profile")
GC_AUTH  = os.environ.get("GC_AUTH", "")          # JSON content of gc_auth.json
HEADLESS = os.environ.get("GC_HEADLESS", "0") == "1"

token     = None
final_url = "?"

with sync_playwright() as p:
    if GC_AUTH:
        # ── CI mode: restore session from the GC_AUTH secret ──────────────────
        auth_path = "gc_auth.json"
        with open(auth_path, "w") as fh:
            fh.write(GC_AUTH)
        browser = p.chromium.launch(headless=True)
        ctx     = browser.new_context(storage_state=auth_path)
        page    = ctx.new_page()
        _own_browser = True
    else:
        # ── Local mode: persistent profile, visible window ─────────────────────
        ctx  = p.chromium.launch_persistent_context(PROFILE, headless=HEADLESS)
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        browser      = None
        _own_browser = False

    def on_request(req):
        global token
        if token is None and "api.team-manager.gc.com" in req.url:
            t = req.headers.get("gc-token")
            if t:
                token = t

    page.on("request", on_request)

    try:
        page.goto("https://web.gc.com/teams",
                  wait_until="domcontentloaded", timeout=30000)
    except Exception as e:
        print(f"[get_token] goto warning: {e}", file=sys.stderr)

    # Give the app time to boot and fire API calls (up to ~15 s)
    page.wait_for_timeout(3000)
    for _ in range(12):
        if token:
            break
        page.wait_for_timeout(1000)

    try:
        final_url = page.url
    except Exception:
        pass

    # Log the final URL so we can confirm we're actually logged in
    print(f"[get_token] ended at: {final_url}", file=sys.stderr)

    ctx.close()
    if _own_browser and browser:
        browser.close()

if token:
    print(token)
else:
    print(f"::error::No gc-token captured. Browser ended at: {final_url}",
          file=sys.stderr)
    sys.exit(2)
