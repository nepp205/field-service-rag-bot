"""Download public technical PDF manuals into the local `pdfs/` folder.

This scraper is deliberately **independent** from the existing local PDF collection.
It does not use the current `pdfs/` folder or `pdf_sources.json` to decide what to search for.
Search queries come only from static technical-manual patterns and optional CLI input.

Examples:
    python scrape_similar_pdfs.py --dry-run
    python scrape_similar_pdfs.py --brand miele --max-downloads 5
    python scrape_similar_pdfs.py --query "laborgerät service manual pdf" --update-sources
"""

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
MAX_RESULTS_PER_QUERY = 8
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


def search_duckduckgo(query: str) -> list[dict[str, str]]:
    """Run a simple public web search and return a few result titles and URLs."""
    response = requests.get(
        "https://duckduckgo.com/html/",
        params={"q": query},
        headers=HEADERS,
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")
    results: list[dict[str, str]] = []

    for anchor in soup.select("a.result__a"):
        url = unwrap_search_result_url(anchor.get("href", ""))
        title = anchor.get_text(" ", strip=True)
        if url and title:
            results.append({"title": title, "url": url})
        if len(results) >= MAX_RESULTS_PER_QUERY:
            break

    return results


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
    parser.add_argument("--max-downloads", type=int, default=5, help="Maximum number of new PDFs to download.")
    parser.add_argument("--brand", default="miele", help="Optional brand or vendor name to focus the search on.")
    parser.add_argument("--query", action="append", help="Optional extra search query. Can be used multiple times.")
    parser.add_argument("--update-sources", action="store_true", help="Write newly downloaded sources back to pdf_sources.json.")
    args = parser.parse_args()

    PDF_DIR.mkdir(parents=True, exist_ok=True)
    source_json = load_sources_for_update() if args.update_sources else {}
    queries = build_search_queries(args.brand, args.query)

    downloaded = 0
    seen_urls: set[str] = set()

    print("[Info] Der Scraper arbeitet unabhängig von der vorhandenen PDF-Sammlung.")
    print(f"[Info] {len(queries)} Suchanfragen vorbereitet")

    for query in queries:
        if downloaded >= args.max_downloads:
            break

        print(f"\n[Search] {query}")
        try:
            results = search_duckduckgo(query)
        except requests.RequestException as exc:
            print(f"  -> Suche fehlgeschlagen: {exc}")
            continue

        for result in results:
            if downloaded >= args.max_downloads:
                break

            domain = urlparse(result["url"]).netloc.lower()
            if domain and domain not in ALLOWED_DOMAINS and not result["url"].lower().endswith(".pdf"):
                continue

            if not is_technical_manual_candidate(result["title"], result["url"]):
                continue

            pdf_links = [result["url"]] if result["url"].lower().endswith(".pdf") else extract_pdf_links(result["url"])

            for pdf_url in pdf_links:
                if pdf_url in seen_urls:
                    continue
                seen_urls.add(pdf_url)

                pretty_title = result["title"].strip() or Path(urlparse(pdf_url).path).stem
                safe_name = sanitize_filename(pretty_title)
                print(f"  -> Kandidat: {pretty_title}")
                print(f"     URL: {pdf_url}")

                if args.dry_run:
                    downloaded += 1
                    break

                output = download_pdf(pdf_url, PDF_DIR, preferred_name=f"{safe_name}.pdf")
                if output is None:
                    print("     Download übersprungen (kein direktes PDF oder nicht erreichbar).")
                    continue

                downloaded += 1
                print(f"     Gespeichert als: {output.name}")

                if args.update_sources:
                    source_json[Path(output.name).stem] = {"source": pdf_url}
                break

        time.sleep(SEARCH_DELAY_SECONDS)

    if args.update_sources and not args.dry_run:
        maybe_update_sources_json(source_json)
        print("\n[Done] pdf_sources.json wurde aktualisiert.")

    print(f"\n[Done] Fertig. Neue/gefundenen Kandidaten: {downloaded}")


if __name__ == "__main__":
    main()
