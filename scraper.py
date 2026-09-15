#!/usr/bin/env python3
"""Daily scraper for the Poland EPG tracker.

Fetches yesterday's finalized broadcast-day schedule for a fixed list of
Polish TV channels from programtv.naziemna.info, keeps only entries whose
origin is USA/UK/Canada/Australia (or unlisted) and whose year is 2018+,
resolves each title's IMDb link via TMDb (cached), and writes everything to
a Supabase Postgres database.
"""
import os
import re
import sys
import json
import unicodedata
import urllib.parse
from datetime import date, timedelta

import requests

SUPABASE_URL = os.environ["SUPABASE_URL"].rstrip("/")
SUPABASE_SERVICE_KEY = os.environ["SUPABASE_SERVICE_KEY"]
TMDB_API_KEY = os.environ["TMDB_API_KEY"]

BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
}

CHANNELS = [
    "bbcfirst", "13ulica", "alekinoplus", "amc", "antenatv", "axn", "axnblack",
    "axnspin", "axnwhite", "bbcbrit", "canalplus1", "canalplus360",
    "canalplus4kultrahd", "canalplusfilm", "canalplus", "canalplusseriale",
    "cinemax", "cinemax2", "comedycentral", "eentertainment", "epicdrama",
    "filmax", "filmboxplusaction", "filmboxpluscomedy", "filmboxplusemotion",
    "filmboxplushits", "filmboxplusone", "fox", "foxcomedy", "hbo", "hbo2",
    "hbo3", "paramountchannel", "planeteplus", "polsat", "polsat1", "polsat2",
    "polsatcomedycentralextra", "polsatfilm", "polsatfilm2", "polsatseriale",
    "puls2", "scifi", "sundancechannel", "superpolsat", "tvpuls", "tv6",
    "tv4", "tvn7", "tvn", "tvn24", "tvphd", "tvp4k", "tvpseriale", "tvp1",
    "tvp2", "tvp3", "viaplay", "vh1", "warnertv", "zoomtv",
]

POLISH_MONTH_GENITIVE = {
    1: "stycznia", 2: "lutego", 3: "marca", 4: "kwietnia", 5: "maja",
    6: "czerwca", 7: "lipca", 8: "sierpnia", 9: "września", 10: "października",
    11: "listopada", 12: "grudnia",
}

COUNTRY_TO_ISO = {
    "uk": "GB", "united kingdom": "GB", "wielka brytania": "GB",
    "usa": "US", "united states": "US", "united states of america": "US",
    "canada": "CA", "kanada": "CA",
    "australia": "AU",
    "polska": "PL", "poland": "PL",
    "niemcy": "DE", "germany": "DE",
    "francja": "FR", "france": "FR",
    "wlochy": "IT", "italy": "IT",
    "hiszpania": "ES", "spain": "ES",
    "irlandia": "IE", "ireland": "IE",
    "szwecja": "SE", "sweden": "SE",
    "norwegia": "NO", "norway": "NO",
    "dania": "DK", "denmark": "DK",
    "belgia": "BE", "belgium": "BE",
    "holandia": "NL", "netherlands": "NL",
    "austria": "AT",
    "szwajcaria": "CH", "switzerland": "CH",
    "rosja": "RU", "russia": "RU",
    "czechy": "CZ", "czech republic": "CZ",
    "nowa zelandia": "NZ", "new zealand": "NZ",
    "indie": "IN", "india": "IN",
    "japonia": "JP", "japan": "JP",
    "korea poludniowa": "KR", "south korea": "KR",
    "chiny": "CN", "china": "CN",
    "bulgaria": "BG",
    "iceland": "IS",
}

QUALIFYING_COUNTRY_RE = re.compile(
    r"\busa\b|united states|\bus\b|\buk\b|united kingdom|wielka brytania|"
    r"canada|kanada|australia",
    re.IGNORECASE,
)

SERIES_INFO_SUFFIX_RE = re.compile(
    r"^(.*?)\s-\s((?:Seria|Sezon|sezon)\s+\d+,?\s*odc\.\s*\d+|[Oo]dc\.\s*\d+)$"
)

