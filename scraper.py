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

ISO_TO_COUNTRY_NAME = {
    "US": "USA", "GB": "UK", "CA": "Canada", "AU": "Australia", "PL": "Poland",
    "DE": "Germany", "FR": "France", "IT": "Italy", "ES": "Spain", "IE": "Ireland",
    "SE": "Sweden", "NO": "Norway", "DK": "Denmark", "BE": "Belgium", "NL": "Netherlands",
    "AT": "Austria", "CH": "Switzerland", "RU": "Russia", "CZ": "Czech Republic",
    "NZ": "New Zealand", "IN": "India", "JP": "Japan", "KR": "South Korea",
    "CN": "China", "BG": "Bulgaria", "IS": "Iceland",
}

QUALIFYING_COUNTRY_RE = re.compile(
    r"\busa\b|united states|\bus\b|\buk\b|united kingdom|wielka brytania|"
    r"canada|kanada|australia",
    re.IGNORECASE,
)

PREMIERA_PREFIX_RE = re.compile(r"^Premiera\s+", re.IGNORECASE)
# Matches just the "odc." marker itself -- what follows varies (a bare number,
# a number in parens, or occasionally a quoted episode name with no number at
# all, e.g. odc. "Pusia") so the number is extracted separately, right after
# locating this marker.
ODC_ANY_RE = re.compile(r"\bodc\.?(?=\s*\(?\d)", re.IGNORECASE)
ODC_NUM_AFTER_RE = re.compile(r"^\s*\(?(\d+)\)?")
SEASON_WORD_RE = re.compile(r"\b(?:sez\.?|sezon|seria|s\.)\s*([IVXLCDM]+|\d+)", re.IGNORECASE)
SEASON_TAIL_STRIP_RE = re.compile(
    r"[\s:,\-]*\b(?:sez\.?|sezon|seria|s\.)\s*(?:[IVXLCDM]+|\d+)[\s:,\-]*$", re.IGNORECASE
)
TRAILING_PUNCT_RE = re.compile(r"[\s:,\-]+$")
BARE_TRAILING_SEASON_RE = re.compile(r"\s+([IVXLCDM]+|\d+)$")
REDUNDANT_EPISODE_SUBTITLE_RE = re.compile(r":\s*Odcinek\s*\d+\s*$", re.IGNORECASE)

_ROMAN_VALUES = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100, "D": 500, "M": 1000}


def _season_number(raw: str):
    if raw.isdigit():
        return int(raw)
    total, prev = 0, 0
    for ch in reversed(raw.upper()):
        val = _ROMAN_VALUES.get(ch)
        if val is None:
            return None
        total = total - val if val < prev else total + val
        prev = max(prev, val)
    return total or None


