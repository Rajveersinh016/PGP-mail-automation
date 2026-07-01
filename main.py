"""
main.py — PGP Container Glass Intelligence Platform
Master orchestrator. Runs the simplified, optimized performance-first pipeline:
1. Health Checks → 2. Retry Loop (Scrape -> Filter -> Deduplicate -> Gemini -> Report -> Email -> Save State)
"""

import logging
import os
import sys
import json
import re
import time
from contextlib import contextmanager
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone, timedelta
from pathlib import Path

# Force UTF-8 on Windows
if sys.platform.startswith('win'):
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')

# IST timezone (UTC+5:30)
IST = timezone(timedelta(hours=5, minutes=30))

# Logging Setup — include full date+time so every log line is unambiguous
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger(__name__)

DATA_DIR = Path(__file__).parent / "data"
WATCHLIST_FILE = DATA_DIR / "watchlist.json"
KEYWORDS_FILE = DATA_DIR / "keywords.json"
LOGS_DIR = Path(__file__).parent / "logs"

DEFAULT_CONTEXT_KEYWORDS = [
    "container glass", "bottle", "bottles", "glass packaging", "glass bottle",
    "furnace", "furnaces", "is machine", "is machines", "forming machine",
    "glass plant", "glass factory", "glass production", "glass melt",
    "annealing lehr", "cold end", "hot end", "gob feeder", "batch plant",
    "cullet", "perfume packaging", "luxury bottle", "spirits packaging", "beverage bottle"
]


def _banner(text: str):
    log.info("─" * 60)
    log.info(f"  {text}")
    log.info("─" * 60)


def _ts(dt: datetime | None = None, tz: timezone = timezone.utc) -> str:
    """Return a formatted timestamp string in the given timezone."""
    d = (dt or datetime.now(timezone.utc)).astimezone(tz)
    label = "IST" if tz == IST else "UTC"
    return d.strftime(f"%Y-%m-%d %H:%M:%S {label}")


def ensure_directories():
    """Ensure required runtime directories exist."""
    base_dir = Path(__file__).parent
    for folder in ["logs", "reports", "temp", "output"]:
        (base_dir / folder).mkdir(exist_ok=True)


def setup_file_logging(start_time: datetime):
    """Set up file logging to logs/YYYY-MM-DD_HH-MM-SS.log using local machine time."""
    local_time = start_time.astimezone()
    filename = local_time.strftime("%Y-%m-%d_%H-%M-%S.log")
    log_filepath = LOGS_DIR / filename

    # Ensure logs directory exists
    LOGS_DIR.mkdir(exist_ok=True)

    file_handler = logging.FileHandler(log_filepath, encoding="utf-8")
    file_handler.setFormatter(logging.Formatter("%(asctime)s  %(message)s", datefmt="%Y-%m-%d %H:%M:%S"))
    logging.getLogger().addHandler(file_handler)

    return local_time.strftime("%Y-%m-%d %H:%M:%S"), log_filepath


def write_log_summary(run_stats: dict, exit_code: int):
    """Write standard execution summary block to log file and stdout."""
    end_time = datetime.now()

    # Format times in local timezone
    start_local = run_stats.get("start_local_str", "N/A")
    end_local = end_time.strftime("%Y-%m-%d %H:%M:%S")

    elapsed = run_stats.get("execution_time_seconds", 0.0)
    if elapsed == 0.0:
        try:
            start_utc = datetime.fromisoformat(run_stats["run_time"])
            elapsed = (datetime.now(timezone.utc) - start_utc).total_seconds()
        except Exception:
            elapsed = 0.0

    errors_str = "None"
    if run_stats.get("errors"):
        errors_str = "; ".join(str(e) for e in run_stats["errors"])

    summary_text = (
        "\n"
        "============================================================\n"
        "EXECUTION SUMMARY\n"
        "============================================================\n"
        f"Start Time:        {start_local}\n"
        f"End Time:          {end_local}\n"
        f"Execution Time:    {elapsed:.1f} seconds\n"
        f"Articles Scraped:  {run_stats.get('articles_collected', 0)}\n"
        f"Relevant Articles: {run_stats.get('gemini_accepted', 0)}\n"
        f"Email Status:      {run_stats.get('email_status', 'Pending')}\n"
        f"Errors:            {errors_str}\n"
        f"Exit Code:         {exit_code}\n"
        "============================================================\n"
    )
    log.info(summary_text)


