#!/usr/bin/env python3
"""Sync active Supabase billing users to OpenWebUI.

Reads `public.billing_users` (status=active), maps `tier`→OWUI group,
and calls OWUI `/api/internal/upsert-users` with `X-API-KEY`.
On any HTTP error, exits non-zero so systemd can alert/retry.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
import time
from typing import Dict, Iterable, List

import requests
from dotenv import load_dotenv

# Map billing_users.tier -> OWUI group_id
TIER_GROUP_MAP: Dict[str, str] = {"free": "1", "standard": "2", "pro": "3"}
MAX_BATCH = 100


def _chunked(items: List[Dict[str, str]], size: int) -> Iterable[List[Dict[str, str]]]:
    for i in range(0, len(items), size):
        yield items[i : i + size]


def health_checks(supabase_url: str, supabase_key: str, owui_url: str) -> None:
    """Run startup health checks and exit on failure."""
    headers = {
        "apikey": supabase_key,
        "Authorization": f"Bearer {supabase_key}",
        "Accept": "application/json",
    }
    count_url = f"{supabase_url}/rest/v1/billing_users"
    try:
        r = requests.get(count_url, headers=headers, params={"select": "count"}, timeout=30)
    except requests.RequestException as exc:  # pragma: no cover - network
        logging.error("Supabase health check failed: %s", exc)
        sys.exit(1)

    if r.status_code != 200:
        logging.error(
            "Supabase health check failed: %s %s", r.status_code, r.text
        )
        sys.exit(1)

    try:
        r2 = requests.get(f"{owui_url}/openapi.json", timeout=30)
    except requests.RequestException as exc:  # pragma: no cover - network
        logging.error("OWUI health check failed: %s", exc)
        sys.exit(1)

    if r2.status_code != 200 or "/api/internal/upsert-users" not in r2.text:
        logging.error(
            "OWUI health check failed: status=%s body=%s", r2.status_code, r2.text
        )
        sys.exit(1)


def fetch_active_users(supabase_url: str, supabase_key: str) -> List[Dict[str, str]]:
    """Fetch active billing users from Supabase."""
    headers = {
        "apikey": supabase_key,
        "Authorization": f"Bearer {supabase_key}",
        "Accept": "application/json",
    }
    params = {
        "select": "email,tier,status,updated_at",
        "status": "eq.active",
        "order": "updated_at.asc",
    }
    url = f"{supabase_url}/rest/v1/billing_users"
    try:
        r = requests.get(url, headers=headers, params=params, timeout=30)
    except requests.RequestException as exc:  # pragma: no cover - network
        logging.error("Supabase request error: %s", exc)
        sys.exit(1)

    if r.status_code != 200:
        redacted = url.replace(supabase_url, "{SUPABASE_URL}")
        logging.error(
            "Supabase request failed URL=%s status=%s body=%s",
            redacted,
            r.status_code,
            r.text,
        )
        sys.exit(1)

    try:
        return r.json()
    except ValueError as exc:
        logging.error("Invalid JSON from Supabase: %s", exc)
        sys.exit(1)


def upsert_batches(users: List[Dict[str, str]], owui_url: str, token: str) -> None:
    """Send users to OWUI in batches and log summary."""
    total_received = total_created = total_updated = total_failed = 0
    endpoint = f"{owui_url}/api/internal/upsert-users"
    headers = {"X-API-KEY": token, "Content-Type": "application/json"}

    for batch in _chunked(users, MAX_BATCH):
        try:
            r = requests.post(endpoint, headers=headers, json={"users": batch}, timeout=30)
        except requests.RequestException as exc:  # pragma: no cover - network
            logging.error("OWUI request error: %s", exc)
            logging.error("First emails: %s", ", ".join(u["email"] for u in batch[:20]))
            sys.exit(1)

        if not (200 <= r.status_code < 300):
            logging.error(
                "OWUI upsert failed path=/api/internal/upsert-users status=%s body=%s",
                r.status_code,
                r.text,
            )
            logging.error("First emails: %s", ", ".join(u["email"] for u in batch[:20]))
            if r.status_code == 401:
                logging.error(
                    "OWUI auth rejected. Regenerate an Admin API key and retry."
                )
            sys.exit(1)

        try:
            res = r.json()
        except ValueError:
            res = {}
        total_received += res.get("received", 0)
        total_created += res.get("created", 0)
        total_updated += res.get("updated", 0)
        total_failed += res.get("failed", 0)

    logging.info(
        "OWUI summary: received=%d created=%d updated=%d failed=%d",
        total_received,
        total_created,
        total_updated,
        total_failed,
    )


def sync_once() -> None:
    """Perform a single sync run."""
    load_dotenv()
    supabase_url = os.getenv("SUPABASE_URL")
    supabase_key = os.getenv("SUPABASE_API_KEY")
    owui_url = os.getenv("OWUI_URL")
    owui_token = os.getenv("OWUI_AUTH_TOKEN")

    if not all([supabase_url, supabase_key, owui_url, owui_token]):
        logging.error("Missing required environment variables")
        sys.exit(1)

    health_checks(supabase_url, supabase_key, owui_url)

    users = fetch_active_users(supabase_url, supabase_key)
    if not users:
        logging.info("no actives")
        return

    payload = []
    for user in users:
        email = user.get("email")
        if not email:
            continue
        tier = (user.get("tier") or "free").lower()
        group_id = TIER_GROUP_MAP.get(tier, TIER_GROUP_MAP["free"])
        payload.append({"email": email, "group_id": group_id})

    logging.info("fetched=%d sending=%d", len(users), len(payload))

    upsert_batches(payload, owui_url, owui_token)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--loop", action="store_true", help="Run every 60 seconds")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )

    if args.loop:
        while True:
            sync_once()
            time.sleep(60)
    else:
        sync_once()


if __name__ == "__main__":
    main()

