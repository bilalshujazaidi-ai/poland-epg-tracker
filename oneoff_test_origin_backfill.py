#!/usr/bin/env python3
"""One-off: sanity-check the new origin-country backfill in resolve_title()
against real TMDb data before it goes live. Read-only against Supabase
(only writes to title_links as resolve_title() normally would, using a
throwaway slug-safe test title that won't collide with real scraped data).
"""
import sys

from scraper import resolve_title


def main():
    # A well-known US movie with no cast/director/country scraped, to force
    # a fresh resolution and exercise the movie (production_countries) path.
    print("=== Movie case: 'Oppenheimer', no scraped country ===")
    imdb_url, original_name, origin_name = resolve_title("Oppenheimer", None, 2023)
    print(f"imdb_url={imdb_url}, original_name={original_name!r}, origin_name={origin_name!r}")

    # A well-known UK show, no scraped country, to exercise the tv
    # (origin_country) path.
    print("\n=== TV case: 'Peaky Blinders', no scraped country ===")
    imdb_url, original_name, origin_name = resolve_title("Peaky Blinders", None, 2013)
    print(f"imdb_url={imdb_url}, original_name={original_name!r}, origin_name={origin_name!r}")

    # Re-resolve the same movie title again -- should hit the cache branch
    # and still produce origin_name from what got stored the first time.
    print("\n=== Cache-hit re-check: 'Oppenheimer' again, no scraped country ===")
    imdb_url, original_name, origin_name = resolve_title("Oppenheimer", None, 2023)
    print(f"imdb_url={imdb_url}, original_name={original_name!r}, origin_name={origin_name!r}")

    # Same cached title, but THIS run's scrape did have a country -- origin_name
    # must come back None since the real scraped value should win, not the cache.
    print("\n=== Cache-hit, but scraped country IS present this time ===")
    imdb_url, original_name, origin_name = resolve_title("Oppenheimer", "USA", 2023)
    print(f"imdb_url={imdb_url}, original_name={original_name!r}, origin_name={origin_name!r} (expect None)")


if __name__ == "__main__":
    sys.exit(main())
