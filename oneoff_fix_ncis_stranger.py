#!/usr/bin/env python3
"""One-off: fix "Agenci NCIS" and "Nieznajoma", the two rows the 2026-09-16
audit couldn't call confidently at the time. Manually researched afterward
using each entry's scraped cast/director, which confirmed:

  - "Agenci NCIS" (cast: David McCallum, Mark Harmon, Pauley Perrette) is
    the flagship "NCIS" (2003-), not "NCIS: New Orleans" (wrongly cached).
  - "Nieznajoma" (cast: Richard Armitage, Siobhan Finneran, Jacob Dudman,
    Hannah John-Kamen; directors Daniel O'Hara, Hannah Quinn; synopsis about
    a lawyer named Adam Price and his wife Corinne) is "The Stranger" (2020
    Netflix miniseries based on the Harlan Coben novel), not "Mon Inconnue"
    (wrongly cached).
"""
import sys

import requests

from scraper import SUPABASE_URL, sb_headers

FIXES = [
    {
        "title": "Agenci NCIS",
        "tmdb_id": 4614,
        "tmdb_type": "tv",
        "imdb_id": "tt0364845",
        "original_name": "NCIS",
    },
    {
        "title": "Nieznajoma",
        "tmdb_id": 96608,
        "tmdb_type": "tv",
        "imdb_id": "tt9698480",
        "original_name": "The Stranger",
    },
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
