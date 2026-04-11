"""Download public technical PDF manuals into the local `pdfs/` folder.

This scraper is deliberately **independent** from the existing local PDF collection.
It does not use the current `pdfs/` folder or `pdf_sources.json` to decide what to search for.
Search queries come only from static technical-manual patterns and optional CLI input.

Examples:
    python scrape_similar_pdfs.py --dry-run
    python scrape_similar_pdfs.py --brand miele --max-downloads 5
    python scrape_similar_pdfs.py --query "laborgerät service manual pdf" --update-sources
"""

# Volsständig mit KI erstellen lassen 1 mal Nutzen

from __future__ import annotations

import argparse
import json
import re
import time
from pathlib import Path
from urllib.parse import parse_qs, unquote, urljoin, urlparse

import requests
from bs4 import BeautifulSoup

BASE_DIR = Path(__file__).resolve().parent
PDF_DIR = BASE_DIR / "pdfs"
SOURCES_JSON = BASE_DIR / "pdf_sources.json"

ALLOWED_DOMAINS = {
    "manualslib.de",
    "www.manualslib.de",
    "gastrouniversum.de",
    "www.gastrouniversum.de",
    "manualzz.com",
    "www.manualzz.com",
}

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0 Safari/537.36"
    )
}

SEARCH_DELAY_SECONDS = 1.5
REQUEST_TIMEOUT_SECONDS = 25
MAX_RESULTS_PER_QUERY = 20
TECHNICAL_KEYWORDS = (
    "pdf",
    "manual",
    "bedienungsanleitung",
    "gebrauchsanweisung",
    "service manual",
    "technical",
    "technical data",
    "gerät",
    "störung",
    "fehler",
    "waschmaschine",
    "geschirrspüler",
    "dryer",
    "washer",
)
DEFAULT_SEARCH_QUERIES = (
    "bedienungsanleitung technische geräte pdf",
    "service manual technische geräte pdf",
    "service manual waschmaschine pdf",
    "bedienungsanleitung geschirrspüler pdf",
    "miele professional manual pdf",
)


def sanitize_filename(value: str) -> str:
    """Create a Windows-safe PDF file name."""
    sanitized = re.sub(r"[<>:\"/\\|?*]+", "_", value).strip(" ._")
    return sanitized or "downloaded_manual"


def build_search_queries(brand: str, extra_queries: list[str] | None) -> list[str]:
    """Build simple, fully static search queries for technical manuals."""
    queries = list(DEFAULT_SEARCH_QUERIES)

    if brand:
        brand = brand.strip()
        queries.extend(
            [
                f"{brand} bedienungsanleitung pdf",
                f"{brand} service manual pdf",
                f"{brand} technical manual pdf",
            ]
        )

    if extra_queries:
        queries.extend(query.strip() for query in extra_queries if query and query.strip())

    seen: set[str] = set()
    ordered_queries: list[str] = []
    for query in queries:
        if query not in seen:
            ordered_queries.append(query)
            seen.add(query)
    return ordered_queries


def unwrap_search_result_url(href: str) -> str:
    """Extract the real result URL from DuckDuckGo redirect links."""
    if not href:
        return ""

    if href.startswith("//"):
        href = f"https:{href}"

    if href.startswith("/l/?"):
        parsed = parse_qs(urlparse(href).query)
        return unquote(parsed.get("uddg", [""])[0])

    return href


def unique_results(items: list[dict[str, str]]) -> list[dict[str, str]]:
    """Deduplicate result dictionaries while keeping their original order."""
    ordered: list[dict[str, str]] = []
    seen_urls: set[str] = set()

    for item in items:
        url = item.get("url", "").strip()
        if not url or url in seen_urls:
            continue

        title = item.get("title", "").strip()
        if not title:
            title = Path(urlparse(url).path).stem.replace("-", " ") or url

        ordered.append({"title": title, "url": url})
        seen_urls.add(url)

    return ordered


def build_site_search_terms(query: str, brand: str = "") -> list[str]:
    """Derive short fallback terms for on-site catalog searches."""
    stop_words = {
        "pdf",
        "manual",
        "bedienungsanleitung",
        "gebrauchsanweisung",
        "service",
        "technical",
        "technische",
        "geräte",
        "gerate",
        "gerät",
        "gerat",
        "data",
        "störung",
        "storung",
        "fehler",
        "und",
        "the",
    }

    terms: list[str] = []
    if brand and brand.strip():
        terms.append(brand.strip())

    words = [
        word
        for word in re.findall(r"[a-zA-Z0-9äöüÄÖÜß-]+", query.lower())
        if len(word) > 2 and word not in stop_words
    ]
    if words:
        terms.append(" ".join(words[:3]))
        terms.extend(words[:2])

    if not terms and query.strip():
        terms.append(query.strip())

    seen: set[str] = set()
    ordered_terms: list[str] = []
    for term in terms:
        normalized = term.strip()
        if normalized and normalized not in seen:
            ordered_terms.append(normalized)
            seen.add(normalized)
    return ordered_terms