def split_title_and_series(title_line: str):
    """Split a raw title line into (clean_title, series_info_or_None).

    Handles the several shapes this site uses for season/episode markers:
    "Title - Seria N, odc. M", "Title: Subtitle, sez. N, odc. M" (the episode
    subtitle after the colon is deliberately left attached to the title rather
    than guessed-and-stripped -- blindly splitting on the first colon caused
    real mismatches, e.g. turning "NCIS: Sydney" into generic "NCIS"), a bare
    trailing roman numeral or digit used as a season with NO separator at all
    ("Rekrut V", "Bestia 2"), and a leading "Premiera " badge the site adds to
    premiere episodes (not part of the show's name).
    """
    t = PREMIERA_PREFIX_RE.sub("", title_line.strip())

    episode_num = None
    m = ODC_ANY_RE.search(t)
    if m:
        num_m = ODC_NUM_AFTER_RE.match(t[m.end():])
        if num_m:
            episode_num = num_m.group(1)
        t = t[: m.start()]

    season_num = None
    sm = SEASON_WORD_RE.search(t)
    if sm:
        season_num = _season_number(sm.group(1))
    t = SEASON_TAIL_STRIP_RE.sub("", t)
    t = TRAILING_PUNCT_RE.sub("", t).strip()

    if episode_num is not None and season_num is None:
        bm = BARE_TRAILING_SEASON_RE.search(t)
        if bm:
            season_num = _season_number(bm.group(1))
            t = BARE_TRAILING_SEASON_RE.sub("", t).strip()

    # "Odcinek N" ("Episode N") as the ENTIRE trailing colon-subtitle is always
    # redundant restating of the episode number, never part of the real show
    # name -- unlike an arbitrary subtitle (which we deliberately leave alone,
    # see the docstring), this specific pattern is safe to drop unconditionally.
    t = REDUNDANT_EPISODE_SUBTITLE_RE.sub("", t).strip()

    if not t:
        t = title_line.strip()

    if episode_num is None:
        return t, (f"Sezon {season_num}" if season_num else None)
    if season_num:
        return t, f"Sezon {season_num}, odc. {episode_num}"
    return t, f"odc. {episode_num}"


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
    # Mark block-level boundaries with a placeholder BEFORE collapsing whitespace --
    # the raw HTML source has its own incidental newlines/indentation (meaningless
    # formatting, e.g. one <a> cast-member link per source line) that must NOT be
    # treated as real line breaks, so we collapse ALL whitespace to single spaces
    # and only turn OUR placeholder back into real breaks afterward. Inline tags
    # (i/b/strong/span/a/...) are stripped without any break at all -- the site
    # wraps labels like "<i>Czas</i>: 50min." with the colon outside the tag, so
    # breaking on every tag would split "Czas" from its own colon.
    html = re.sub(r"</?(br|p|div|li|tr|h[1-6])[^>]*>", "\x00", html, flags=re.I)
    text = re.sub(r"<[^>]+>", "", html)
    text = text.replace("&nbsp;", " ").replace("&amp;", "&")
    text = text.replace("&quot;", '"').replace("&#39;", "'")
    text = re.sub(r"\s+", " ", text)
    text = text.replace("\x00", "\n")
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

        title_line = re.sub(r"\s*\|\s*$", "", chunk_lines[0].strip()).strip()
        title, series_info = split_title_and_series(title_line)

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
            cast = re.sub(r"\s*\|\s*$", "", cm.group(1).strip())
            cast = re.sub(r"\s*,\s*", ", ", cast).strip()

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
    if not r.ok:
        print(f"  Supabase GET {table} failed: {r.status_code} {r.text}")
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


def tmdb_details(kind, tmdb_id):
    """Fetch external_ids and credits (cast/crew) in a single request -- both
    are needed per candidate (imdb_id always; credits only when cross-
    checking against scraped cast/director), so append_to_response avoids a
    second round trip for the common case."""
    url = f"https://api.themoviedb.org/3/{kind}/{tmdb_id}"
    r = requests.get(url, params={"api_key": TMDB_API_KEY, "append_to_response": "credits,external_ids"}, timeout=20)
    if not r.ok:
        return {}
    return r.json()


def normalize_name(name):
    ascii_name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"\s+", " ", ascii_name).strip().lower()


def scraped_name_list(raw):
    if not raw:
        return []
    return [normalize_name(p) for p in raw.split(",") if p.strip()]


def credits_overlap_score(details, scraped_cast, scraped_director):
    """Count how many scraped cast/director names (already normalized) show
    up in this TMDb candidate's actual credits. Director matches count for
    more since a shared director is rarer to coincide with a wrong match
    than a shared background cast member."""
    if not scraped_cast and not scraped_director:
        return 0

    credits = details.get("credits") or {}
    cast = credits.get("cast") or []
    crew = credits.get("crew") or []
    created_by = details.get("created_by") or []  # tv only

    tmdb_cast = {normalize_name(p["name"]) for p in cast if p.get("name")}
    tmdb_directors = {normalize_name(p["name"]) for p in crew if p.get("job") == "Director" and p.get("name")}
    tmdb_directors |= {normalize_name(p["name"]) for p in created_by if p.get("name")}

    cast_hits = len(set(scraped_cast) & tmdb_cast)
    director_hits = len(set(scraped_director) & tmdb_directors)
    return cast_hits + 3 * director_hits