@contextmanager
def _stage_timer(label: str, stage_timings: dict):
    """Context manager that measures wall-clock time for a pipeline stage."""
    t0 = time.monotonic()
    log.info(f"[TIMER] ▶ {label} started")
    try:
        yield
    finally:
        elapsed = time.monotonic() - t0
        stage_timings[label] = round(elapsed, 2)
        log.info(f"[TIMER] ■ {label} completed in {elapsed:.1f}s")


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


def health_check() -> bool:
    """
    Verify all prerequisites before execution:
    1. Gemini API key is present
    2. Gmail credentials are present
    3. Sources config exists and is readable
    4. Connectivity to key external dependencies — checked IN PARALLEL to save time.
    """
    log.info("Running pre-flight reliability health checks...")

    # 1. Credentials Check
    if not os.environ.get("GEMINI_API_KEY"):
        raise ValueError("GEMINI_API_KEY environment variable is missing.")
    if not os.environ.get("GMAIL_USER") or not os.environ.get("GMAIL_APP_PASSWORD"):
        raise ValueError("GMAIL_USER or GMAIL_APP_PASSWORD credentials are missing.")

    # 2. Source Configuration Check
    from scraper import SOURCES_FILE
    if not SOURCES_FILE.exists():
        raise FileNotFoundError(f"Sources registry file not found at {SOURCES_FILE}")
    try:
        sources = json.loads(SOURCES_FILE.read_text(encoding="utf-8"))
        if not isinstance(sources, list) or len(sources) == 0:
            raise ValueError("Sources configuration list is empty.")
    except Exception as e:
        raise ValueError(f"Sources configuration file is corrupted or unreadable: {e}")

    # 3. Connectivity Checks for Critical Dependencies — run in parallel
    import requests
    dependencies = {
        "Gemini API Portal": "https://generativelanguage.googleapis.com",
        "Google News RSS": "https://news.google.com",
        "Glass Online": "https://www.glassonline.com",
    }

    def _check(name: str, url: str) -> str:
        try:
            resp = requests.get(url, timeout=6)
            return f"✓ {name}: Reachable (HTTP {resp.status_code})"
        except Exception as e:
            raise ConnectionError(f"Cannot connect to {name} ({url}): {e}")

    errors = []
    with ThreadPoolExecutor(max_workers=3) as pool:
        futures = {pool.submit(_check, name, url): name for name, url in dependencies.items()}
        for future in as_completed(futures):
            try:
                log.info(f"  {future.result()}")
            except Exception as e:
                errors.append(str(e))

    if errors:
        raise ConnectionError("Health check failed: " + " | ".join(errors))

    log.info("✓ Pre-flight health checks passed successfully.")
    return True


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
    """Load context keywords from keywords.json or return defaults."""
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
    Keep only articles published in the last 7 days that contain 
    at least one watchlist company or alias AND at least one context keyword.
    """
    filtered = []
    now = datetime.now(timezone.utc)
    date_limit = now - timedelta(days=7)
    
    # Compile company name and alias patterns
    company_patterns = []
    companies = watchlist.get("companies", [])
    for co in companies:
        name = co.get("name", "")
        aliases = co.get("aliases", [])
        terms = [name] + [a for a in aliases if a.strip()]
        for term in terms:
            company_patterns.append(re.compile(rf"\b{re.escape(term)}\b", re.IGNORECASE))
            
    # Compile context keywords patterns
    context_patterns = [re.compile(rf"\b{re.escape(w)}\b", re.IGNORECASE) for w in context_keywords]

    log.info(f"Applying local filter (7 days limit, {len(company_patterns)} company terms, {len(context_patterns)} context keywords)...")

    for a in articles:
        # Check publication date
        pub_str = a.get("published", "")
        if pub_str:
            try:
                pub_dt = datetime.fromisoformat(pub_str)
                if pub_dt < date_limit:
                    continue
            except Exception:
                pass
                
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


def check_timeout(start_time: datetime, run_stats: dict):
    """Gracefully terminates execution if runtime exceeds 9 minutes."""
    elapsed = (datetime.now(timezone.utc) - start_time).total_seconds()
    if elapsed > 540: # 9 minutes limit
        err_msg = f"Pipeline runtime exceeded 9 minutes limit ({elapsed:.1f}s). Gracefully exiting to prevent hard crash."
        log.error(f"✗ {err_msg}")
        run_stats["errors"].append(err_msg)
        run_stats["email_status"] = "Failed (Execution Timeout)"
        run_stats["execution_time_seconds"] = elapsed
        save_run_log(run_stats)
        write_github_summary(run_stats)
        write_log_summary(run_stats, exit_code=1)
        sys.exit(1)


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


def write_github_summary(stats: dict):
    """Write run statistics to GitHub Actions Job Summary Markdown file."""
    summary_file = os.environ.get("GITHUB_STEP_SUMMARY")
    if not summary_file:
        return
    try:
        status_emoji = "✅ SUCCESS" if stats["email_status"] == "Success" else "❌ FAILED"
        overall_result = (
            "Completed successfully." if stats["email_status"] == "Success"
            else "Failed. Check workflow logs or artifact files for details."
        )
        if stats["email_status"].startswith("Skipped"):
            status_emoji = "⚠️ SKIPPED"
            overall_result = f"Skipped: {stats['email_status']}"

        # ── Timing section ────────────────────────────────────────────────
        scheduled_raw = os.environ.get("GITHUB_RUN_CREATED_AT", "")
        start_utc     = stats.get("run_time_utc", "—")
        start_ist     = stats.get("run_time_ist", "—")
        finish_utc    = stats.get("finish_time_utc", "—")
        finish_ist    = stats.get("finish_time_ist", "—")
        email_time    = stats.get("email_sent_time", "—")
        elapsed       = stats["execution_time_seconds"]

        # Queue delay: difference between GitHub run creation and Python start
        queue_delay_str = "—"
        if scheduled_raw and stats.get("run_time_utc"):
            try:
                sched_dt = datetime.fromisoformat(scheduled_raw.replace("Z", "+00:00"))
                start_dt = datetime.fromisoformat(stats["run_time_utc"])
                queue_secs = (start_dt - sched_dt).total_seconds()
                if queue_secs >= 0:
                    queue_delay_str = f"{int(queue_secs // 60)}m {int(queue_secs % 60)}s"
                else:
                    queue_delay_str = "< 1s (instantaneous)"
            except Exception:
                pass

        # Stage timings table rows
        stage_rows = ""
        for stage, secs in stats.get("stage_timings", {}).items():
            stage_rows += f"| {stage} | `{secs:.1f}s` |\n"

        md = f"""### 📊 PGP Container Glass Market Intelligence Platform Summary

