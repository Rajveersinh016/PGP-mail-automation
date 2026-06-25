"""
deduplicator.py — PGP Glass Intelligence Platform (Version 4)
Handles URL and Title-based duplicate detection.
When intra-batch duplicates occur, resolves in favor of the highest quality source.
"""

import json
import hashlib
import logging
import re
from datetime import datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path

log = logging.getLogger(__name__)

PROCESSED_URLS_FILE = Path(__file__).parent / "processed_urls.json"
MAX_STORED_URLS = 50_000          # Maximum URL hashes to keep in file
MAX_STORED_TITLES = 5_000         # Maximum title hashes to keep in file
TITLE_SIMILARITY_THRESHOLD = 0.82 # 82% match = duplicate

# ── URL Normalization ─────────────────────────────────────────────────────────

def _normalize_url(url: str) -> str:
    """Normalize URL by lowercasing, stripping UTM params, and trailing slashes."""
    url = url.strip().lower()
    url = re.sub(r'[?&](utm_[a-z_]+|source|medium|campaign|ref|referrer|fbclid|gclid|ocid)=[^&]*', '', url)
    url = re.sub(r'[?&]+$', '', url)
    url = url.rstrip('/')
    return url


def _url_hash(url: str) -> str:
    return hashlib.sha256(_normalize_url(url).encode()).hexdigest()


def _title_hash(title: str) -> str:
    """Hash of cleaned, lowercased title for fast exact comparison."""
    cleaned = re.sub(r'\s+', ' ', title.lower().strip())
    return hashlib.sha256(cleaned.encode()).hexdigest()


def _title_similarity(a: str, b: str) -> float:
    """Compute fuzzy similarity between two title strings (0.0 to 1.0)."""
    a_clean = re.sub(r'\s+', ' ', a.lower().strip())
    b_clean = re.sub(r'\s+', ' ', b.lower().strip())
    return SequenceMatcher(None, a_clean, b_clean).ratio()


# ── Storage I/O ───────────────────────────────────────────────────────────────

def _load_store() -> dict:
    """Load processed_urls.json. Returns empty store if file is missing/corrupt."""
    if not PROCESSED_URLS_FILE.exists():
        return {
            "urls": [],
            "url_hashes": [],
            "title_hashes": [],
            "last_run": None,
            "total_processed": 0,
            "runs": []
        }
    try:
        data = json.loads(PROCESSED_URLS_FILE.read_text(encoding="utf-8"))
        data.setdefault("urls", [])
        data.setdefault("url_hashes", [])
        data.setdefault("title_hashes", [])
        data.setdefault("last_run", None)
        data.setdefault("total_processed", 0)
        data.setdefault("runs", [])
        return data
    except (json.JSONDecodeError, OSError) as e:
        log.warning(f"  Could not read processed_urls.json: {e}. Starting fresh.")
        return {
            "urls": [],
            "url_hashes": [],
            "title_hashes": [],
            "last_run": None,
            "total_processed": 0,
            "runs": []
        }


def _save_store(store: dict) -> None:
    """Save updated store back to processed_urls.json."""
    PROCESSED_URLS_FILE.write_text(
        json.dumps(store, indent=2, ensure_ascii=False),
        encoding="utf-8"
    )


# ── Deduplication Core ────────────────────────────────────────────────────────

