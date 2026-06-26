"""
main.py — PGP Container Glass Intelligence Platform
Master orchestrator. Runs the simplified, optimized performance-first pipeline:
1. Scrape (Parallel) → 2. Local Filter (Watchlist + Keywords + 24h) → 3. Deduplicate 
→ 4. Gemini AI Analysis & Market Pulse → 5. Report (Pulse + Dashboard) → 6. Email → 7. Logging & Cleanup
"""

import logging
import os
import sys
import json
import re
from datetime import datetime, timezone, timedelta
from pathlib import Path

# Force UTF-8 on Windows
if sys.platform.startswith('win'):
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')

# Logging Setup
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(message)s",
    datefmt="%H:%M:%S",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger(__name__)

DATA_DIR = Path(__file__).parent / "data"
WATCHLIST_FILE = DATA_DIR / "watchlist.json"
KEYWORDS_FILE = DATA_DIR / "keywords.json"
LOGS_DIR = Path(__file__).parent / "logs"

# Fallback context keywords in case file is missing
DEFAULT_CONTEXT_KEYWORDS = [
    "container glass", "bottle", "bottles", "glass packaging", "glass bottle",
    "furnace", "furnaces", "is machine", "is machines", "forming machine",
    "glass plant", "glass factory", "glass production", "glass melt",
    "annealing lehr", "cold end", "hot end", "gob feeder", "batch plant",
    "cullet", "perfume packaging", "luxury bottle", "spirits packaging", "beverage bottle"
]


def _banner(text: str):
    log.info("─" * 55)
    log.info(f"  {text}")
    log.info("─" * 55)


def load_env():
    """Load env variables from .env or .env.example without overwriting existing environment."""
    for filename in (".env", ".env.example"):
        path = Path(__file__).parent / filename
        if path.exists():
            try:
                for line in path.read_text(encoding="utf-8").splitlines():
                    line = line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    key, val = line.split("=", 1)
                    key = key.strip()
                    val = val.strip().strip("'").strip('"')
                    if key and key not in os.environ:
                        os.environ[key] = val
            except Exception as e:
                log.warning(f"Failed to load {filename}: {e}")


def load_watchlist() -> dict:
    """Load structured watchlist.json."""
    if not WATCHLIST_FILE.exists():
        log.warning("Watchlist file data/watchlist.json not found!")
        return {"companies": []}
    try:
        return json.loads(WATCHLIST_FILE.read_text(encoding="utf-8"))
    except Exception as e:
        log.error(f"Error parsing watchlist.json: {e}")
        return {"companies": []}


def load_context_keywords() -> list[str]:
    """Load context keywords from keywords.json or return fallbacks."""
    if not KEYWORDS_FILE.exists():
        log.warning("Keywords file data/keywords.json not found! Using defaults.")
        return DEFAULT_CONTEXT_KEYWORDS
    try:
        data = json.loads(KEYWORDS_FILE.read_text(encoding="utf-8"))
        return data.get("context_keywords", DEFAULT_CONTEXT_KEYWORDS)
    except Exception as e:
        log.error(f"Error loading keywords.json: {e}")
        return DEFAULT_CONTEXT_KEYWORDS


def local_pre_filter(articles: list[dict], watchlist: dict, context_keywords: list[str]) -> list[dict]:
    """
    Keep only articles published in the last 24h that contain 
    at least one watchlist company or alias AND at least one context keyword.
    """
    filtered = []
    now = datetime.now(timezone.utc)
    date_limit = now - timedelta(hours=24)
    
    # 1. Compile company name and alias patterns
    company_patterns = []
    companies = watchlist.get("companies", [])
    for co in companies:
        name = co.get("name", "")
        aliases = co.get("aliases", [])
        terms = [name] + [a for a in aliases if a.strip()]
        for term in terms:
            # Whole-word boundaries to avoid partial matches
            company_patterns.append(re.compile(rf"\b{re.escape(term)}\b", re.IGNORECASE))
            
    # 2. Compile context keywords patterns
    context_patterns = [re.compile(rf"\b{re.escape(w)}\b", re.IGNORECASE) for w in context_keywords]

    log.info(f"Applying local filter (24h limit, {len(company_patterns)} company terms, {len(context_patterns)} context keywords)...")

    for a in articles:
        # Check publication date (strict 24 hours)
        pub_str = a.get("published", "")
        if pub_str:
            try:
                pub_dt = datetime.fromisoformat(pub_str)
                if pub_dt < date_limit:
                    continue
            except Exception:
                pass # If parsing fails, fall back to matching text
                
        # Match company and context in title or text
        title_text = f"{a.get('title', '')} {a.get('raw_text', '')}".lower()
        
        has_company = any(pat.search(title_text) for pat in company_patterns)
        if not has_company:
            continue
            
        has_context = any(pat.search(title_text) for pat in context_patterns)
        if not has_context:
            continue
            
        filtered.append(a)

    log.info(f"✓ Local pre-filter: Kept {len(filtered)}/{len(articles)} candidate articles")
    return filtered


