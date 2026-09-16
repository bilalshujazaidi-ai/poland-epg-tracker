#!/usr/bin/env python3
"""One-off broader audit: re-check every resolved title_links row using the
FULL current resolution pipeline (year-direction matching + combined tv/movie
search + cast/director cross-check), not just the narrower year-direction
bug signature the first audit looked for. Read-only -- prints a report, does
not write anything.

Why broader: the "FBI" mismatch found during the 2026-09-16 fresh-scrape
spot-check was NOT a year-direction bug -- both the old and new year logic
agreed on "FBI: International" over the real "FBI" (2018), because for a
long-running flagship show with a newer spinoff, the flagship's ORIGINAL
air year is naturally further from a given season's scraped year than the
newer spinoff's air year is. Only a cast/director check catches that class
of error. This audit re-derives the match fresh (bypassing the cache, since
resolve_title() would just return whatever's already cached) and flags any
row where the result differs from what's cached, for any reason -- not just
the narrow year-signature the first audit targeted.
"""
import sys

from scraper import (
    sb_get,
    tmdb_search,
    tmdb_details,
    rank_candidates,
    credits_overlap_score,
    scraped_name_list,
    CREDITS_CHECK_LIMIT,
    BARE_TRAILING_SEASON_RE,
)


def sb_get_all(table, params, page_size=1000):
    out = []
    offset = 0
    while True:
        page_params = dict(params)
        page_params["limit"] = page_size
        page_params["offset"] = offset
        rows = sb_get(table, page_params)
        out.extend(rows)
        if len(rows) < page_size:
            break
        offset += page_size
    return out


def gather(query):
    candidates = [(r, "tv") for r in tmdb_search("tv", query)]
    candidates += [(r, "movie") for r in tmdb_search("movie", query)]
    if not candidates and " - " in query:
        base = query.split(" - ")[0]
        candidates = [(r, "tv") for r in tmdb_search("tv", base)]
        candidates += [(r, "movie") for r in tmdb_search("movie", base)]
    return candidates


def resolve_fresh(title, iso, entry_year, cast, director):
    candidates = gather(title)
    if not candidates:
        alt = BARE_TRAILING_SEASON_RE.sub("", title).strip()
        if alt and alt != title:
            candidates = gather(alt)
    if not candidates:
        return None, None

    ranked = rank_candidates(candidates, iso, entry_year)
    if not ranked:
        return None, None

    best, kind = ranked[0]
    scraped_cast = scraped_name_list(cast)
    scraped_director = scraped_name_list(director)
    if len(ranked) > 1 and (scraped_cast or scraped_director):
        scored = [
            (credits_overlap_score(tmdb_details(k, r["id"]), scraped_cast, scraped_director), r, k)
            for r, k in ranked[:CREDITS_CHECK_LIMIT]
        ]
        scored.sort(key=lambda t: -t[0])
        if scored[0][0] > 0:
            _, best, kind = scored[0]
    return best, kind


def pick_entry_context(entries):
    """Prefer an entries row that has both a year and cast/director, so we
    never mix year from one row with cast from a different (possibly
    different-season) row. Falls back to the first with just a year."""
    fallback = None
    for e in entries:
        if not e.get("year"):
            continue
        if fallback is None:
            fallback = e
        if e.get("cast_list") or e.get("director"):
            return e
    return fallback


def main():
    links = sb_get_all(
        "title_links",
        {"imdb_id": "not.is.null", "select": "slug,title,country,tmdb_id,tmdb_type,imdb_id,imdb_url,matched_original_name"},
    )
    print(f"Re-checking {len(links)} resolved title_links rows with full current logic...\n")

    flagged = []
    checked = 0
    errors = 0

    for row in links:
        checked += 1
        title = row["title"]
        iso = row.get("country")

        entries = sb_get(
            "entries",
            {"title": f"eq.{title}", "select": "year,cast_list,director", "limit": 10},
        )
        ctx = pick_entry_context(entries) if entries else None
        if not ctx:
            continue
        entry_year = ctx["year"]
        cast = ctx.get("cast_list")
        director = ctx.get("director")

        try:
            best, kind = resolve_fresh(title, iso, entry_year, cast, director)
        except Exception as e:
            print(f"  [{title}] error: {e}")
            errors += 1
            continue

        if not best:
            continue

        if best["id"] != row["tmdb_id"] or kind != row["tmdb_type"]:
            ext = (tmdb_details(kind, best["id"]) or {}).get("external_ids") or {}
            new_imdb = ext.get("imdb_id")
            flagged.append({
                "title": title,
                "entry_year": entry_year,
                "had_cast_or_director": bool(cast or director),
                "cached_original_name": row["matched_original_name"],
                "cached_imdb_url": row["imdb_url"],
                "suspected_original_name": best.get("original_name") or best.get("original_title"),
                "suspected_imdb": f"https://www.imdb.com/title/{new_imdb}/" if new_imdb else None,
                "suspected_tmdb_id": best["id"],
                "kind": kind,
            })

        if checked % 50 == 0:
            print(f"  ...checked {checked}/{len(links)}")

    print(f"\nChecked {checked} rows, {errors} errors.\n")
    print(f"=== FLAGGED: {len(flagged)} rows differ from cache under full current logic ===\n")
    for f in flagged:
        print(f"- \"{f['title']}\" (entry year {f['entry_year']}, had cast/director: {f['had_cast_or_director']})")
        print(f"    cached:    {f['cached_original_name']} -> {f['cached_imdb_url']}")
        print(f"    suspected: {f['suspected_original_name']} -> {f['suspected_imdb']} (tmdb {f['kind']} id {f['suspected_tmdb_id']})")
    if not flagged:
        print("(none)")


if __name__ == "__main__":
    sys.exit(main())
