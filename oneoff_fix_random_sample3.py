#!/usr/bin/env python3
"""One-off: fix 3 errors found via a third true random sample audit
(2026-09-16), 200 more rows drawn from the resolved title_links cache
(non-overlapping with the first two batches of 30 each). Each verified
against actual cast/director/genre context, not title translation alone:

  - "Klika" (cast: Jay Dee, Cristian Gutierrez, director Michael Greene,
    genre drama/musical) was matched to the unrelated AMC series "Lucky
    Hank" (completely different cast) instead of "Clika" (2026), whose
    Polish transliteration this literally is.
  - "Superman" (full narrative cast: Reeve/Brando/Kidder/Hackman, director
    Richard Donner, genre action) was matched to "Selling Superman" (a
    documentary about a comic collector, unrelated) instead of the actual
    1978 "Superman: The Movie".
  - "Anakonda" (cast: J.Lo/Ice Cube/Voight, director Luis Llosa -- exactly
    the 1997 original film) was matched to tt33244668, confirmed to
    actually be the UNRELATED 2025 meta-reboot (different cast entirely),
    instead of the real 1997 film this cast belongs to.
"""
import sys

import requests

from scraper import SUPABASE_URL, sb_headers

FIXES = [
    {"title": "Klika", "tmdb_id": 1450257, "tmdb_type": "movie", "imdb_id": "tt28334938", "original_name": "Clika"},
    {"title": "Superman", "tmdb_id": 1924, "tmdb_type": "movie", "imdb_id": "tt0078346", "original_name": "Superman"},
    {"title": "Anakonda", "tmdb_id": 9360, "tmdb_type": "movie", "imdb_id": "tt0118615", "original_name": "Anaconda"},
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