def rank_candidates(candidates, iso_country, entry_year):
    """candidates: list of (result_dict, kind) pairs, kind in {"tv", "movie"}.
    Returns candidates ordered best-first (closest scraped year, in either
    direction, to entry_year) so the caller can cross-check more than just
    the top pick against scraped cast/director when there's ambiguity.
    Pooling both kinds together (rather than committing to whichever kind's
    search happened to return results first) matters because a real movie
    can otherwise get permanently matched against an unrelated same-named TV
    show -- see the "Diuna"/Dune and "The Lost City" cases from the
    2026-09-16 historical audit, where the movie search was never even
    attempted since the TV search hadn't come back empty.
    """
    if not candidates:
        return []

    pool = candidates
    if iso_country:
        matching = [(r, k) for r, k in pool if iso_country in (r.get("origin_country") or [])]
        if matching:
            pool = matching

    def year_of(r, k):
        date_field = "first_air_date" if k == "tv" else "release_date"
        d = r.get(date_field) or ""
        return int(d[:4]) if d[:4].isdigit() else None

    # Score by closest year in either direction, not just closest-below --
    # the scraped year (often a production/original-release year) can trail
    # the actual first-air-date by a year, and a below-only filter would drop
    # the real match entirely, silently falling back to an unrelated
    # same-named show that happens to satisfy year <= entry_year (e.g. our
    # scraped 2023 for "Truelove" (2024) matching an unrelated "True Love"
    # (2012) instead, since 2024 was excluded outright).
    dated = [(r, k, year_of(r, k)) for r, k in pool if year_of(r, k) is not None]
    if dated:
        dated.sort(key=lambda t: abs(entry_year - t[2]))
        return [(r, k) for r, k, _ in dated]

    # Neither country nor year narrowed it down. Only trust a plain top-result
    # guess when exactly one candidate is left -- with several undated
    # candidates still in play, guessing the top one is exactly how a generic
    # title like "Bestia" or "FBI" ends up matched to some unrelated
    # same-named show. No confident pick beats a wrong one.
    if len(pool) == 1:
        return pool
    return []


# How many of the top year-ranked candidates to fetch full credits for when
# cast/director cross-checking kicks in. Keeps the extra TMDb calls bounded
# even for a very generic title with many same-named results.
CREDITS_CHECK_LIMIT = 5


SKIP_RESOLUTION_GENRES = {"teleturniej"}


def tmdb_origin_iso(kind, best, details):
    """Best-effort origin country, straight from data already fetched for
    this candidate -- no extra TMDb call needed. TV search results (and
    details) carry origin_country directly; movie details carry
    production_countries instead (movies have no such field in search
    results, only in the full details response we already pulled for the
    imdb_id lookup)."""
    if kind == "tv":
        oc = best.get("origin_country") or details.get("origin_country") or []
        return oc[0] if oc else None
    pc = details.get("production_countries") or []
    return pc[0]["iso_3166_1"] if pc else None