| Metric | Status / Value |
| :--- | :--- |
| **Workflow Status** | {status_emoji} |
| **Articles Found** | `{stats['articles_collected']}` |
| **Articles Sent** | `{stats['gemini_accepted']}` |
| **Execution Time** | `{elapsed:.1f} seconds` |
| **Email Status** | `{stats['email_status']}` |
| **Overall Result** | {overall_result} |

#### ⏱ Run Timing

| Event | UTC | IST |
| :--- | :--- | :--- |
| **GitHub Run Created (queue)** | `{scheduled_raw or "—"}` | — |
| **Python Script Start** | `{start_utc}` | `{start_ist}` |
| **Queue Delay** | `{queue_delay_str}` | — |
| **Email Sent** | `{email_time}` | — |
| **Script Finish** | `{finish_utc}` | `{finish_ist}` |
| **Total Script Duration** | `{elapsed:.1f}s` | — |

> ℹ️ **Queue Delay** is the gap between when GitHub created the run and when Python started.
> A large value indicates GitHub-hosted runner scheduling delay — not a code issue.
> For guaranteed 9:00 AM IST delivery, use a self-hosted runner or dedicated VPS.

#### 🔬 Per-Stage Execution Breakdown

| Stage | Duration |
| :--- | :--- |
{stage_rows}
#### 📂 Detailed Execution Statistics
* **Sources Checked**: {len(stats['sources_checked'])} active sources
* **Duplicates Prevented**: {stats['duplicates_removed']} articles
* **Gemini Approved**: {stats['gemini_accepted']} relevant developments
* **Gemini Discarded**: {stats['gemini_rejected']} irrelevant news items
"""
        if stats["errors"]:
            md += "\n#### ⚠ Errors Encountered:\n"
            for err in stats["errors"]:
                md += f"- `{err}`\n"

        Path(summary_file).write_text(md, encoding="utf-8")
        log.info("✓ Written Job Summary markdown to GITHUB_STEP_SUMMARY.")
    except Exception as e:
        log.warning(f"Failed to write GITHUB_STEP_SUMMARY: {e}")


def execute_pipeline(start_time: datetime, run_stats: dict) -> bool:
    """
    Executes a single pipeline run. Returns True on success, False on failure.
    Raises exception on severe infrastructure failures.
    Each stage is wrapped with _stage_timer() for per-step timing.
    """
    stage_timings: dict = run_stats.setdefault("stage_timings", {})

    # ── 1. Scrape (Parallel) ──────────────────────────────────────────────
    _banner("STEP 1: Scraping all sources in parallel")
    from scraper import scrape_all_sources
    with _stage_timer("Scraping", stage_timings):
        raw_articles, sources_checked = scrape_all_sources()
    run_stats["sources_checked"] = sources_checked
    run_stats["articles_collected"] = len(raw_articles)

    if not raw_articles:
        log.warning("No raw articles fetched. Skipping report generation.")
        run_stats["email_status"] = "Skipped (No News)"
        return True

    # ── 2. Local Filter ───────────────────────────────────────────────────
    check_timeout(start_time, run_stats)
    _banner("STEP 2: Applying fast local pre-filter")
    watchlist = load_watchlist()
    context_keywords = load_context_keywords()
    with _stage_timer("Local Filtering", stage_timings):
        filtered = local_pre_filter(raw_articles, watchlist, context_keywords)

    if not filtered:
        log.info("No candidate articles passed the local pre-filter. Skipping report generation.")
        run_stats["email_status"] = "Skipped (No News)"
        return True

    # ── 3. Deduplicate ────────────────────────────────────────────────────
    check_timeout(start_time, run_stats)
    _banner("STEP 3: Removing duplicate articles")
    from deduplicator import get_new_articles, update_processed_urls
    with _stage_timer("Deduplication", stage_timings):
        new_articles, cross_run_count, intra_batch_count = get_new_articles(filtered)
    run_stats["duplicates_removed"] = cross_run_count + intra_batch_count

    if not new_articles:
        log.info("All candidates already reported in previous runs. Skipping report generation.")
        run_stats["email_status"] = "Skipped (No News)"
        return True

    # ── 4. Gemini AI Analysis (with full article body fetch) ──────────────
    check_timeout(start_time, run_stats)
    _banner("STEP 4: Full article fetch + AI relevance validation and summarization")
    from gemini import analyze_article, generate_market_pulse
    from scraper import fetch_full_article
    from concurrent.futures import ThreadPoolExecutor as _TPE, as_completed as _asc
    curated_articles = []

    def _analyze_with_full_text(article: dict) -> dict | None:
        """Fetch the full article body then run Gemini analysis."""
        full_text = fetch_full_article(article["url"])
        if full_text and len(full_text) > 200:
            article["raw_text"] = full_text
            log.debug(f"    Full text fetched ({len(full_text)} chars): {article['title'][:45]}")
        else:
            log.debug(f"    Full text unavailable, using RSS/title text: {article['title'][:45]}")
        return analyze_article(article)

    log.info(f"Starting parallel full-text fetch + AI analysis of {len(new_articles)} articles...")
    with _stage_timer("Full Article Fetch + Gemini Analysis", stage_timings):
        with _TPE(max_workers=5) as executor:
            futures = {
                executor.submit(_analyze_with_full_text, article): article
                for article in new_articles
            }
            for future in _asc(futures):
                article = futures[future]
                try:
                    analysis = future.result()
                    if analysis:
                        run_stats["gemini_accepted"] += 1
                        article["company"]         = analysis.get("Company", "Unknown")
                        article["country"]         = analysis.get("Country", "Unknown")
                        article["category"]        = analysis.get("Category", "🌍 Industry Update")
                        article["summary"]         = analysis.get("Executive Summary", article["title"])
                        article["key_details"]     = analysis.get("Key Details", "")
                        article["business_impact"] = analysis.get("Business Impact", "")
                        article["priority"]        = analysis.get("Priority", "Low")
                        article["confidence"]      = analysis.get("Confidence", "High")
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
        if os.environ.get("FORCE_SEND") == "true":
            log.info("FORCE_SEND=true detected. Injecting test container glass article for validation.")
            mock_article = {
                "title": "PGP Glass Announces Capacity Expansion at Kosamba Plant",
                "url": "https://www.pgpglass.com/test-article-expansion-2026",
                "source": "PGP Glass Press Release",
                "published": datetime.now(timezone.utc).isoformat(),
                "raw_text": "PGP Glass Private Limited, a global leader in design, production, and decoration of premium glass packaging (bottles), today announced the commissioning of a new state-of-the-art furnace and expansion of container glass capacity at its Kosamba facility in Gujarat, India to meet the growing demand for perfume and cosmetics packaging.",
                "company": "PGP Glass",
                "country": "India",
                "category": "🏭 New Factory / Expansion",
                "summary": "PGP Glass has announced the expansion of container glass production capacity at its Kosamba plant in India, installing a new furnace to meet premium cosmetic and perfume packaging demands.",
                "key_details": "• Location: Kosamba, Gujarat, India\n• Product segment: Cosmetics and perfume packaging\n• Equipment: New furnace installed",
                "business_impact": "Increases capacity to serve global luxury and cosmetics packaging clients.",
                "priority": "High",
                "confidence": "High"
            }
            curated_articles.append(mock_article)
            run_stats["gemini_accepted"] += 1
        else:
            log.info("No relevant container glass developments found after AI analysis. Skipping report.")
            run_stats["email_status"] = "Skipped (No News)"
            return True

    # ── 4b. Generate Weekly Market Pulse Paragraph (Disabled as requested) ──
    market_pulse = ""

    # ── 5. Report & Email ─────────────────────────────────────────────────
    check_timeout(start_time, run_stats)
    _banner("STEP 5: Generating reports and sending email")
    from reporter import generate_report
    from email_service import send_email

    with _stage_timer("Report Generation", stage_timings):
        html_body, excel_path = generate_report(curated_articles, market_pulse)

    with _stage_timer("Email Sending", stage_timings):
        success = send_email(html_body, excel_path, len(curated_articles))

    # Record email sent time
    if success:
        run_stats["email_sent_time"] = _ts()

    # ── 6. Cleanup & Save State ────────────────────────────────────────────
    if excel_path and os.path.exists(excel_path):
        try:
            os.remove(excel_path)
            log.info(f"Deleted temp file: {excel_path}")
        except Exception as e:
            log.warning(f"Failed to delete temp Excel file: {e}")

    if success:
        log.info("✓ Email sent successfully. Updating processed_urls.json...")
        run_stats["email_status"] = "Success"
        with _stage_timer("State Save (processed_urls)", stage_timings):
            try:
                update_processed_urls(curated_articles)
            except Exception as e:
                run_stats["errors"].append(f"Updating processed URLs failed: {e}")
                log.error(f"Failed to update processed URLs: {e}")
    else:
        log.error("✗ Email delivery failed. URL history not updated.")
        run_stats["email_status"] = "Failed"
        run_stats["errors"].append("SMTP delivery failed.")

    return success


def main():
    ensure_directories()
    load_env()
    start_time = datetime.now(timezone.utc)
    start_local_str, log_filepath = setup_file_logging(start_time)

    _banner("PGP Container Glass Daily Intelligence Pipeline (Version 6.0)")
    log.info(f"  Workflow Start (UTC) : {_ts(start_time)}")
    log.info(f"  Workflow Start (IST) : {_ts(start_time, IST)}")
    log.info(f"  Scheduled cron      : 30 3 * * *  (3:30 AM UTC = 9:00 AM IST)")
    log.info(f"  GitHub Run Created  : {os.environ.get('GITHUB_RUN_CREATED_AT', 'N/A (local run)')}")
    log.info("─" * 60)

    # Standard run statistics dictionary
    run_stats = {
        "run_time": start_time.isoformat(),
        "run_time_utc": _ts(start_time),
        "run_time_ist": _ts(start_time, IST),
        "start_local_str": start_local_str,
        "execution_time_seconds": 0.0,
        "stage_timings": {},
        "sources_checked": [],
        "articles_collected": 0,
        "duplicates_removed": 0,
        "gemini_accepted": 0,
        "gemini_rejected": 0,
        "email_status": "Pending",
        "email_sent_time": "",
        "finish_time_utc": "",
        "finish_time_ist": "",
        "errors": []
    }

    try:
        # Prerequisite Health Check
        try:
            with _stage_timer("Health Check", run_stats["stage_timings"]):
                health_check()
        except Exception as e:
            err_msg = f"Pre-flight health check failed: {e}"
            log.error(f"✗ {err_msg}")
            run_stats["errors"].append(err_msg)
            run_stats["email_status"] = "Skipped (Health Check Failed)"
            run_stats["execution_time_seconds"] = (datetime.now(timezone.utc) - start_time).total_seconds()
            save_run_log(run_stats)
            write_github_summary(run_stats)
            write_log_summary(run_stats, exit_code=1)
            sys.exit(1)

        max_retries = 3
        retry_delay = 10  # Reduced from 30s — saves up to 40s across two retries
        success = False

        for attempt in range(1, max_retries + 1):
            if attempt > 1:
                log.info(f"Sleeping for {retry_delay} seconds before retry attempt {attempt}...")
                time.sleep(retry_delay)
                # Reset per-attempt statistics
                run_stats["errors"] = []
                run_stats["duplicates_removed"] = 0
                run_stats["gemini_accepted"] = 0
                run_stats["gemini_rejected"] = 0

            log.info(f"Pipeline Execution Attempt {attempt}/{max_retries}")

            try:
                success = execute_pipeline(start_time, run_stats)
                if success:
                    break
            except Exception as e:
                err_msg = f"Pipeline execution failed on attempt {attempt}: {e}"
                log.error(f"✗ {err_msg}")
                run_stats["errors"].append(err_msg)

        # ── Wrap up ───────────────────────────────────────────────────────────
        finish_time = datetime.now(timezone.utc)
        elapsed = (finish_time - start_time).total_seconds()
        run_stats["execution_time_seconds"] = elapsed
        run_stats["finish_time_utc"] = _ts(finish_time)
        run_stats["finish_time_ist"] = _ts(finish_time, IST)

        # Save statistics JSON
        save_run_log(run_stats)

        # Write GitHub Summary
        write_github_summary(run_stats)

        # ── Completion banner ──────────────────────────────────────────────────
        _banner(f"DONE — Run completed in {elapsed:.1f}s")
        log.info(f"  Script Start  (UTC) : {_ts(start_time)}")
        log.info(f"  Script Start  (IST) : {_ts(start_time, IST)}")
        log.info(f"  Script Finish (UTC) : {_ts(finish_time)}")
        log.info(f"  Script Finish (IST) : {_ts(finish_time, IST)}")
        if run_stats.get("email_sent_time"):
            log.info(f"  Email Sent    (UTC) : {run_stats['email_sent_time']}")
        log.info(f"  Total Duration      : {elapsed:.1f}s")
        log.info("─" * 60)

        exit_code = 0 if success else 1
        write_log_summary(run_stats, exit_code=exit_code)
        sys.exit(exit_code)

    except SystemExit as se:
        raise se
    except Exception as e:
        err_msg = f"Unhandled exception: {e}"
        log.exception(f"✗ {err_msg}")
        run_stats["errors"].append(err_msg)
        run_stats["email_status"] = "Failed (Unhandled Exception)"
        run_stats["execution_time_seconds"] = (datetime.now(timezone.utc) - start_time).total_seconds()
        save_run_log(run_stats)
        write_log_summary(run_stats, exit_code=1)
        sys.exit(1)


if __name__ == "__main__":
    main()