TIME_LINE_RE = re.compile(r"(?m)^(\d{2}:\d{2})\s+(.+)$")
PAREN_RE = re.compile(r"\(([^)]*)\)")
YEAR_RE = re.compile(r"(19|20)\d{2}")
DURATION_RE = re.compile(r"Czas:\s*(\d+)\s*min", re.IGNORECASE)
CAST_RE = re.compile(r"Obsada:\s*(.+)")
DIRECTOR_RE = re.compile(r"Reżyseria:\s*(.+)")
TRAILING_FRACTION_RE = re.compile(r"(\d+/\d+)\.?\s*$")


def strip_html(html: str) -> str:
    html = re.sub(r"<script.*?</script>", "", html, flags=re.S | re.I)
    html = re.sub(r"<style.*?</style>", "", html, flags=re.S | re.I)
    text = re.sub(r"<[^>]+>", "\n", html)
    text = text.replace("&nbsp;", " ").replace("&amp;", "&")
    text = text.replace("&quot;", '"').replace("&#39;", "'")
    lines = [l.strip() for l in text.split("\n")]
    lines = [l for l in lines if l]
    return "\n".join(lines)


def slugify(title: str) -> str:
    normalized = unicodedata.normalize("NFKD", title)
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii")
    lowered = ascii_text.lower()
    slug = re.sub(r"[^a-z0-9]+", "-", lowered).strip("-")
    return slug[:190]


def fetch_channel_page(slug: str, target_date: date):
    day = target_date.day
    month_name = POLISH_MONTH_GENITIVE[target_date.month]
    url = f"https://programtv.naziemna.info/program/stacja/{slug},{day}-{month_name}"
    try:
        resp = requests.get(url, headers=BROWSER_HEADERS, timeout=30)
        resp.raise_for_status()
    except requests.RequestException as e:
        print(f"  [{slug}] fetch error: {e}")
        return None, None

    title_match = re.search(r"<title>([^<]*)</title>", resp.text, re.I)
    page_title = title_match.group(1) if title_match else ""
    if "program TV" not in page_title:
        print(f"  [{slug}] no schedule for {target_date} (page: {page_title!r})")
        return None, None

    display_name = page_title.split(" program TV")[0].strip()
    text = strip_html(resp.text)
    return display_name, text


def parse_entries(text: str):
    matches = list(TIME_LINE_RE.finditer(text))
    entries = []
    for i, m in enumerate(matches):
        time_str = m.group(1)
        start = m.start(2)
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        chunk = text[start:end]

        # Cut off the boilerplate footer for this entry, if present.
        chunk = re.split(r"Godziny emisji .* w TV", chunk)[0]
        chunk_lines = [l for l in chunk.split("\n") if l.strip()]
        if not chunk_lines:
            continue

        title_line = chunk_lines[0].strip()
        title = title_line
        series_info = None
        sm = SERIES_INFO_SUFFIX_RE.match(title_line)
        if sm:
            title, series_info = sm.group(1).strip(), sm.group(2).strip()

        rest = "\n".join(chunk_lines[1:])

        genre = None
        country = None
        year = None
        paren = PAREN_RE.search(rest)
        if paren:
            inside = paren.group(1).strip()
            ym = YEAR_RE.search(inside)
            if ym:
                year = int(ym.group(0))
                before_year = inside[: ym.start()].strip().rstrip(",").strip()
                if before_year:
                    country = before_year
            else:
                country = inside or None
            # genre is whatever precedes the parenthesis on its line
            paren_line_start = rest.rfind("\n", 0, paren.start()) + 1
            genre_text = rest[paren_line_start:paren.start()].strip()
            if genre_text:
                genre = genre_text

        duration = None
        dm = DURATION_RE.search(rest)
        if dm:
            duration = int(dm.group(1))

        cast = None
        cm = CAST_RE.search(rest)
        if cm:
            cast = re.sub(r"\s*,\s*", ", ", cm.group(1).strip())

        director = None
        dirm = DIRECTOR_RE.search(rest)
        if dirm:
            director = re.sub(r"\s*,\s*", ", ", dirm.group(1).strip())

        # Synopsis = whatever's left after removing the metadata lines.
        synopsis_lines = []
        for line in rest.split("\n"):
            l = line.strip()
            if not l:
                continue
            if PAREN_RE.search(l) and YEAR_RE.search(l):
                continue
            if l.startswith("Obsada:") or l.startswith("Reżyseria:"):
                continue
            if DURATION_RE.search(l) and len(l) < 40:
                continue
            synopsis_lines.append(l)
        synopsis = " ".join(synopsis_lines).strip() or None

        episode_of = None
        if synopsis:
            fm = TRAILING_FRACTION_RE.search(synopsis)
            if fm:
                episode_of = fm.group(1)
                synopsis = synopsis[: fm.start()].strip()

        entries.append({
            "time": time_str,
            "title": title,
            "series_info": series_info,
            "genre": genre,
            "country": country,
            "year": year,
            "duration_min": duration,
            "cast_list": cast,
            "director": director,
            "synopsis": synopsis,
            "episode_of": episode_of,
        })
    return entries


