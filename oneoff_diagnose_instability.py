#!/usr/bin/env python3
"""One-off diagnostic: the broader audit flagged "Nieznajoma", "Agenci NCIS"
and "Cuda inzynierii" as differing from cache -- but all three were just
manually verified correct minutes ago. Print the full ranked candidate list
and credit scores for each to understand why the same resolution logic
produced a different answer this time. Read-only.
"""
import sys

from scraper import (
    tmdb_search,
    tmdb_details,
    rank_candidates,
    credits_overlap_score,
    scraped_name_list,
    CREDITS_CHECK_LIMIT,
)


def gather(query):
    candidates = [(r, "tv") for r in tmdb_search("tv", query)]
    candidates += [(r, "movie") for r in tmdb_search("movie", query)]
    return candidates


def diagnose(label, query, iso, entry_year, cast_str, director_str):
    print(f"\n=== {label} (query={query!r}, iso={iso!r}, year={entry_year}) ===")
    candidates = gather(query)
    print(f"total raw candidates: {len(candidates)}")
    ranked = rank_candidates(candidates, iso, entry_year)
    print(f"ranked (year-filtered pool size {len(ranked)}), top 10:")
    for i, (r, k) in enumerate(ranked[:10]):
        name = r.get("name") or r.get("title")
        date_field = "first_air_date" if k == "tv" else "release_date"
        print(f"  #{i} [{k}] {name} ({r.get(date_field)}) id={r['id']}")

    cast = scraped_name_list(cast_str)
    director = scraped_name_list(director_str)
    print(f"scraped cast (normalized): {cast}")
    print(f"scraped director (normalized): {director}")

    print(f"credit scores for top {CREDITS_CHECK_LIMIT}:")
    for r, k in ranked[:CREDITS_CHECK_LIMIT]:
        d = tmdb_details(k, r["id"])
        score = credits_overlap_score(d, cast, director)
        name = r.get("name") or r.get("title")
        tmdb_cast_sample = [p.get("name") for p in (d.get("credits") or {}).get("cast", [])[:8]]
        print(f"  [{k}] {name} id={r['id']} score={score} sample_tmdb_cast={tmdb_cast_sample}")


def main():
    diagnose("Nieznajoma", "Nieznajoma", "GB", 2020,
              "Richard Armitage, Shaun Dooley, Hannah John - Kamen, Dervla Kirwan, Siobhan Finneran, Jacob Dudman",
              "Daniel O'Hara, Hannah Quinn")

    diagnose("Agenci NCIS", "Agenci NCIS", "US", 2018,
              "David McCallum, Mark Harmon, Pauley Perrette", None)

    diagnose("Cuda inzynierii", "Cuda inżynierii", "GB", 2021, None, "Gavin Maxwell")


if __name__ == "__main__":
    sys.exit(main())
