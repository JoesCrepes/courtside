"""Sign in to Supabase and call the deployed API as that user.

    python scripts/signin_check.py

Reads SUPABASE_URL, SUPABASE_ANON_KEY and COURTSIDE_API_URL from .env (or
prompts), asks for email and password, and prints /context. The access token
is never printed.
"""

from __future__ import annotations

import getpass
import os
import sys
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from courtside.config import _load_dotenv  # noqa: E402


def setting(name: str, default: str | None = None) -> str:
    return os.environ.get(name) or default or input(f"{name}: ").strip()


def main() -> int:
    _load_dotenv(Path(".env"))
    supabase = setting("SUPABASE_URL").rstrip("/")
    anon = setting("SUPABASE_ANON_KEY")
    api = setting("COURTSIDE_API_URL", "https://courtside-azure-six.vercel.app").rstrip("/")
    email = input("email: ").strip()
    password = getpass.getpass("password: ")

    r = requests.post(
        f"{supabase}/auth/v1/token", params={"grant_type": "password"},
        headers={"apikey": anon}, json={"email": email, "password": password}, timeout=20,
    )
    if not r.ok:
        print(f"sign-in failed ({r.status_code}): {r.json().get('msg') or r.text[:200]}")
        return 1
    token = r.json()["access_token"]
    print("signed in")

    r = requests.get(f"{api}/context", headers={"Authorization": f"Bearer {token}"}, timeout=20)
    print(f"GET /context -> {r.status_code}: {r.json()}")
    return 0 if r.ok else 1


if __name__ == "__main__":
    sys.exit(main())
