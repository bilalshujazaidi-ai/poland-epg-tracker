#!/usr/bin/env python3
"""One-off: clear 3 confirmed-wrong matches found during the full-coverage
audit that have no correct replacement to substitute -- each is a generic
Polish local-programming placeholder (a weather segment, a regional
station's local block, a news/politics magazine show) that coincidentally
title-matched an unrelated IMDb entry with no real content to link to.
"""
import sys

import requests

from scraper import SUPABASE_URL, sb_headers

TITLES = [
    "Pogoda 1",
    "OTV - PASMO LOKALNE",
    "Niebezpieczne związki",
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
