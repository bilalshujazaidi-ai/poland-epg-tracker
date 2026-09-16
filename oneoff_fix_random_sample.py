#!/usr/bin/env python3
"""One-off: fix 3 wrong matches found via a true random sample audit of 30
resolved title_links rows (2026-09-16), drawn independently of any
diff-based algorithmic flagging. These were verified against actual cast
(Nope) or genre/franchise-season context (I.S.S., Apollo Has Fallen), not
just title translation:

  - "Nie!" (Polish release title for "Nope") was wrongly cached as an
    unrelated Polish TV series "To nie ze mną" -- confirmed via cast
    (Daniel Kaluuya, Keke Palmer, Steven Yeun).
  - "I.S.S." was wrongly cached as "The 2010s" (a CNN documentary
    mini-series) -- confirmed via genre (sci-fi) and country/year context.
  - "Apollo w ogniu" was wrongly cached as "Paris Has Fallen" (the FIRST
    season of the same franchise) instead of "Apollo Has Fallen" (the
    correct 2026 second season) -- confirmed via cast/creator/plot details.

A 4th sampled title ("MacGyver") was independently re-verified and found
to already be correctly cached -- not included here.
"""
import sys

import requests

from scraper import SUPABASE_URL, sb_headers

FIXES = [
    {"title": "Nie!", "tmdb_id": 762504, "tmdb_type": "movie", "imdb_id": "tt10954984", "original_name": "Nope"},
    {"title": "I.S.S.", "tmdb_id": 790462, "tmdb_type": "movie", "imdb_id": "tt13655120", "original_name": "I.S.S."},
    {"title": "Apollo w ogniu", "tmdb_id": 287453, "tmdb_type": "tv", "imdb_id": "tt36350690", "original_name": "Apollo Has Fallen"},
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
    for fix in FIXES:
        title = fix["title"]
        imdb_url = f"https://www.imdb.com/title/{fix['imdb_id']}/"

        updated = sb_patch(
            "title_links",
            {"title": f"eq.{title}"},
            {
                "tmdb_id": fix["tmdb_id"],
                "tmdb_type": fix["tmdb_type"],
                "imdb_id": fix["imdb_id"],
                "imdb_url": imdb_url,
                "matched_original_name": fix["original_name"],
            },
        )
        print(f'"{title}": title_links rows updated: {len(updated)}')

        updated = sb_patch(
            "entries",
            {"title": f"eq.{title}"},
            {"imdb_url": imdb_url, "original_name": fix["original_name"]},
        )
        print(f'"{title}": entries rows updated: {len(updated)}')


if __name__ == "__main__":
    sys.exit(main())
