#!/usr/bin/env python3
"""One-off maintenance job: clean up messy titles in already-scraped `entries`
rows (embedded "odc. N" episode markers, "Premiera " badges, etc. that leaked
into the title field before scraper.py's parser was fixed), and re-attempt
IMDb resolution for those rows using the cleaned title.

Safe to re-run: rows that no longer have "odc" in the title are left alone,
and resolve_title() already caches by the cleaned title's slug, so repeat
runs cost nothing extra once a title has been resolved once.
"""
import json
import sys

import requests

from scraper import (
    SUPABASE_URL,
    sb_headers,
    sb_get,
    split_title_and_series,
    resolve_title,
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


def sb_patch(table, row_id, data):
    r = requests.patch(
        f"{SUPABASE_URL}/rest/v1/{table}?id=eq.{row_id}",
        headers=sb_headers(prefer="return=minimal"),
        data=json.dumps(data),
        timeout=30,
    )
    if not r.ok:
        print(f"  patch failed for id={row_id}: {r.status_code} {r.text}")
    return r.ok


def main():
    # Re-run against every currently-unresolved entry rather than trying to
    # build one precise filter for every messy-title shape (embedded "odc.",
    # a leading "Premiera " badge on movies with no episode marker at all, the
    # dot-abbreviated "s.XX" season form, etc.) -- split_title_and_series() is
    # a safe no-op for a title that doesn't match any of those patterns, so
    # this is just a thorough sweep, not a riskier one.
    rows = sb_get_all(
        "entries",
        {"imdb_url": "is.null", "select": "id,title,country,year,series_info,imdb_url"},
    )
    print(f"Found {len(rows)} unresolved entries to re-check")

    patched = 0
    newly_resolved = 0
    unchanged = 0

    for row in rows:
        clean_title, series_info = split_title_and_series(row["title"])
        title_changed = clean_title != row["title"]
        series_changed = series_info != row.get("series_info")

        if not title_changed and not series_changed:
            unchanged += 1
            continue

        imdb_url, original_name = resolve_title(clean_title, row.get("country"), row.get("year"))

        patch = {"title": clean_title, "series_info": series_info}
        if imdb_url:
            patch["imdb_url"] = imdb_url
            patch["original_name"] = original_name

        if sb_patch("entries", row["id"], patch):
            patched += 1
            if imdb_url and not row.get("imdb_url"):
                newly_resolved += 1

    print(
        f"\nDone. {patched} entries updated, {unchanged} needed no change, "
        f"{newly_resolved} newly gained an IMDb link."
    )


if __name__ == "__main__":
    sys.exit(main())
