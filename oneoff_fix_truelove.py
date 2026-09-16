#!/usr/bin/env python3
"""One-off: correct the wrong IMDb match for "TrueLove" caused by the
pick_best below-only-year bug (fixed in scraper.py). Deletes itself and its
workflow from the repo in the same run once the patch succeeds -- this is a
single historical correction, not a job meant to run again.
"""
import sys

import requests

from scraper import SUPABASE_URL, sb_headers


def sb_patch(table, params, data):
    r = requests.patch(
        f"{SUPABASE_URL}/rest/v1/{table}",
        headers=sb_headers(prefer="return=representation"),
        params=params,
        json=data,
        timeout=30,
    )
    if not r.ok:
        print(f"  patch failed for {table}: {r.status_code} {r.text}")
        r.raise_for_status()
    return r.json()


def main():
    updated = sb_patch(
        "title_links",
        {"slug": "eq.truelove"},
        {
            "tmdb_id": 218353,
            "imdb_id": "tt20453286",
            "imdb_url": "https://www.imdb.com/title/tt20453286/",
            "matched_original_name": "Truelove",
        },
    )
    print(f"title_links rows updated: {len(updated)}")

    updated = sb_patch(
        "entries",
        {"title": "eq.TrueLove"},
        {
            "imdb_url": "https://www.imdb.com/title/tt20453286/",
            "original_name": "Truelove",
        },
    )
    print(f"entries rows updated: {len(updated)}")


if __name__ == "__main__":
    sys.exit(main())