def search_manualslib(keyword: str) -> list[dict[str, str]]:
    """Search ManualsLib directly for manual pages when public search engines are blocked."""
    if not keyword:
        return []

    response = requests.get(
        "https://www.manualslib.de/",
        params={"keyword": keyword},
        headers=HEADERS,
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")
    results: list[dict[str, str]] = []

    generic_titles = {
        "bedienungsanleitung",
        "gebrauchsanweisung",
        "handbuch",
        "anweisungen",
        "montageanleitung",
        "parallelinstallation",
    }

    for anchor in soup.select('a[href*="/manual/"]'):
        absolute = urljoin(response.url, anchor.get("href", "").strip())
        if not absolute:
            continue

        domain = urlparse(absolute).netloc.lower()
        if domain not in ALLOWED_DOMAINS:
            continue

        title = anchor.get_text(" ", strip=True)
        if not title or title.lower() in generic_titles:
            title = Path(urlparse(absolute).path).stem.replace("-", " ")

        results.append({"title": f"ManualsLib: {title}", "url": absolute})
        if len(results) >= MAX_RESULTS_PER_QUERY:
            break

    return unique_results(results)


def search_gastrouniversum(keyword: str) -> list[dict[str, str]]:
    """Search Gastrouniversum product pages that frequently expose direct PDF manuals."""
    if not keyword:
        return []

    response = requests.get(
        "https://www.gastrouniversum.de/search",
        params={"sSearch": keyword},
        headers=HEADERS,
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")
    results: list[dict[str, str]] = []
    keyword_tokens = {token for token in re.findall(r"[a-zA-Z0-9äöüÄÖÜß-]+", keyword.lower()) if len(token) > 2}

    for anchor in soup.select("a[href]"):
        absolute = urljoin(response.url, anchor.get("href", "").strip())
        if not absolute:
            continue

        parsed = urlparse(absolute)
        domain = parsed.netloc.lower()
        if domain not in ALLOWED_DOMAINS:
            continue

        if absolute.lower().endswith(".pdf"):
            title = anchor.get_text(" ", strip=True) or Path(parsed.path).stem.replace("-", " ")
            results.append({"title": title, "url": absolute})
        else:
            if parsed.path.startswith("/search") or not re.search(r"/\d{3,}/", parsed.path):
                continue

            title = anchor.get_text(" ", strip=True) or Path(parsed.path).stem.replace("-", " ")
            haystack = f"{title} {absolute}".lower()
            if keyword_tokens and not any(token in haystack for token in keyword_tokens):
                continue

            results.append({"title": title, "url": absolute})

        if len(results) >= MAX_RESULTS_PER_QUERY:
            break

    return unique_results(results)


def search_duckduckgo(query: str, brand: str = "") -> list[dict[str, str]]:
    """Run a public web search and fall back to site-native catalog searches if blocked."""
    results: list[dict[str, str]] = []

    try:
        response = requests.get(
            "https://duckduckgo.com/html/",
            params={"q": query},
            headers=HEADERS,
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        response.raise_for_status()

        blocked_text = response.text.lower()
        if response.status_code != 202 and "bots use duckduckgo too" not in blocked_text:
            soup = BeautifulSoup(response.text, "html.parser")
            for anchor in soup.select("a.result__a, a.result-link"):
                url = unwrap_search_result_url(anchor.get("href", ""))
                title = anchor.get_text(" ", strip=True)
                if url and title:
                    results.append({"title": title, "url": url})
                if len(results) >= MAX_RESULTS_PER_QUERY:
                    break
    except requests.RequestException:
        results = []

    if results:
        return unique_results(results)

    for term in build_site_search_terms(query, brand):
        for search_fn in (search_manualslib, search_gastrouniversum):
            try:
                results.extend(search_fn(term))
            except requests.RequestException:
                continue

        deduplicated = unique_results(results)
        if len(deduplicated) >= MAX_RESULTS_PER_QUERY:
            return deduplicated[:MAX_RESULTS_PER_QUERY]

    return unique_results(results)[:MAX_RESULTS_PER_QUERY]


def is_technical_manual_candidate(title: str, url: str) -> bool:
    """Keep only search results that look like technical manuals or PDF documentation."""
    haystack = f"{title} {url}".lower()
    return any(keyword in haystack for keyword in TECHNICAL_KEYWORDS)


def is_pdf_response(response: requests.Response, url: str) -> bool:
    """Check whether the current response is a direct PDF download."""
    content_type = (response.headers.get("Content-Type") or "").lower()
    return "application/pdf" in content_type or url.lower().endswith(".pdf")


def extract_pdf_links(page_url: str) -> list[str]:
    """Open a page and collect direct PDF links from it."""
    try:
        response = requests.get(page_url, headers=HEADERS, timeout=REQUEST_TIMEOUT_SECONDS)
        response.raise_for_status()
    except requests.RequestException:
        return []

    if is_pdf_response(response, page_url):
        return [page_url]

    soup = BeautifulSoup(response.text, "html.parser")
    links: list[str] = []
    seen: set[str] = set()

    for anchor in soup.select("a[href]"):
        absolute = urljoin(page_url, anchor.get("href", "").strip())
        if not absolute:
            continue

        domain = urlparse(absolute).netloc.lower()
        if absolute.lower().endswith(".pdf") and (not domain or domain in ALLOWED_DOMAINS):
            if absolute not in seen:
                links.append(absolute)
                seen.add(absolute)

    return links


def download_pdf(url: str, destination_dir: Path, preferred_name: str | None = None) -> Path | None:
    """Download a direct PDF link into the local collection folder."""
    try:
        response = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT_SECONDS)
        response.raise_for_status()
    except requests.RequestException:
        return None

    if not is_pdf_response(response, url):
        return None

    file_name = preferred_name or Path(unquote(urlparse(url).path)).name or "manual.pdf"
    if not file_name.lower().endswith(".pdf"):
        file_name = f"{file_name}.pdf"

    output_path = destination_dir / sanitize_filename(file_name)
    counter = 1
    while output_path.exists():
        output_path = destination_dir / sanitize_filename(f"{Path(file_name).stem}_{counter}.pdf")
        counter += 1

    output_path.write_bytes(response.content)
    return output_path


def canonicalize_url(url: str) -> str:
    """Normalize URLs so the same PDF is not downloaded repeatedly."""
    parsed = urlparse(url.strip())
    return parsed._replace(query="", fragment="").geturl()


def normalize_identifier(value: str) -> str:
    """Normalize titles/file names to detect duplicates across runs."""
    stem = Path(value).stem
    stem = re.sub(r"_\d+$", "", stem)
    return re.sub(r"[^a-z0-9]+", "", stem.lower())


def collect_known_downloads() -> tuple[set[str], set[str], dict[str, dict[str, str]]]:
    """Read known sources and local PDF names so only new manuals are fetched."""
    source_map = load_sources_for_update()
    known_urls: set[str] = set()
    known_names: set[str] = set()

    for name, meta in source_map.items():
        known_names.add(normalize_identifier(name))
        if isinstance(meta, dict):
            source = (meta.get("source") or "").strip()
            if source:
                known_urls.add(canonicalize_url(source))

    if PDF_DIR.exists():
        for pdf_path in PDF_DIR.glob("*.pdf"):
            known_names.add(normalize_identifier(pdf_path.stem))

    return known_urls, known_names, source_map


def update_source_map(source_map: dict[str, dict[str, str]], name: str, source_url: str) -> None:
    """Insert or refresh a source entry without creating normalized duplicates."""
    normalized_name = normalize_identifier(name)
    canonical_source = canonicalize_url(source_url)

    for existing_name, meta in source_map.items():
        if normalize_identifier(existing_name) == normalized_name:
            if not isinstance(meta, dict):
                source_map[existing_name] = {"source": canonical_source}
            else:
                meta["source"] = canonical_source
            return

    source_map[name] = {"source": canonical_source}


def load_sources_for_update() -> dict[str, dict[str, str]]:
    """Load `pdf_sources.json` only when we want to append new downloads."""
    if not SOURCES_JSON.exists():
        return {}

    with open(SOURCES_JSON, "r", encoding="utf-8") as file:
        return json.load(file)


def maybe_update_sources_json(source_map: dict[str, dict[str, str]]) -> None:
    """Persist discovered source URLs back into pdf_sources.json."""
    with open(SOURCES_JSON, "w", encoding="utf-8") as file:
        json.dump(source_map, file, ensure_ascii=False, indent=4)


def main() -> None:
    parser = argparse.ArgumentParser(description="Find and download additional technical PDF manuals.")
    parser.add_argument("--dry-run", action="store_true", help="Only print candidates; do not download anything.")
    parser.add_argument(
        "--max-downloads",
        type=int,
        default=0,
        help="Maximum number of new PDFs to download. 0 means unlimited until you stop the scraper.",
    )
    parser.add_argument("--brand", default="miele", help="Optional brand or vendor name to focus the search on.")
    parser.add_argument("--query", action="append", help="Optional extra search query. Can be used multiple times.")
    parser.add_argument(
        "--no-update-sources",
        action="store_true",
        help="Do not write discovered sources back to pdf_sources.json.",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Run only one search round and then exit. Default behavior keeps running until you stop it.",
    )
    parser.add_argument(
        "--loop-delay",
        type=int,
        default=120,
        help="Seconds to wait between rounds in continuous mode.",
    )
    args = parser.parse_args()

    PDF_DIR.mkdir(parents=True, exist_ok=True)
    known_urls, known_names, source_json = collect_known_downloads()
    queries = build_search_queries(args.brand, args.query)
    should_update_sources = not args.dry_run and not args.no_update_sources

    downloaded = 0
    cycle = 0

    print("[Info] Der Scraper arbeitet unabhängig von der vorhandenen PDF-Sammlung.")
    print(f"[Info] {len(queries)} Suchanfragen vorbereitet")
    print(f"[Info] Bereits bekannte PDFs/Quellen werden übersprungen: {len(known_names)} Namen, {len(known_urls)} URLs")
    if should_update_sources:
        print("[Info] `pdf_sources.json` wird automatisch aktualisiert.")
    if not args.once and not args.dry_run:
        print(f"[Info] Kontinuierlicher Modus aktiv. Stoppen mit Strg+C. Wartezeit: {args.loop_delay}s")

    try:
        while True:
            cycle += 1
            cycle_downloaded = 0
            seen_urls: set[str] = set()

            print(f"\n[Cycle] Runde {cycle}")

            for query in queries:
                if args.max_downloads > 0 and downloaded >= args.max_downloads:
                    break

                print(f"\n[Search] {query}")
                try:
                    results = search_duckduckgo(query, args.brand)
                except requests.RequestException as exc:
                    print(f"  -> Suche fehlgeschlagen: {exc}")
                    continue

                for result in results:
                    if args.max_downloads > 0 and downloaded >= args.max_downloads:
                        break

                    domain = urlparse(result["url"]).netloc.lower()
                    if domain and domain not in ALLOWED_DOMAINS and not result["url"].lower().endswith(".pdf"):
                        continue

                    if not is_technical_manual_candidate(result["title"], result["url"]):
                        continue

                    pdf_links = [result["url"]] if result["url"].lower().endswith(".pdf") else extract_pdf_links(result["url"])

                    for pdf_url in pdf_links:
                        canonical_pdf_url = canonicalize_url(pdf_url)
                        if canonical_pdf_url in seen_urls or canonical_pdf_url in known_urls:
                            continue
                        seen_urls.add(canonical_pdf_url)

                        pretty_title = result["title"].strip() or Path(urlparse(pdf_url).path).stem
                        safe_name = sanitize_filename(pretty_title)
                        normalized_name = normalize_identifier(safe_name)
                        if normalized_name in known_names:
                            print(f"  -> Übersprungen (bereits vorhanden): {pretty_title}")
                            known_urls.add(canonical_pdf_url)
                            if should_update_sources:
                                update_source_map(source_json, safe_name, canonical_pdf_url)
                                maybe_update_sources_json(source_json)
                            continue

                        print(f"  -> Kandidat: {pretty_title}")
                        print(f"     URL: {pdf_url}")

                        if args.dry_run:
                            downloaded += 1
                            cycle_downloaded += 1
                            known_urls.add(canonical_pdf_url)
                            known_names.add(normalized_name)
                            break

                        output = download_pdf(pdf_url, PDF_DIR, preferred_name=f"{safe_name}.pdf")
                        if output is None:
                            print("     Download übersprungen (kein direktes PDF oder nicht erreichbar).")
                            continue

                        downloaded += 1
                        cycle_downloaded += 1
                        known_urls.add(canonical_pdf_url)
                        known_names.add(normalize_identifier(output.stem))
                        print(f"     Gespeichert als: {output.name}")

                        if should_update_sources:
                            update_source_map(source_json, Path(output.name).stem, canonical_pdf_url)
                            maybe_update_sources_json(source_json)
                        break

                time.sleep(SEARCH_DELAY_SECONDS)

            if args.max_downloads > 0 and downloaded >= args.max_downloads:
                break

            if args.dry_run or args.once:
                break

            print(
                f"\n[Wait] Runde {cycle} abgeschlossen. Neue Kandidaten/Downloads: {cycle_downloaded}. "
                f"Nächster Durchlauf in {args.loop_delay} Sekunden..."
            )
            time.sleep(max(args.loop_delay, 1))

    except KeyboardInterrupt:
        print("\n[Stop] Vom Benutzer beendet.")

    if should_update_sources:
        maybe_update_sources_json(source_json)
        print("\n[Done] pdf_sources.json wurde aktualisiert.")

    print(f"\n[Done] Fertig. Neue/gefundenen Kandidaten: {downloaded}")


if __name__ == "__main__":
    main()