def passes_filter(entry) -> bool:
    if not entry["year"] or entry["year"] < 2018:
        return False
    if entry["country"] and not QUALIFYING_COUNTRY_RE.search(entry["country"]):
        return False
    return True


def map_country_to_iso(country: str):
    if not country:
        return None
    key = unicodedata.normalize("NFKD", country).encode("ascii", "ignore").decode("ascii").lower().strip()
    return COUNTRY_TO_ISO.get(key)


# ---------------------------------------------------------------------------
# Supabase REST helpers
# ---------------------------------------------------------------------------

def sb_headers(prefer=None):
    h = {
        "apikey": SUPABASE_SERVICE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
        "Content-Type": "application/json",
    }
    if prefer:
        h["Prefer"] = prefer
    return h


def sb_get(table, params):
    r = requests.get(f"{SUPABASE_URL}/rest/v1/{table}", headers=sb_headers(), params=params, timeout=30)
    r.raise_for_status()
    return r.json()


def sb_upsert(table, rows, on_conflict):
    if not rows:
        return
    r = requests.post(
        f"{SUPABASE_URL}/rest/v1/{table}?on_conflict={on_conflict}",
        headers=sb_headers(prefer="resolution=merge-duplicates"),
        data=json.dumps(rows),
        timeout=30,
    )
    if not r.ok:
        print(f"  Supabase upsert into {table} failed: {r.status_code} {r.text}")
    r.raise_for_status()


def sb_insert(table, rows):
    if not rows:
        return
    r = requests.post(
        f"{SUPABASE_URL}/rest/v1/{table}",
        headers=sb_headers(prefer="return=minimal"),
        data=json.dumps(rows),
        timeout=30,
    )
    if not r.ok:
        print(f"  Supabase insert into {table} failed: {r.status_code} {r.text}")
    r.raise_for_status()


# ---------------------------------------------------------------------------
# TMDb resolution
# ---------------------------------------------------------------------------

def tmdb_search(kind, query, language="pl-PL"):
    url = f"https://api.themoviedb.org/3/search/{kind}"
    params = {"api_key": TMDB_API_KEY, "query": query}
    if language:
        params["language"] = language
    r = requests.get(url, params=params, timeout=20)
    if not r.ok:
        return []
    return r.json().get("results", [])


def tmdb_external_ids(kind, tmdb_id):
    url = f"https://api.themoviedb.org/3/{kind}/{tmdb_id}/external_ids"
    r = requests.get(url, params={"api_key": TMDB_API_KEY}, timeout=20)
    if not r.ok:
        return {}
    return r.json()


def pick_best(results, date_field, iso_country, entry_year):
    if iso_country:
        matching = [r for r in results if iso_country in (r.get("origin_country") or [])]
        if matching:
            results = matching

    def year_of(r):
        d = r.get(date_field) or ""
        return int(d[:4]) if d[:4].isdigit() else None

    dated = [(r, year_of(r)) for r in results if year_of(r) and year_of(r) <= entry_year]
    if dated:
        dated.sort(key=lambda t: entry_year - t[1])
        return dated[0][0]
    return results[0] if results else None


