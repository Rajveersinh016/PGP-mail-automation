"""
scraper.py — PGP Container Glass Intelligence Platform
Parallel configuration-driven scraper supporting RSS, HTML scraping, and Google News.
Executes all scraping tasks concurrently to minimize execution time.
"""

import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote_plus, urljoin
from concurrent.futures import ThreadPoolExecutor, as_completed

import feedparser
import requests
import urllib3
from bs4 import BeautifulSoup
from dateutil import parser as dateparser

log = logging.getLogger(__name__)

# Suppress SSL warnings for verify=False requests
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

DATA_DIR = Path(__file__).parent / "data"
SOURCES_FILE = DATA_DIR / "sources.json"
WATCHLIST_FILE = DATA_DIR / "watchlist.json"

REQUEST_TIMEOUT = 12          # seconds per request
MAX_ARTICLES_PER_SOURCE = 50  # cap per source

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
}

GOOGLE_NEWS_RSS_BASE = "https://news.google.com/rss/search?q={query}&hl=en-US&gl=US&ceid=US:en"


def _parse_date(date_str: str) -> str:
    """Normalize date strings to ISO 8601 UTC. Returns current time if parsing fails."""
    if not date_str:
        return datetime.now(timezone.utc).isoformat()
    try:
        dt = dateparser.parse(date_str)
        if dt is None:
            return datetime.now(timezone.utc).isoformat()
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        else:
            dt = dt.astimezone(timezone.utc)
        return dt.isoformat()
    except Exception:
        return datetime.now(timezone.utc).isoformat()


def _make_article(title: str, url: str, source_name: str, priority_type: str,
                   tier: int, published: str = "", raw_text: str = "") -> dict:
    """Create a standardized article dictionary."""
    return {
        "title": (title or "").strip(),
        "url": (url or "").strip(),
        "source": source_name,
        "priority_type": priority_type,
        "tier": tier,
        "published": _parse_date(published),
        "raw_text": (raw_text or title or "").strip(),
    }


