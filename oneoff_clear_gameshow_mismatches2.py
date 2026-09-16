#!/usr/bin/env python3
"""One-off: clear two more instances of the same game-show mismatch pattern
(different episode numbers than the ones already cleared) found via a
targeted query for genre=teleturniej rows that still have an imdb_url set.
"Postaw na milion" was also in that query result but is a genuinely correct
match (exact title, real IMDb series page) and is deliberately left alone.
"""
import sys

import requests

from scraper import SUPABASE_URL, sb_headers

TITLES = [
    "Va Banque - odc 1073",
    "Koło fortuny - 2074 ed. 15",
]


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
    for title in TITLES:
        updated = sb_patch(
            "title_links",
            {"title": f"eq.{title}"},
            {"tmdb_id": None, "tmdb_type": None, "imdb_id": None, "imdb_url": None, "matched_original_name": None},
        )
        print(f'"{title}": title_links rows cleared: {len(updated)}')

        updated = sb_patch(
            "entries",
            {"title": f"eq.{title}"},
            {"imdb_url": None, "original_name": None},
        )
        print(f'"{title}": entries rows cleared: {len(updated)}')


if __name__ == "__main__":
    sys.exit(main())
