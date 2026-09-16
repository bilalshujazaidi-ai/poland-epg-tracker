#!/usr/bin/env python3
"""One-off: fix "FBI", found wrongly cached as "FBI: International" while
spot-checking a fresh scrape run. This cache row predates all of today's
matching fixes (resolved_at 09:07, before the pick_best/cast-crosscheck
work), so it was never touched by any of them -- a reminder that fixed
logic only ever applies to new resolutions, never to what's already cached.
Cast (Missy Peregrym, Zeeko Zaki, Jeremy Sisto) confirmed via web search as
the flagship "FBI" (2018-, tt7491982), not the International spinoff.
"""
import sys

import requests

from scraper import SUPABASE_URL, sb_headers

TITLE = "FBI"
TMDB_ID = 80748
TMDB_TYPE = "tv"
IMDB_ID = "tt7491982"
ORIGINAL_NAME = "FBI"


def sb_patch(table, params, data):
    r = requests.patch(
        f"{SUPABASE_URL}/rest/v1/{table}",
        headers=sb_headers(prefer="return=representation"),
        params=params,
        json=data,
        timeout=30,
    )
    if not r.ok:
        print(f"  patch failed for {table} {params}: {r.status_code} {r.text}")
        r.raise_for_status()
    return r.json()


def main():
    imdb_url = f"https://www.imdb.com/title/{IMDB_ID}/"

    updated = sb_patch(
        "title_links",
        {"title": f"eq.{TITLE}"},
        {
            "tmdb_id": TMDB_ID,
            "tmdb_type": TMDB_TYPE,
            "imdb_id": IMDB_ID,
            "imdb_url": imdb_url,
            "matched_original_name": ORIGINAL_NAME,
        },
    )
    print(f"title_links rows updated: {len(updated)}")

    updated = sb_patch(
        "entries",
        {"title": f"eq.{TITLE}"},
        {"imdb_url": imdb_url, "original_name": ORIGINAL_NAME},
    )
    print(f"entries rows updated: {len(updated)}")


if __name__ == "__main__":
    sys.exit(main())
