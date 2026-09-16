#!/usr/bin/env python3
"""One-off: re-resolve "Diuna" and "The Lost City", the two rows the
2026-09-16 audit flagged as movie-vs-TV mismatches that neither the
year-direction fix nor cast/director cross-check had corrected yet (their
title_links cache still held the old wrong match, and resolve_title() only
ever consults the cache -- it never re-queries TMDb for an already-cached
title). Deletes the stale cache rows first so resolve_title() is forced to
redo the resolution with the current logic, then patches the entries rows
to match.
"""
import sys

import requests

from scraper import SUPABASE_URL, sb_headers, sb_get, resolve_title

TITLES = ["Diuna", "The Lost City"]


def sb_delete(table, params):
    r = requests.delete(
        f"{SUPABASE_URL}/rest/v1/{table}",
        headers=sb_headers(prefer="return=representation"),
        params=params,
        timeout=30,
    )
    if not r.ok:
        print(f"  delete failed for {table} {params}: {r.status_code} {r.text}")
        r.raise_for_status()
    return r.json()


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
    for title in TITLES:
        print(f"\n=== {title} ===")
        entries = sb_get("entries", {"title": f"eq.{title}", "select": "country,year,cast_list,director", "limit": 1})
        if not entries:
            print("  no entries row found, skipping")
            continue
        row = entries[0]

        deleted = sb_delete("title_links", {"title": f"eq.{title}"})
        print(f"  cleared {len(deleted)} stale title_links row(s)")

        imdb_url, original_name = resolve_title(title, row.get("country"), row.get("year"), row.get("cast_list"), row.get("director"))
        print(f"  re-resolved -> {original_name} -> {imdb_url}")

        if imdb_url:
            updated = sb_patch("entries", {"title": f"eq.{title}"}, {"imdb_url": imdb_url, "original_name": original_name})
            print(f"  patched {len(updated)} entries row(s)")
        else:
            print("  no IMDb link found -- leaving entries rows untouched")


if __name__ == "__main__":
    sys.exit(main())
