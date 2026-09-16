#!/usr/bin/env python3
"""One-off audit: re-check every resolved title_links row for the pick_best
below-only-year bug fixed in scraper.py (see git history / the
imdb-year-matching-bugfix memory). Read-only -- prints a report, does not
write anything. Bypasses the title_links cache and re-queries TMDb fresh for
every row, since resolve_title() would just return the (possibly wrong)
cached value.

A row is flagged only when BOTH:
  - the OLD (year <= entry_year only) logic reproduces the currently cached
    tmdb_id, i.e. the cached match is explained by the old bug, AND
  - the NEW (closest year in either direction) logic picks something else.

That is the specific signature of the bug, not just "TMDb search results
changed since we last looked" (ranking drift, catalogue updates, etc. would
show up as differences on both branches and are not the bug we're hunting).
"""
import sys

from scraper import (
    sb_get,
    tmdb_search,
    tmdb_external_ids,
    map_country_to_iso,
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


def year_of(r, date_field):
    d = r.get(date_field) or ""
    return int(d[:4]) if d[:4].isdigit() else None


def filter_by_country(results, iso_country):
    if iso_country:
        matching = [r for r in results if iso_country in (r.get("origin_country") or [])]
        if matching:
            return matching
    return results


def pick_old(candidates, date_field, entry_year):
    dated = [(r, year_of(r, date_field)) for r in candidates if year_of(r, date_field) and year_of(r, date_field) <= entry_year]
    if dated:
        dated.sort(key=lambda t: entry_year - t[1])
        return dated[0][0]
    if len(candidates) == 1:
        return candidates[0]
    return None


def pick_new(candidates, date_field, entry_year):
    dated = [(r, year_of(r, date_field)) for r in candidates if year_of(r, date_field) is not None]
    if dated:
        dated.sort(key=lambda t: abs(entry_year - t[1]))
        return dated[0][0]
    if len(candidates) == 1:
        return candidates[0]
    return None


def try_query(title, kind_first="tv"):
    def one_kind(kind, query):
        results = tmdb_search(kind, query)
        if not results and " - " in query:
            results = tmdb_search(kind, query.split(" - ")[0])
        return results

    other_kind = "movie" if kind_first == "tv" else "tv"
    results = one_kind(kind_first, title)
    kind = kind_first
    if not results:
        results = one_kind(other_kind, title)
        kind = other_kind
    return kind, results


def resolve_fresh(title, iso, entry_year):
    kind, results = try_query(title, "tv")
    if not results:
        alt = BARE_TRAILING_SEASON_RE.sub("", title).strip()
        if alt and alt != title:
            kind, results = try_query(alt, "tv")

    if not results:
        return None, None, None

    candidates = filter_by_country(results, iso)
    date_field = "first_air_date" if kind == "tv" else "release_date"
    old_best = pick_old(candidates, date_field, entry_year)
    new_best = pick_new(candidates, date_field, entry_year)
    return kind, old_best, new_best


def main():
    links = sb_get_all(
        "title_links",
        {"imdb_id": "not.is.null", "select": "slug,title,country,tmdb_id,tmdb_type,imdb_id,imdb_url,matched_original_name"},
    )
    print(f"Re-checking {len(links)} resolved title_links rows...\n")

    flagged = []
    checked = 0
    errors = 0

    for row in links:
        checked += 1
        title = row["title"]
        iso = row.get("country")

        entries = sb_get(
            "entries",
            {"title": f"eq.{title}", "select": "year", "limit": 1},
        )
        if not entries or not entries[0].get("year"):
            continue
        entry_year = entries[0]["year"]

        try:
            kind, old_best, new_best = resolve_fresh(title, iso, entry_year)
        except Exception as e:
            print(f"  [{title}] error: {e}")
            errors += 1
            continue

        if not old_best or not new_best:
            continue

        old_id = old_best["id"]
        new_id = new_best["id"]

        if old_id == row["tmdb_id"] and new_id != old_id:
            ext = tmdb_external_ids(kind, new_id)
            new_imdb = ext.get("imdb_id")
            flagged.append({
                "title": title,
                "entry_year": entry_year,
                "cached_imdb_url": row["imdb_url"],
                "cached_original_name": row["matched_original_name"],
                "suspected_correct_original_name": new_best.get("original_name") or new_best.get("original_title"),
                "suspected_correct_imdb": f"https://www.imdb.com/title/{new_imdb}/" if new_imdb else None,
                "suspected_correct_tmdb_id": new_id,
                "kind": kind,
            })

    print(f"Checked {checked} rows, {errors} errors.\n")
    print(f"=== FLAGGED: {len(flagged)} rows likely affected by the year-direction bug ===\n")
    for f in flagged:
        print(f"- \"{f['title']}\" (entry year {f['entry_year']})")
        print(f"    cached:    {f['cached_original_name']} -> {f['cached_imdb_url']}")
        print(f"    suspected: {f['suspected_correct_original_name']} -> {f['suspected_correct_imdb']} (tmdb {f['kind']} id {f['suspected_correct_tmdb_id']})")
    if not flagged:
        print("(none)")


if __name__ == "__main__":
    sys.exit(main())
