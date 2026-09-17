#!/usr/bin/env python3
"""One-off: backfill origin country for already-resolved titles whose
source scrape never stated one, using the same TMDb data (origin_country
for TV, production_countries for movies) that the permanent fix in
resolve_title() now applies to all future resolutions. This catches the
titles that were resolved before that fix existed.

Only ever fills a blank -- never overwrites a country the source page did
state.
"""
import sys

import requests

from scraper import SUPABASE_URL, sb_headers, sb_get, tmdb_details, tmdb_origin_iso, ISO_TO_COUNTRY_NAME


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
    rows = sb_get_all(
        "title_links",
        {"country": "is.null", "imdb_id": "not.is.null", "select": "slug,title,tmdb_id,tmdb_type"},
    )
    print(f"{len(rows)} title_links rows to backfill\n")

    updated_links = 0
    updated_entries = 0
    no_origin = 0

    for row in rows:
        try:
            details = tmdb_details(row["tmdb_type"], row["tmdb_id"])
            iso = tmdb_origin_iso(row["tmdb_type"], {}, details)
        except Exception as e:
            print(f'  [{row["title"]}] error: {e}')
            continue

        if not iso:
            no_origin += 1
            continue

        name = ISO_TO_COUNTRY_NAME.get(iso, iso)

        sb_patch("title_links", {"slug": f"eq.{row['slug']}"}, {"country": iso})
        updated_links += 1

        ent = sb_patch("entries", {"title": f"eq.{row['title']}", "country": "is.null"}, {"country": name})
        updated_entries += len(ent)

    print(
        f"\nDone. {updated_links} title_links rows backfilled, "
        f"{updated_entries} entries rows backfilled, {no_origin} had no TMDb origin data at all."
    )


if __name__ == "__main__":
    sys.exit(main())
