#!/usr/bin/env python3
"""One-off: apply the batch of corrections found by the broader full-logic
audit (2026-09-16), each manually verified against the entry's actual
scraped cast/director/context before being included here -- the audit's
raw suggestions included several false positives (structural cast-matching
limits, not real errors) that are deliberately excluded from this list; see
the imdb-year-matching-bugfix memory for the full accounting.

Note: "Dotyk" corrects an earlier mistake from this same investigation --
it was previously (wrongly) set to "Dotyk zivota" without checking the
entry's actual director (Baltasar Kormakur), which identifies it as
"Touch"/"Snerting" (2024) instead.
"""
import sys

import requests

from scraper import SUPABASE_URL, sb_headers

FIXES = [
    {"title": "Więzień", "tmdb_id": 1307373, "tmdb_type": "movie", "imdb_id": "tt29028515", "original_name": "Wasteman"},
    {"title": "Czarny diament", "tmdb_id": 384212, "tmdb_type": "movie", "imdb_id": "tt3759370", "original_name": "Diamant noir"},
    {"title": "Piekarz", "tmdb_id": 823395, "tmdb_type": "movie", "imdb_id": "tt3917710", "original_name": "The Baker"},
    {"title": "Duchy", "tmdb_id": 17174, "tmdb_type": "tv", "imdb_id": "tt8594324", "original_name": "Ghosts"},
    {"title": "Władimir Putin - Wróg numer jeden?", "tmdb_id": 507469, "tmdb_type": "movie", "imdb_id": "tt8238872", "original_name": "America's Greatest Threat: Vladimir Putin"},
    {"title": "Skarbek", "tmdb_id": 1159939, "tmdb_type": "movie", "imdb_id": "tt27664301", "original_name": "The Partisan"},
    {"title": "Alita: Battle Angel", "tmdb_id": 399579, "tmdb_type": "movie", "imdb_id": "tt0437086", "original_name": "Alita: Battle Angel"},
    {"title": "W otchłani", "tmdb_id": 454615, "tmdb_type": "movie", "imdb_id": "tt5622412", "original_name": "Black Water"},
    {"title": "Prawda o kłamstwach", "tmdb_id": 321558, "tmdb_type": "movie", "imdb_id": "tt2377752", "original_name": "The Truth About Lies"},
    {"title": "Wojownicze zolwie ninja", "tmdb_id": 614930, "tmdb_type": "movie", "imdb_id": "tt8589698", "original_name": "Teenage Mutant Ninja Turtles: Mutant Mayhem"},
    {"title": "Until Dawn", "tmdb_id": 1232546, "tmdb_type": "movie", "imdb_id": "tt30955489", "original_name": "Until Dawn"},
    {"title": "Kanciarz", "tmdb_id": 454648, "tmdb_type": "movie", "imdb_id": "tt6675400", "original_name": "Con Man"},
    {"title": "Bez urazy", "tmdb_id": 884605, "tmdb_type": "movie", "imdb_id": "tt15671028", "original_name": "No Hard Feelings"},
    {"title": "Wyspa Fantazji", "tmdb_id": 539537, "tmdb_type": "movie", "imdb_id": "tt0983946", "original_name": "Fantasy Island"},
    {"title": "Escape Room", "tmdb_id": 522681, "tmdb_type": "movie", "imdb_id": "tt5886046", "original_name": "Escape Room"},
    {"title": "Małe kobietki", "tmdb_id": 331482, "tmdb_type": "movie", "imdb_id": "tt3281548", "original_name": "Little Women"},
    {"title": "Kaskader", "tmdb_id": 746036, "tmdb_type": "movie", "imdb_id": "tt1684562", "original_name": "The Fall Guy"},
    {"title": "Uncharted", "tmdb_id": 335787, "tmdb_type": "movie", "imdb_id": "tt1464335", "original_name": "Uncharted"},
    {"title": "Mission: Impossible - Dead Reckoning", "tmdb_id": 575264, "tmdb_type": "movie", "imdb_id": "tt9603212", "original_name": "Mission: Impossible - Dead Reckoning Part One"},
    {"title": "Narodziny gwiazdy", "tmdb_id": 19610, "tmdb_type": "movie", "imdb_id": "tt0075265", "original_name": "A Star Is Born"},
    {"title": "Polowanie", "tmdb_id": 1168598, "tmdb_type": "movie", "imdb_id": "tt27876667", "original_name": "Polowanie"},
    {"title": "Teraz albo nigdy", "tmdb_id": 503616, "tmdb_type": "movie", "imdb_id": "tt2126357", "original_name": "Second Act"},
    {"title": "Zabójcze umysły", "tmdb_id": 4057, "tmdb_type": "tv", "imdb_id": "tt0452046", "original_name": "Criminal Minds"},
    {"title": "Rekrut", "tmdb_id": 79744, "tmdb_type": "tv", "imdb_id": "tt7587890", "original_name": "The Rookie"},
    {"title": "Cobra Kai", "tmdb_id": 77169, "tmdb_type": "tv", "imdb_id": "tt7221388", "original_name": "Cobra Kai"},
    {"title": "Top Gear", "tmdb_id": 45, "tmdb_type": "tv", "imdb_id": "tt1628033", "original_name": "Top Gear"},
    {"title": "The Killer", "tmdb_id": 970347, "tmdb_type": "movie", "imdb_id": "tt1121948", "original_name": "The Killer"},
    {"title": "Panna młoda!", "tmdb_id": 1159831, "tmdb_type": "movie", "imdb_id": "tt30851137", "original_name": "The Bride!"},
    {"title": "FBI - Prosto w ogień", "tmdb_id": 80748, "tmdb_type": "tv", "imdb_id": "tt7491982", "original_name": "FBI"},
    {"title": "FBI - Brzemię ojca", "tmdb_id": 80748, "tmdb_type": "tv", "imdb_id": "tt7491982", "original_name": "FBI"},
    {"title": "FBI - Drugie życie", "tmdb_id": 80748, "tmdb_type": "tv", "imdb_id": "tt7491982", "original_name": "FBI"},
    {"title": "Dotyk", "tmdb_id": 1032472, "tmdb_type": "movie", "imdb_id": "tt23468836", "original_name": "Snerting"},
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
