# -*- coding: utf-8 -*-
"""
First-run setup. Run this once after cloning:

    python setup.py

It walks you through copying four cookies from your logged-in Instagram
browser, checks they work, and saves them to a git-ignored .env file.
Nothing is sent anywhere except to instagram.com.
"""
import os, sys, subprocess

BASE = os.path.dirname(os.path.abspath(__file__))
ENV = os.path.join(BASE, ".env")

COOKIES = [
    ("IG_SESSIONID", "sessionid", True),
    ("IG_CSRFTOKEN", "csrftoken", True),
    ("IG_DS_USER_ID", "ds_user_id", True),
    ("IG_MID", "mid", False),
]

INSTRUCTIONS = """
================================================================================
  INSTAGRAM MEDIA X CREATIVES - FIRST-RUN SETUP
================================================================================

This tool works through YOUR Instagram login. It needs four cookies from a
browser where you are already logged in to Instagram. Here is how to get them:

  1. Open Chrome (or Edge) and log in to https://www.instagram.com
  2. Press F12 to open Developer Tools
  3. Click the "Application" tab at the top (if you don't see it, click >>)
  4. On the left, expand "Cookies" and click "https://www.instagram.com"
  5. You will see a table. Find these rows and copy the "Value" column:
         sessionid      (long, contains %3A)
         csrftoken      (32 letters/numbers)
         ds_user_id     (a number)
         mid            (optional)

Paste each value below when asked. They are saved ONLY to a local file
called .env which git ignores, so they never get uploaded anywhere.

IMPORTANT: a sessionid is your login. Do not share it or paste it into chat,
documents or code. If you think it leaked, go to Instagram > Settings >
Security > Login activity and log out of all sessions - that kills it.
================================================================================
"""


def ask(label, cookie, required):
    while True:
        val = input(f"  {cookie:<12} {'(required)' if required else '(optional, Enter to skip)'}: ").strip().strip('"').strip("'")
        if val or not required:
            return val
        print("  This one is required.")


def check_session(cookies):
    """Hit one cheap authenticated endpoint. Returns (ok, message)."""
    try:
        from curl_cffi import requests as cffi
    except ImportError:
        return None, "curl_cffi not installed - run: pip install -r requirements.txt"
    try:
        # Same call every tool in this repo depends on: the user's own profile
        # by pk. Anonymous or dead cookies get the login page or 401/403.
        pk = cookies.get("ds_user_id", "")
        r = cffi.get(f"https://www.instagram.com/api/v1/users/{pk}/info/",
                     headers={"x-ig-app-id": "936619743392459",
                              "x-csrftoken": cookies.get("csrftoken", ""),
                              "User-Agent": "Instagram 269.0.0.18.75 Android (26/8.0.0; 480dpi; 1080x1920; "
                                            "OnePlus; ONEPLUS A6003; OnePlus6; qcom; en_US; 314665256)"},
                     cookies=cookies, impersonate="chrome120", timeout=20)
        ct = r.headers.get("content-type", "")
        if r.status_code == 200 and "json" in ct:
            try:
                u = r.json().get("user") or {}
            except Exception:
                u = {}
            if u.get("username"):
                return True, f"logged in as @{u['username']}"
        if r.status_code in (401, 403) or (r.status_code == 200 and "json" not in ct):
            return False, "Instagram does not recognise these cookies as a live login. Re-copy them from a browser that is logged in."
        if r.status_code == 429:
            return None, "Instagram is rate-limiting right now (HTTP 429); cannot verify"
        return False, f"unexpected response HTTP {r.status_code}"
    except Exception as e:
        if "redirect" in type(e).__name__.lower():
            return False, "Instagram bounced these cookies to the login page. Re-copy them from a browser that is logged in."
        return None, f"could not reach instagram.com ({type(e).__name__})"


def main():
    print(INSTRUCTIONS)
    if os.path.exists(ENV):
        ans = input(".env already exists. Overwrite it? [y/N]: ").strip().lower()
        if ans != "y":
            print("Kept the existing .env. Run again if you want to replace it.")
            return

    values = {}
    for var, cookie, req in COOKIES:
        values[var] = ask(var, cookie, req)

    cookie_dict = {c: values[v] for v, c, _ in COOKIES if values[v]}
    print("\nChecking the session with Instagram...")
    ok, msg = check_session(cookie_dict)
    if ok:
        print(f"  OK - {msg}")
    elif ok is None:
        print(f"  Could not verify ({msg}). Saving anyway; the first real run will tell you if it fails.")
    else:
        print(f"  FAILED - {msg}")
        if input("Save anyway? [y/N]: ").strip().lower() != "y":
            print("Not saved. Run python setup.py again.")
            return

    with open(ENV, "w", encoding="utf-8") as f:
        f.write("# Instagram session cookies. Git-ignored. Never commit or share this file.\n")
        for var, _, _ in COOKIES:
            f.write(f"{var}={values[var]}\n")
    print(f"\nSaved to {ENV}")

    print("\nInstalling Playwright's browser (needed for the brand tier scan)...")
    try:
        subprocess.run([sys.executable, "-m", "playwright", "install", "chromium"], check=False)
    except Exception as e:
        print(f"  Skipped ({e}). Run manually later: python -m playwright install chromium")

    print("""
================================================================================
  DONE. You are set up.

  Open this folder in Claude Code (or any agent IDE) and just say what you
  want, for example:

    "find kolkata food creators above 20k followers with email"
    "audit these pages for invest / dont invest"   (then paste the list)
    "who did CRED collaborate with in the last 2 years, in tiers"

  Or run the scripts directly - see README.md.
================================================================================
""")


if __name__ == "__main__":
    main()
