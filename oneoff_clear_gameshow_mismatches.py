#!/usr/bin/env python3
"""One-off: clear two wrong matches found during a 2026-09-17 fresh-scrape
spot-check. Both are Polish game shows ("teleturniej") whose episode-number
suffix wasn't recognized by split_title_and_series() -- "- odc 1074" (no
period after "odc", unlike the "odc." pattern the splitter looks for) and
"- 2075 ed. 15" (a format never seen before) -- so the full garbled title
string got sent to TMDb, which coincidentally matched unrelated foreign
films. Neither Polish game show actually has a meaningful per-episode IMDb
identity, so this clears the bad match rather than substituting another
guess.
"""
import sys

import requests

from scraper import SUPABASE_URL, sb_headers

TITLES = [
    "Va Banque - odc 1074",
    "Koło fortuny - 2075 ed. 15",
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
