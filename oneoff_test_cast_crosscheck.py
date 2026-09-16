#!/usr/bin/env python3
"""One-off: sanity-check the new cast/director cross-check logic against a
real TMDb-backed case before it goes live in resolve_title(). Read-only --
never touches Supabase or title_links, just exercises tmdb_search/rank_
candidates/credits_overlap_score directly so the cache isn't polluted with
test data.
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


def run_case(label, query, entry_year, cast_str, director_str):
    print(f"\n=== {label} ===")
    candidates = gather(query)
    ranked = rank_candidates(candidates, None, entry_year)
    print("Year-only ranking (top 5):")
    for r, k in ranked[:5]:
        name = r.get("name") or r.get("title")
        date_field = "first_air_date" if k == "tv" else "release_date"
        print(f"  [{k}] {name} ({r.get(date_field)}) id={r['id']}")

    cast = scraped_name_list(cast_str)
    director = scraped_name_list(director_str)
    scored = []
    for r, k in ranked[:CREDITS_CHECK_LIMIT]:
        d = tmdb_details(k, r["id"])
        score = credits_overlap_score(d, cast, director)
        scored.append((score, r, k))
    scored.sort(key=lambda t: -t[0])

    print("With cast/director cross-check:")
    for score, r, k in scored:
        name = r.get("name") or r.get("title")
        print(f"  score={score} [{k}] {name} id={r['id']}")

    winner_before = ranked[0] if ranked else (None, None)
    winner_after = (scored[0][1], scored[0][2]) if scored and scored[0][0] > 0 else winner_before
    print(f"Would have picked (year-only): {(winner_before[0] or {}).get('id')}")
    print(f"Now picks (with cross-check):  {(winner_after[0] or {}).get('id')}")


def main():
    # This is the exact real-world case that motivated the fix: "Diuna"
    # (scraped year 2021) previously resolved to the wrong candidate because
    # the search only tried "tv" and the movie search never ran.
    run_case(
        "Diuna / Dune (2021 movie, real cast)",
        "Dune",
        2021,
        "Timothée Chalamet, Rebecca Ferguson, Oscar Isaac, Josh Brolin, Stellan Skarsgård, Zendaya",
        "Denis Villeneuve",
    )


if __name__ == "__main__":
    sys.exit(main())
