#!/usr/bin/env python3
"""One-off: fix 4 errors found while checking ALL remaining unaudited
resolved title_links rows (2026-09-16), completing full human coverage of
the ~529-row resolved cache. Each verified against actual cast/director/
genre context and confirmed via independent research (not blind trust):

  - "Klan" (Polish cast/directors, genre "telenowela TVP") was matched to
    a Chinese title "九门" instead of the real, famous Polish soap opera
    "Klan" (1997-).
  - "Barbie" (cast Robbie/Gosling/Ferrell, director Greta Gerwig) was
    matched to "Barbie: A Touch of Magic" (an unrelated animated special)
    instead of the actual 2023 live-action film.
  - "Lista" (cast Sienna Guillory/Clive Russell, director Klaus Huttmann)
    was matched to "The Terminal List" (wrong cast entirely) instead of
    "The List" (2013), the real film this cast belongs to.
  - "Milosc x 3" (cast Rosanna Arquette/Kathy Baker, director Eleanor
    Coppola) was matched to the Netflix anthology "Love, Death & Robots"
    instead of "Love Is Love Is Love" (2020), Coppola's actual 3-story
    anthology film -- explaining the "x3" in the Polish title.

Three other suspicious-looking titles ("Niebezpieczne zwiazki", "Pogoda 1",
"OTV - PASMO LOKALNE") were confirmed as coincidental generic-title
mismatches with no meaningful correct answer to substitute (they're
placeholder/local-programming-block listings, not real content with an
IMDb identity) -- not included here, left as-is since no better answer
exists. A 5th suspect ("Krytyczna godzina" / Line of Duty) turned out to
already be correct on closer check -- tt3541524 is genuinely the 2019
American film with this exact cast, not the British TV series it was
first assumed to be.
"""
import sys

import requests

from scraper import SUPABASE_URL, sb_headers

FIXES = [
    {"title": "Klan", "tmdb_id": 6489, "tmdb_type": "tv", "imdb_id": "tt0182607", "original_name": "Klan"},
    {"title": "Barbie", "tmdb_id": 346698, "tmdb_type": "movie", "imdb_id": "tt1517268", "original_name": "Barbie"},
    {"title": "Lista", "tmdb_id": 205749, "tmdb_type": "movie", "imdb_id": "tt2150511", "original_name": "The List"},
    {"title": "Miłość x 3", "tmdb_id": 680590, "tmdb_type": "movie", "imdb_id": "tt7686376", "original_name": "Love Is Love Is Love"},
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