def resolve_title(title, country, year, cast=None, director=None, genre=None):
    slug = slugify(title)
    cached = sb_get("title_links", {"slug": f"eq.{slug}", "select": "*"})
    if cached:
        row = cached[0]
        # The source page didn't state an origin for this scrape, but we may
        # already have one on file from TMDb (backfilled the first time this
        # title was ever resolved) -- offer it up so the caller can fill the
        # gap. Only relevant when THIS run's scrape genuinely had no country;
        # if it did, that's the source of truth and nothing here overrides it.
        origin_name = None if country else ISO_TO_COUNTRY_NAME.get(row.get("country"))
        return row.get("imdb_url"), row.get("matched_original_name"), origin_name

    # Polish game shows essentially never have a meaningful per-episode IMDb
    # identity -- attempting to match one against TMDb just produces a
    # confident-looking false positive (a numbered episode's garbled title
    # coincidentally matching an unrelated foreign film) instead of correctly
    # finding nothing. Skip only AFTER the cache check, not before -- some
    # game shows (e.g. "Postaw na milion") already have a genuinely correct
    # cached match by exact title, and skipping unconditionally would throw
    # that away too. This only prevents NEW risky lookups; see the
    # "Va Banque" / "Koło fortuny" cases from the 2026-09-17 fresh-scrape
    # check for real examples of the failure this avoids.
    if genre and genre.strip().lower() in SKIP_RESOLUTION_GENRES:
        return None, None

    iso = map_country_to_iso(country)

    def gather(query):
        # Always search both catalogs and let pick_best() choose across the
        # combined pool -- searching movie only as a fallback-on-empty-tv
        # means a real movie with the same title as some unrelated TV show
        # never gets a chance to compete for the match at all.
        candidates = [(r, "tv") for r in tmdb_search("tv", query)]
        candidates += [(r, "movie") for r in tmdb_search("movie", query)]
        if not candidates and " - " in query:
            base = query.split(" - ")[0]
            candidates = [(r, "tv") for r in tmdb_search("tv", base)]
            candidates += [(r, "movie") for r in tmdb_search("movie", base)]
        return candidates

    candidates = gather(title)
    if not candidates:
        # A bare trailing roman numeral/digit with no season word (e.g. "Rekrut V",
        # "Bestia 2") sometimes confuses TMDb's search -- retry without it. Whatever
        # comes back still goes through pick_best()'s country/year disambiguation
        # below, same as the first attempt -- never take a blind top result, that's
        # what caused wrong matches (generic short titles like "Bestia"/"FBI"/"Lady"
        # have many unrelated same-named entries worldwide).
        alt = BARE_TRAILING_SEASON_RE.sub("", title).strip()
        if alt and alt != title:
            candidates = gather(alt)

    imdb_url = None
    original_name = None
    tmdb_id = None
    imdb_id = None
    kind = None

    ranked = rank_candidates(candidates, iso, year or 2100)
    scraped_cast = scraped_name_list(cast)
    scraped_director = scraped_name_list(director)

    details_cache = {}

    def get_details(k, tid):
        key = (k, tid)
        if key not in details_cache:
            details_cache[key] = tmdb_details(k, tid)
        return details_cache[key]

    best, kind = None, None
    if ranked:
        best, kind = ranked[0]
        # Only worth cross-checking cast/director when there's more than one
        # year-plausible candidate to choose between, and we actually have
        # scraped names to check against -- otherwise it's just a wasted
        # TMDb call that can't change the outcome.
        if len(ranked) > 1 and (scraped_cast or scraped_director):
            scored = [
                (credits_overlap_score(get_details(k, r["id"]), scraped_cast, scraped_director), r, k)
                for r, k in ranked[:CREDITS_CHECK_LIMIT]
            ]
            # Stable sort: among equal (including zero) scores, the original
            # closest-year ordering from rank_candidates() is preserved, so
            # this only overrides the year-based pick when a candidate's
            # actual cast or director genuinely matches what was scraped.
            scored.sort(key=lambda t: -t[0])
            if scored[0][0] > 0:
                _, best, kind = scored[0]

    origin_name = None
    if best:
        tmdb_id = best["id"]
        original_name = best.get("original_name") or best.get("original_title")
        details = get_details(kind, tmdb_id)
        imdb_id = (details.get("external_ids") or {}).get("imdb_id")
        if imdb_id:
            imdb_url = f"https://www.imdb.com/title/{imdb_id}/"
        if not iso:
            # The scraped page had no origin for this title at all -- TMDb's
            # own country data for the matched title is a reasonable stand-in,
            # and we're already holding these fields from the lookup above,
            # so this costs nothing extra.
            iso = tmdb_origin_iso(kind, best, details)
            origin_name = ISO_TO_COUNTRY_NAME.get(iso)

    sb_upsert("title_links", [{
        "slug": slug,
        "title": title,
        "country": iso,
        "tmdb_id": tmdb_id,
        "tmdb_type": kind,
        "imdb_id": imdb_id,
        "imdb_url": imdb_url,
        "matched_original_name": original_name,
    }], on_conflict="slug")

    return imdb_url, original_name, origin_name


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    override = os.environ.get("TARGET_DATE")
    target_date = date.fromisoformat(override) if override else date.today() - timedelta(days=1)
    print(f"Target date: {target_date.isoformat()}")
    print(f"Supabase URL: {SUPABASE_URL}")
    print(f"Service key length: {len(SUPABASE_SERVICE_KEY)} chars "
          f"(starts with {SUPABASE_SERVICE_KEY[:6]!r})")

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
                distinct_titles[e["title"]] = (e["country"], e["year"], e["cast_list"], e["director"], e["genre"])

        resolved = {}
        for title, (country, year, cast, director, genre) in distinct_titles.items():
            imdb_url, original_name, origin_name = resolve_title(title, country, year, cast, director, genre)
            resolved[title] = (imdb_url, original_name, origin_name)

        rows = []
        for e in surviving:
            imdb_url, original_name, origin_name = resolved[e["title"]]
            rows.append({
                "channel_slug": slug,
                "date": target_date.isoformat(),
                "time": e["time"],
                "title": e["title"],
                "series_info": e["series_info"],
                "genre": e["genre"],
                "country": e["country"] or origin_name,
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