def save_run_log(stats: dict):
    """Save execution statistics to a JSON log file in the logs/ directory."""
    try:
        LOGS_DIR.mkdir(exist_ok=True)
        date_str = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        filename = f"run_{date_str}.json"
        filepath = LOGS_DIR / filename
        filepath.write_text(json.dumps(stats, indent=2, ensure_ascii=False), encoding="utf-8")
        log.info(f"✓ Run statistics saved to: {filepath.name}")
    except Exception as e:
        log.error(f"Failed to save run log: {e}")


def main():
    load_env()
    start_time = datetime.now(timezone.utc)
    
    _banner("PGP Container Glass Daily Intelligence Pipeline (Version 5)")
    log.info(f"Started: {start_time.strftime('%Y-%m-%d %H:%M:%S UTC')}")

    # Standard run statistics dictionary
    run_stats = {
        "run_time": start_time.isoformat(),
        "execution_time_seconds": 0.0,
        "sources_checked": [],
        "articles_collected": 0,
        "duplicates_removed": 0,
        "gemini_accepted": 0,
        "gemini_rejected": 0,
        "email_status": "Pending",
        "errors": []
    }

    # Verify key environment variables
    if not os.environ.get("GEMINI_API_KEY"):
        err_msg = "GEMINI_API_KEY is missing. Pipeline cannot continue."
        log.error(f"✗ {err_msg}")
        run_stats["errors"].append(err_msg)
        run_stats["email_status"] = "Skipped (Configuration Error)"
        save_run_log(run_stats)
        sys.exit(1)

    # 1. Scrape (Parallel)
    _banner("STEP 1: Scraping all sources in parallel")
    from scraper import scrape_all_sources
    try:
        raw_articles, sources_checked = scrape_all_sources()
        run_stats["sources_checked"] = sources_checked
        run_stats["articles_collected"] = len(raw_articles)
    except Exception as e:
        err_msg = f"Scraping failed: {e}"
        log.error(f"✗ {err_msg}")
        run_stats["errors"].append(err_msg)
        run_stats["email_status"] = "Failed"
        run_stats["execution_time_seconds"] = (datetime.now(timezone.utc) - start_time).total_seconds()
        save_run_log(run_stats)
        sys.exit(1)
    
    if not raw_articles:
        log.warning("No raw articles fetched. Exiting.")
        run_stats["email_status"] = "Skipped (No News)"
        run_stats["execution_time_seconds"] = (datetime.now(timezone.utc) - start_time).total_seconds()
        save_run_log(run_stats)
        sys.exit(0)

    # 2. Local Filter
    _banner("STEP 2: Applying fast local pre-filter")
    watchlist = load_watchlist()
    context_keywords = load_context_keywords()
    filtered = local_pre_filter(raw_articles, watchlist, context_keywords)
    
    if not filtered:
        log.info("No candidate articles passed the local pre-filter. Exiting.")
        run_stats["email_status"] = "Skipped (No News)"
        run_stats["execution_time_seconds"] = (datetime.now(timezone.utc) - start_time).total_seconds()
        save_run_log(run_stats)
        sys.exit(0)

    # 3. Deduplicate
    _banner("STEP 3: Removing duplicate articles")
    from deduplicator import get_new_articles, update_processed_urls
    try:
        new_articles, cross_run_count, intra_batch_count = get_new_articles(filtered)
        run_stats["duplicates_removed"] = cross_run_count + intra_batch_count
    except Exception as e:
        err_msg = f"Deduplication failed: {e}"
        log.error(f"✗ {err_msg}")
        run_stats["errors"].append(err_msg)
        run_stats["email_status"] = "Failed"
        run_stats["execution_time_seconds"] = (datetime.now(timezone.utc) - start_time).total_seconds()
        save_run_log(run_stats)
        sys.exit(1)
    
    if not new_articles:
        log.info("All candidates already reported in previous runs. Exiting.")
        run_stats["email_status"] = "Skipped (No News)"
        run_stats["execution_time_seconds"] = (datetime.now(timezone.utc) - start_time).total_seconds()
        save_run_log(run_stats)
        sys.exit(0)

    # 4. Gemini AI Analysis
    _banner("STEP 4: AI relevance validation and summarization")
    from gemini import analyze_article, generate_market_pulse
    from concurrent.futures import ThreadPoolExecutor, as_completed
    curated_articles = []
    
    log.info(f"Starting parallel AI analysis of {len(new_articles)} articles...")
    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = {
            executor.submit(analyze_article, article): article 
            for article in new_articles
        }
        for future in as_completed(futures):
            article = futures[future]
            try:
                analysis = future.result()
                if analysis:
                    run_stats["gemini_accepted"] += 1
                    # Overwrite metadata from Gemini's verified extractions
                    article["company"] = analysis.get("Company", "Unknown")
                    article["country"] = analysis.get("Country", "Unknown")
                    article["category"] = analysis.get("Category", "🌍 Industry Update")
                    article["summary"] = analysis.get("Summary", article["title"])
                    article["business_impact"] = analysis.get("Business Impact", "")
                    article["priority"] = analysis.get("Priority", "Low")
                    article["confidence"] = analysis.get("Confidence", "High")
                    
                    curated_articles.append(article)
                    log.info(f"    ✓ RELEVANT: {article['title'][:55]} -> Company={article['company']} | Priority={article['priority']}")
                else:
                    run_stats["gemini_rejected"] += 1
                    log.info(f"    ✗ Discarded: {article['title'][:55]}")
            except Exception as e:
                run_stats["gemini_rejected"] += 1
                log.error(f"    ✗ Gemini thread error for {article['title'][:55]}: {e}")
                run_stats["errors"].append(f"Gemini thread error: {e}")

    if not curated_articles:
        log.info("No relevant container glass developments found after AI analysis. Exiting.")
        run_stats["email_status"] = "Skipped (No News)"
        run_stats["execution_time_seconds"] = (datetime.now(timezone.utc) - start_time).total_seconds()
        save_run_log(run_stats)
        sys.exit(0)

    # 4b. Generate Daily Market Pulse Paragraph
    log.info("Generating cohesive daily Market Pulse summary...")
    market_pulse = generate_market_pulse(curated_articles)
    log.info(f"Market Pulse summary generated successfully.")

    # 5. Report & Email
    _banner("STEP 5: Generating reports and sending email")
    from reporter import generate_report
    from email_service import send_email
    
    html_body, excel_path = generate_report(curated_articles, market_pulse)
    
    success = send_email(html_body, excel_path, len(curated_articles))

    # 6. Cleanup & Save State
    _banner("STEP 6: Cleaning up temporary files")
    if excel_path and os.path.exists(excel_path):
        try:
            os.remove(excel_path)
            log.info(f"Deleted temp file: {excel_path}")
        except Exception as e:
            log.warning(f"Failed to delete temp Excel file: {e}")

    if success:
        log.info("✓ Email sent successfully. Updating processed_urls.json...")
        run_stats["email_status"] = "Success"
        try:
            update_processed_urls(curated_articles)
        except Exception as e:
            run_stats["errors"].append(f"Updating processed URLs failed: {e}")
    else:
        log.error("✗ Email delivery failed. History NOT updated.")
        run_stats["email_status"] = "Failed"
        run_stats["errors"].append("SMTP delivery failed.")

    elapsed = (datetime.now(timezone.utc) - start_time).total_seconds()
    run_stats["execution_time_seconds"] = elapsed
    save_run_log(run_stats)
    
    _banner(f"DONE — Run completed in {elapsed:.1f}s")
    
    if not success:
        sys.exit(1)


if __name__ == "__main__":
    main()
