#!/usr/bin/env python3
"""Supabase billing user sync watcher for Open WebUI.

This script fetches all billing users from the Supabase ``billing_users``
table and upserts those users into Open WebUI via its internal API. It
can be run once (e.g. from cron) or in a continuous loop every minute by
supplying the ``--loop`` flag.

Environment variables loaded from a `.env` file:
    SUPABASE_URL        - Base URL of your Supabase project.
    SUPABASE_API_KEY    - Service role API key for Supabase.
    OWUI_AUTH_TOKEN     - Bearer token for OWUI internal API.
    OWUI_INTERNAL_API   - OWUI internal upsert-user endpoint URL.

Example cron entry to run every minute:
    * * * * * /usr/bin/python3 /path/to/supabase_watcher.py
"""
from __future__ import annotations

import argparse
import os
import time
from typing import Dict, Optional

import requests
from dotenv import load_dotenv

# Map billing_users.tier -> OWUI group_id
TIER_GROUP_MAP: Dict[str, str] = {"free": "1", "standard": "2", "pro": "3"}


def sync_users() -> None:
    """Fetch users from Supabase and upsert them into OWUI."""
    load_dotenv()

    supabase_url: Optional[str] = os.getenv("SUPABASE_URL")
    supabase_api_key: Optional[str] = os.getenv("SUPABASE_API_KEY")
    owui_auth_token: Optional[str] = os.getenv("OWUI_AUTH_TOKEN")
    owui_internal_api: Optional[str] = os.getenv("OWUI_INTERNAL_API")

    if not all([supabase_url, supabase_api_key, owui_auth_token, owui_internal_api]):
        print("Missing required environment variables.")
        return

    headers = {
        "apikey": supabase_api_key,
        "Authorization": f"Bearer {supabase_api_key}",
        "Accept": "application/json",
        "Accept-Profile": "public",
        "Prefer": "count=exact",
    }
    try:
        # Only ACTIVE users; pull email+tier (the column is 'tier', not 'plan')
        params = {
            "select": "email,tier,status",
            "status": "eq.active",
            "order": "email.asc",
        }
        response = requests.get(
            f"{supabase_url}/rest/v1/billing_users",
            headers=headers,
            params=params,
            timeout=30,
        )
    except requests.RequestException as exc:
        print(f"Error fetching users: {exc}")
        return

    if response.status_code != 200:
        print(f"Failed to fetch users: {response.status_code} {response.text}")
        return

    try:
        users = response.json()
    except ValueError as exc:
        print(f"Invalid JSON from Supabase: {exc}")
        return

    created = 0
    updated = 0
    for user in users:
        email = user.get("email")
        tier = (user.get("tier") or "free").lower()
        group_id = TIER_GROUP_MAP.get(tier, TIER_GROUP_MAP["free"])
        if not email:
            continue

        payload = {"email": email, "group_id": group_id}
        try:
            r = requests.post(
                owui_internal_api,
                headers={
                    "Authorization": f"Bearer {owui_auth_token}",
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=30,
            )
        except requests.RequestException as exc:
            print(f"OWUI upsert error for {email}: {exc}")
            continue
        if r.status_code in (200, 201):
            created += 1
        elif r.status_code in (204,):
            updated += 1
        else:
            print(f"OWUI upsert failed for {email}: {r.status_code} {r.text}")

    print(f"sync complete: created={created} updated={updated}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--loop", action="store_true", help="Run every 60s")
    args = parser.parse_args()
    if args.loop:
        while True:
            sync_users()
            time.sleep(60)
    else:
        sync_users()


if __name__ == "__main__":
    main()
