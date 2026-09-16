#!/usr/bin/env python3
"""One-off: apply the 6 verified corrections found by the year-direction bug
audit (see the imdb-year-matching-bugfix memory). Each entry below was
manually checked against the Polish title's meaning before being included --
this is not a blind re-application of the audit's raw suggestions, several
of which were false positives.
"""
import sys

import requests

from scraper import SUPABASE_URL, sb_headers

FIXES = [
    {
        "title": "Linoleum",
        "tmdb_id": 765904,
        "tmdb_type": "movie",
        "imdb_id": "tt13483866",
        "original_name": "Linoleum",
    },
    {
        "title": "Królowa ringu",
        "tmdb_id": 1144932,
        "tmdb_type": "movie",
        "imdb_id": "tt28070202",
        "original_name": "Queen of the Ring",
    },
    {
        "title": "Witaj, smutku",
        "tmdb_id": 1127648,
        "tmdb_type": "movie",
        "imdb_id": "tt27774999",
        "original_name": "Bonjour Tristesse",
    },
    {
        "title": "Dotyk",
        "tmdb_id": 280902,
        "tmdb_type": "tv",
        "imdb_id": "tt35232816",
        "original_name": "Dotyk života",
    },
    {
        "title": "Duch Świąt",
        "tmdb_id": 910816,
        "tmdb_type": "movie",
        "imdb_id": "tt14460090",
        "original_name": "A Show-Stopping Christmas",
    },
    {
        "title": "Ścieżki życia",
        "tmdb_id": 1127625,
        "tmdb_type": "movie",
        "imdb_id": "tt27766440",
        "original_name": "The Salt Path",
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