def _safe_get(url: str, verify: bool = True) -> requests.Response | None:
    """HTTP GET with error handling."""
    try:
        resp = requests.get(url, headers=HEADERS, verify=verify, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        return resp
    except Exception:
        return None


def fetch_full_article(url: str) -> str:
    """
    Fetch and clean the full article body from a URL.

    Steps:
    1. HTTP GET the article page.
    2. Strip noise tags: nav, header, footer, script, style, aside, form, ads.
    3. Find the main article container (article tag, role=main, common class names).
    4. Extract clean plain text, collapse whitespace.
    5. Return text truncated to 6000 characters (Gemini token budget).

    Returns empty string on failure so callers can fall back to raw_text.
    """
    NOISE_TAGS = ["nav", "header", "footer", "script", "style", "aside", "form",
                  "noscript", "iframe", "figure", "figcaption"]
    NOISE_CLASSES = [
        "ad", "ads", "advertisement", "sidebar", "side-bar", "widget",
        "related", "related-articles", "recommended", "newsletter", "subscribe",
        "social", "share", "comments", "comment", "breadcrumb", "pagination",
        "cookie", "banner", "promo", "popup", "menu", "nav", "navigation",
    ]
    ARTICLE_SELECTORS = [
        "article",
        "[role='main']",
        ".post-content",
        ".article-body",
        ".article-content",
        ".entry-content",
        ".story-body",
        ".story-content",
        ".content-body",
        ".news-body",
        ".article__body",
        ".post-body",
        "main",
        "#main-content",
        "#content",
    ]
    MAX_CHARS = 6000

    resp = _safe_get(url)
    if not resp:
        return ""

    try:
        soup = BeautifulSoup(resp.text, "lxml")

        # Remove noise tags entirely
        for tag in soup.find_all(NOISE_TAGS):
            tag.decompose()

        # Remove elements with noise classes or IDs
        for noise_cls in NOISE_CLASSES:
            for tag in soup.find_all(class_=re.compile(noise_cls, re.IGNORECASE)):
                tag.decompose()
            for tag in soup.find_all(id=re.compile(noise_cls, re.IGNORECASE)):
                tag.decompose()

        # Find the best article container
        container = None
        for selector in ARTICLE_SELECTORS:
            container = soup.select_one(selector)
            if container:
                break

        # Fall back to body if nothing matched
        if not container:
            container = soup.find("body") or soup

        # Extract clean text
        text = container.get_text(separator="\n", strip=True)

        # Collapse excessive blank lines
        lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
        cleaned = "\n".join(lines)

        return cleaned[:MAX_CHARS]

    except Exception as e:
        log.debug(f"fetch_full_article failed for {url}: {e}")
        return ""


def _generate_watchlist_queries(watchlist: dict) -> list[str]:

    """
    Construct optimized queries grouped by OR logic for every watchlist company.
    Combines company name + aliases with container glass industry context suffixes.
    """
    companies = watchlist.get("companies", [])
    suffixes = [
        "expansion", "new plant", "investment", "furnace", 
        "bottle", "packaging", "acquisition", "sustainability"
    ]
    queries = []
    
    for co in companies:
        name = co.get("name", "")
        aliases = co.get("aliases", [])
        if not name:
            continue
            
        # Collect all active non-empty names
        names = [name] + [a for a in aliases if a.strip()]
        names_escaped = []
        for n in names:
            if " " in n or "-" in n or "/" in n:
                names_escaped.append(f'"{n}"')
            else:
                names_escaped.append(n)
                
        names_part = " OR ".join(names_escaped)
        if len(names_escaped) > 1:
            names_part = f"({names_part})"
            
        # Format suffixes (wrap multi-word suffixes in quotes, e.g. "new plant")
        suffixes_escaped = []
        for s in suffixes:
            if " " in s:
                suffixes_escaped.append(f'"{s}"')
            else:
                suffixes_escaped.append(s)
        suffixes_part = " OR ".join(suffixes_escaped)
        
        # Build optimized Google News query string
        query = f"{names_part} AND ({suffixes_part})"
        queries.append(query)
        
    return queries


def scrape_rss(source: dict) -> list[dict]:
    """Parse RSS feed."""
    articles = []
    name = source["name"]
    url = source["rss_url"]
    tier = source["tier"]
    priority_type = source["priority_type"]
    
    try:
        feed = feedparser.parse(url, agent=HEADERS["User-Agent"])
        entries = feed.entries[:MAX_ARTICLES_PER_SOURCE]
        for entry in entries:
            title = entry.get("title", "")
            link = entry.get("link", "")
            published = entry.get("published", entry.get("updated", ""))
            summary_html = entry.get("summary", entry.get("description", ""))
            
            raw_text = title
            if summary_html:
                try:
                    raw_text = BeautifulSoup(summary_html, "lxml").get_text(separator=" ")
                except Exception:
                    pass
            if title and link:
                articles.append(_make_article(title, link, name, priority_type, tier, published, raw_text))
    except Exception as e:
        log.warning(f"Failed to crawl RSS {name}: {e}")
    return articles


def scrape_html(source: dict) -> list[dict]:
    """Scrapes news articles from an HTML webpage."""
    articles = []
    name = source["name"]
    url = source["web_url"]
    tier = source["tier"]
    priority_type = source["priority_type"]
    cfg = source.get("scraping_config", {})
    selector = cfg.get("selector", "")
    verify = cfg.get("verify_ssl", True)
    
    resp = _safe_get(url, verify=verify)
    if not resp:
        return articles

    try:
        soup = BeautifulSoup(resp.text, "lxml")
        tags = soup.select(selector) if selector else []
        if not tags:
            tags = soup.select("article a, h2 a, h3 a, .news a, .article a, .news-item a")
            
        seen = set()
        for tag in tags[:MAX_ARTICLES_PER_SOURCE]:
            anchor = tag if tag.name == "a" else tag.find("a")
            if not anchor:
                continue
                
            title = anchor.get_text(strip=True)
            href = anchor.get("href", "")
            if not title or not href or href in seen or len(title) < 15:
                continue
                
            href = urljoin(url, href)
            seen.add(href)
            
            date_str = ""
            parent = anchor.find_parent(["div", "article", "li", "tr"])
            if parent:
                date_match = re.search(r'\b\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{4}\b|\b\d{4}-\d{2}-\d{2}\b', parent.get_text())
                if date_match:
                    date_str = date_match.group(0)
                    
            articles.append(_make_article(title, href, name, priority_type, tier, date_str, raw_text=title))
    except Exception as e:
        log.warning(f"Error parsing HTML {name}: {e}")
    return articles


def scrape_google_news_rss(query: str, source_name: str, priority_type: str, tier: int) -> list[dict]:
    """Parse articles from a Google News RSS query."""
    articles = []
    url = GOOGLE_NEWS_RSS_BASE.format(query=quote_plus(query))
    try:
        feed = feedparser.parse(url, agent=HEADERS["User-Agent"])
        entries = feed.entries[:MAX_ARTICLES_PER_SOURCE]
        for entry in entries:
            title = entry.get("title", "")
            link = entry.get("link", "")
            published = entry.get("published", entry.get("updated", ""))
            summary_html = entry.get("summary", entry.get("description", ""))
            
            raw_text = title
            if summary_html:
                try:
                    raw_text = BeautifulSoup(summary_html, "lxml").get_text(separator=" ")
                except Exception:
                    pass
            if title and link:
                articles.append(_make_article(title, link, source_name, priority_type, tier, published, raw_text))
    except Exception as e:
        log.warning(f"Google News query failed '{query[:40]}': {e}")
    return articles


def scrape_source(source: dict, watchlist_data: dict) -> list[dict]:
    """Scrape a single configured source based on its method."""
    method = source.get("scraping_method", "html")
    name = source["name"]
    tier = source.get("tier", 3)
    priority_type = source.get("priority_type", "other")
    
    if source.get("status") == "inactive":
        return []

    try:
        if method == "rss":
            return scrape_rss(source)
        elif method == "html":
            return scrape_html(source)
        elif method == "google_news":
            cfg = source.get("scraping_config", {})
            query = cfg.get("query", "")
            if query:
                return scrape_google_news_rss(query, name, priority_type, tier)
        elif method == "google_news_watchlist":
            if not watchlist_data:
                return []
            queries = _generate_watchlist_queries(watchlist_data)
            
            # Scrape watchlist queries in parallel to speed it up!
            watchlist_articles = []
            with ThreadPoolExecutor(max_workers=6) as executor:
                futures = {
                    executor.submit(scrape_google_news_rss, q, f"Google News (Watchlist - {co_name})", "company_website", tier): q 
                    for q, co_name in zip(queries, [c.get("name", "Unknown") for c in watchlist_data.get("companies", [])])
                }
                for future in as_completed(futures):
                    try:
                        watchlist_articles.extend(future.result())
                    except Exception as e:
                        log.warning(f"Watchlist query thread failed: {e}")
            return watchlist_articles
    except Exception as e:
        log.error(f"Error scraping source {name}: {e}")
        
    return []


def scrape_all_sources() -> tuple[list[dict], list[str]]:
    """
    Load sources, perform scraping in parallel using ThreadPoolExecutor.
    Returns a tuple of (all_articles, list_of_sources_checked).
    """
    if not SOURCES_FILE.exists():
        log.error(f"Sources registry file not found at {SOURCES_FILE}")
        return [], []
        
    sources_data = json.loads(SOURCES_FILE.read_text(encoding="utf-8"))
    watchlist_data = {}
    if WATCHLIST_FILE.exists():
        watchlist_data = json.loads(WATCHLIST_FILE.read_text(encoding="utf-8"))
        
    all_articles = []
    sources_checked = []
    
    active_sources = [s for s in sources_data if s.get("status") != "inactive"]
    
    log.info(f"Starting parallel scrape of {len(active_sources)} active sources...")
    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = {
            executor.submit(scrape_source, source, watchlist_data): source 
            for source in active_sources
        }
        for future in as_completed(futures):
            source = futures[future]
            name = source['name']
            sources_checked.append(name)
            try:
                res = future.result()
                all_articles.extend(res)
                log.info(f"  ✓ {name}: Scraped {len(res)} articles")
            except Exception as e:
                log.error(f"  ✗ Thread error for {name}: {e}")
                
    # Clean up results
    all_articles = [a for a in all_articles if a.get("url") and a.get("title")]
    log.info(f"Parallel scraping complete. Collected {len(all_articles)} raw articles.")
    return all_articles, sources_checked
