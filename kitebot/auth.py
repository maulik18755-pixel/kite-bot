"""Kite Connect login. The access token expires every day, so a human logs in each morning.

API key and secret come from the KITE_API_KEY and KITE_API_SECRET environment variables.
"""

import json
import os
from datetime import date
from pathlib import Path
from urllib.parse import parse_qs, urlparse

TOKEN_FILE = Path(".kite_token.json")


def _kite():
    from kiteconnect import KiteConnect

    api_key = os.environ.get("KITE_API_KEY")
    if not api_key:
        raise SystemExit("Set KITE_API_KEY (and KITE_API_SECRET) in your environment first.")
    return KiteConnect(api_key=api_key)


def login_interactive() -> None:
    """Print the login URL, take the redirect URL back, and save today's access token."""
    kite = _kite()
    print("1. Open this URL and log in to Zerodha:\n  ", kite.login_url())
    print("2. After login you are redirected. Paste the full redirect URL (or just the request_token):")
    pasted = input("> ").strip()
    token = parse_qs(urlparse(pasted).query).get("request_token", [pasted])[0]
    session = kite.generate_session(token, api_secret=os.environ["KITE_API_SECRET"])
    TOKEN_FILE.write_text(json.dumps({"access_token": session["access_token"], "date": date.today().isoformat()}))
    TOKEN_FILE.chmod(0o600)
    print("Logged in. Token saved for today.")


def get_kite():
    """Return an authenticated KiteConnect client, or exit if today's login is missing."""
    if not TOKEN_FILE.exists():
        raise SystemExit("No Kite session. Run: python -m kitebot login")
    saved = json.loads(TOKEN_FILE.read_text())
    if saved.get("date") != date.today().isoformat():
        raise SystemExit("Kite session is from a previous day. Run: python -m kitebot login")
    kite = _kite()
    kite.set_access_token(saved["access_token"])
    return kite
