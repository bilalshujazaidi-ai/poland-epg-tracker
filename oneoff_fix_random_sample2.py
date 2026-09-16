#!/usr/bin/env python3
"""One-off: fix "Bird" found via a second true random sample audit
(2026-09-16), 30 more rows drawn from the resolved title_links cache
(excluding the first 30 already checked). Was wrongly cached as "3rd &
Bird" (a children's show) instead of Andrea Arnold's 2024 film "Bird" --
confirmed via full cast match (Nykiya Adams, Barry Keoghan, Franz Rogowski).

The other 4 titles flagged as uncertain in this batch (Lilly i kangurek,
Okiem Oscara, Talamasca: sekretny zakon, Westhampton) were independently
verified and are already correct -- not included here.
"""
import sys

import requests

from scraper import SUPABASE_URL, sb_headers

TITLE = "Bird"
TMDB_ID = 1128752
TMDB_TYPE = "movie"
IMDB_ID = "tt28277817"
ORIGINAL_NAME = "Bird"


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