def get_new_articles(articles: list[dict]) -> list[dict]:
    """
    Filters out duplicate articles using 4-level deduplication:
      - Cross-run: exact URL and Title hashes already sent in past runs are removed.
      - Intra-batch: exact URL and fuzzy Title matches are grouped, and the article
        from the highest priority source is retained.
    """
    store = _load_store()
    known_url_hashes = set(store.get("url_hashes", []))
    known_title_hashes = set(store.get("title_hashes", []))

    # 1. Filter out cross-run duplicates
    candidates = []
    skipped_cross_run = 0
    
    for article in articles:
        url = article.get("url", "")
        title = article.get("title", "")
        if not url or not title:
            continue
            
        uh = _url_hash(url)
        th = _title_hash(title)
        
        if uh in known_url_hashes or th in known_title_hashes:
            skipped_cross_run += 1
            continue
            
        candidates.append(article)

    # 2. Group candidates into duplicate clusters (intra-batch)
    groups = []
    
    for article in candidates:
        url = article["url"]
        title = article["title"]
        uh = _url_hash(url)
        
        added = False
        for g in groups:
            is_dup = False
            for member in g:
                if _url_hash(member["url"]) == uh:
                    is_dup = True
                    break
                if _title_similarity(member["title"], title) >= TITLE_SIMILARITY_THRESHOLD:
                    is_dup = True
                    break
            
            if is_dup:
                g.append(article)
                added = True
                break
                
        if not added:
            groups.append([article])

    # 3. Resolve duplicates in favor of the highest quality source type
    PRIORITY_MAPPING = {
        "company_website": 1,
        "press_release": 2,
        "industry_magazine": 3,
        "government_source": 4,
        "business_news": 5,
        "google_news": 6,
        "other": 7
    }
    
    new_articles = []
    skipped_intra_batch = 0
    
    for g in groups:
        # Sort group by priority score (ascending), then by tier (ascending)
        g.sort(key=lambda a: (
            PRIORITY_MAPPING.get(a.get("priority_type", "other"), 7),
            a.get("tier", 3)
        ))
        
        selected = g[0]
        new_articles.append(selected)
        skipped_intra_batch += len(g) - 1

    log.info(
        f"  ✓ Deduplication: {len(new_articles)} new | "
        f"{skipped_cross_run} cross-run dups removed | "
        f"{skipped_intra_batch} intra-batch dups resolved by priority"
    )
    return new_articles


def update_processed_urls(articles: list[dict]) -> None:
    """
    Append newly-sent article URLs and title hashes to processed_urls.json.
    Called ONLY after successful email delivery.
    """
    if not articles:
        return

    store = _load_store()
    existing_url_hashes = set(store.get("url_hashes", []))
    existing_title_hashes = set(store.get("title_hashes", []))

    new_url_hashes = []
    new_title_hashes = []

    for article in articles:
        url = article.get("url", "")
        title = article.get("title", "")

        if url:
            h = _url_hash(url)
            if h not in existing_url_hashes:
                new_url_hashes.append(h)
                existing_url_hashes.add(h)

        if title:
            th = _title_hash(title)
            if th not in existing_title_hashes:
                new_title_hashes.append(th)
                existing_title_hashes.add(th)

    store["url_hashes"].extend(new_url_hashes)
    store["title_hashes"].extend(new_title_hashes)
    store["total_processed"] = store.get("total_processed", 0) + len(new_url_hashes)
    store["last_run"] = datetime.now(timezone.utc).isoformat()
    store["runs"].append({
        "date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "articles_sent": len(articles),
        "new_urls_added": len(new_url_hashes),
    })

    # Prune if over limit (keep most recent)
    if len(store["url_hashes"]) > MAX_STORED_URLS:
        excess = len(store["url_hashes"]) - MAX_STORED_URLS
        store["url_hashes"] = store["url_hashes"][excess:]
        log.info(f"  Pruned {excess} old URL hashes from store")

    if len(store["title_hashes"]) > MAX_STORED_TITLES:
        excess = len(store["title_hashes"]) - MAX_STORED_TITLES
        store["title_hashes"] = store["title_hashes"][excess:]

    # Keep only last 365 run entries
    store["runs"] = store["runs"][-365:]

    _save_store(store)
    log.info(
        f"  Saved {len(new_url_hashes)} URL hashes + "
        f"{len(new_title_hashes)} title hashes to processed_urls.json "
        f"(total: {store['total_processed']})"
    )