def resolve_title(title, country, year):
    slug = slugify(title)
    cached = sb_get("title_links", {"slug": f"eq.{slug}", "select": "*"})
    if cached:
        row = cached[0]
        return row.get("imdb_url"), row.get("matched_original_name")

    iso = map_country_to_iso(country)
    query = title
    results = tmdb_search("tv", query)
    if not results and " - " in title:
        results = tmdb_search("tv", title.split(" - ")[0])
    kind = "tv"
    if not results:
        results = tmdb_search("movie", query)
        kind = "movie"
        if not results and " - " in title:
            results = tmdb_search("movie", title.split(" - ")[0])

    imdb_url = None
    original_name = None
    tmdb_id = None
    imdb_id = None

    if results:
        date_field = "first_air_date" if kind == "tv" else "release_date"
        best = pick_best(results, date_field, iso, year or 2100)
        if best:
            tmdb_id = best["id"]
            original_name = best.get("original_name") or best.get("original_title")
            ext = tmdb_external_ids(kind, tmdb_id)
            imdb_id = ext.get("imdb_id")
            if imdb_id:
                imdb_url = f"https://www.imdb.com/title/{imdb_id}/"

    sb_upsert("title_links", [{
        "slug": slug,
        "title": title,
        "country": iso,
        "tmdb_id": tmdb_id,
        "tmdb_type": kind if results else None,
        "imdb_id": imdb_id,
        "imdb_url": imdb_url,
        "matched_original_name": original_name,
    }], on_conflict="slug")

    return imdb_url, original_name


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    target_date = date.today() - timedelta(days=1)
    print(f"Target date: {target_date.isoformat()}")

    scraped = 0
    skipped = 0
    invalid = 0
    total_entries = 0

    for slug in CHANNELS:
        existing = sb_get("scrape_log", {
            "channel_slug": f"eq.{slug}",
            "date": f"eq.{target_date.isoformat()}",
            "select": "channel_slug",
        })
        if existing:
            skipped += 1
            continue

        display_name, text = fetch_channel_page(slug, target_date)
        if text is None:
            invalid += 1
            continue

        sb_upsert("channels", [{
            "slug": slug,
            "name": display_name,
            "source_url": f"https://programtv.naziemna.info/program/stacja/{slug}",
        }], on_conflict="slug")

        raw_entries = parse_entries(text)
        surviving = [e for e in raw_entries if passes_filter(e)]

        distinct_titles = {}
        for e in surviving:
            if e["title"] not in distinct_titles:
                distinct_titles[e["title"]] = (e["country"], e["year"])

        resolved = {}
        for title, (country, year) in distinct_titles.items():
            imdb_url, original_name = resolve_title(title, country, year)
            resolved[title] = (imdb_url, original_name)

        rows = []
        for e in surviving:
            imdb_url, original_name = resolved[e["title"]]
            rows.append({
                "channel_slug": slug,
                "date": target_date.isoformat(),
                "time": e["time"],
                "title": e["title"],
                "series_info": e["series_info"],
                "genre": e["genre"],
                "country": e["country"],
                "year": e["year"],
                "duration_min": e["duration_min"],
                "cast_list": e["cast_list"],
                "director": e["director"],
                "synopsis": e["synopsis"],
                "episode_of": e["episode_of"],
                "imdb_url": imdb_url,
                "original_name": original_name,
            })

        sb_insert("entries", rows)
        sb_upsert("scrape_log", [{
            "channel_slug": slug,
            "date": target_date.isoformat(),
            "entry_count": len(rows),
        }], on_conflict="channel_slug,date")

        print(f"  [{slug}] {display_name}: {len(raw_entries)} scraped, {len(rows)} kept")
        scraped += 1
        total_entries += len(rows)

    print(
        f"\nDone. {scraped} channels scraped, {skipped} skipped (already done), "
        f"{invalid} had no data for this date. {total_entries} entries written."
    )


if __name__ == "__main__":
    sys.exit(main())
