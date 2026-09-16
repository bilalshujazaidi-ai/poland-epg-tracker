#!/usr/bin/env python3
"""One-off: fix "Cuda inzynierii" (Polish "Engineering Marvels"), the last
remaining title from the 2026-09-16 audit. Manually researched: its
per-episode synopses (TI Europe supertanker, Beijing Daxing airport, the
"skinniest skyscraper" 111 W 57th St, China's South-North Water Transfer
project) match real episodes of "Impossible Engineering" (2015-, Science
Channel). Polish "Season 5" doesn't match the US season numbering, which is
a common licensing/renumbering quirk for factual series and likely why
year/season-based matching missed it. Was wrongly cached as "Project
Impossible".
"""
import sys

import requests

from scraper import SUPABASE_URL, sb_headers

TITLE = "Cuda inżynierii"
TMDB_ID = 67080
TMDB_TYPE = "tv"
IMDB_ID = "tt4648556"
ORIGINAL_NAME = "Impossible Engineering"


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
