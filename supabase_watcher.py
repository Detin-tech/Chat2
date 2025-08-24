#!/usr/bin/env python3
"""Supabase user sync watcher for Prosper Chat.

This script fetches all users from the Supabase REST API and upserts
those users into Prosper Chat via its internal API. It can be run once
(e.g. from cron) or in a continuous loop every minute by supplying the
``--loop`` flag.

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
from typing import Dict

import requests
from dotenv import load_dotenv

PLAN_GROUP_MAP: Dict[str, str] = {"free": "1", "standard": "2", "pro": "3"}


def sync_users() -> None:
    """Fetch users from Supabase and upsert them into OWUI."""
    load_dotenv()

    supabase_url = os.getenv("SUPABASE_URL")
    supabase_api_key = os.getenv("SUPABASE_API_KEY")
    owui_auth_token = os.getenv("OWUI_AUTH_TOKEN")
    owui_internal_api = os.getenv("OWUI_INTERNAL_API")

    if not all([supabase_url, supabase_api_key, owui_auth_token, owui_internal_api]):
        print("Missing required environment variables.")
        return

    headers = {
        "apikey": supabase_api_key,
        "Authorization": f"Bearer {supabase_api_key}",
    }
    try:
        response = requests.get(
            f"{supabase_url}/rest/v1/users?select=email,plan",
            headers=headers,
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
        plan = user.get("plan", "free")
        group_id = PLAN_GROUP_MAP.get(plan, PLAN_GROUP_MAP["free"])

        payload = {"email": email, "group_id": group_id}
        headers = {"Authorization": owui_auth_token}
        try:
            resp = requests.post(owui_internal_api, json=payload, headers=headers, timeout=30)
        except requests.RequestException as exc:
            print(f"Request error for {email}: {exc}")
            continue

        if resp.status_code == 200:
            try:
                data = resp.json()
            except ValueError:
                print(f"{email} returned invalid JSON: {resp.text}")
                continue

            status = data.get("status")
            if status == "created":
                created += 1
                print(f"{email} created")
            elif status == "updated":
                updated += 1
                print(f"{email} updated")
            else:
                print(f"{email} unexpected response: {data}")
        else:
            print(f"Failed to upsert {email}: {resp.status_code} {resp.text}")

    print(f"Totals - created: {created}, updated: {updated}")


def main(loop: bool = False) -> None:
    """Run the sync once or in a continuous minute loop."""
    if loop:
        while True:
            sync_users()
            time.sleep(60)
    else:
        sync_users()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Supabase watcher for OWUI")
    parser.add_argument(
        "--loop",
        action="store_true",
        help="Run continuously every minute instead of once",
    )
    args = parser.parse_args()
    main(loop=args.loop)
