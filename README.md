# PGP Glass Intelligence Engine

**Production-ready Glass Industry Intelligence Automation Platform**  
Zero infrastructure · Completely free · Runs automatically every day at 8:00 AM IST

---

## What This Does

Every day at **8:00 AM IST**, GitHub Actions automatically:

1. 🔍 **Scrapes** 30+ news sources (RSS feeds + web pages) → 200–500 raw articles
2. 🏷️ **Filters** for glass industry relevance using 100+ industry keywords
3. ♻️ **Deduplicates** against previously sent URLs (no repeat articles)
4. 🏢 **Extracts** company, state, district, city from article text
5. 📂 **Classifies** into: New Factory / Expansion / Investment / Approval / Acquisition / Industry Update
6. 📝 **Summarizes** each article using free rule-based extraction (no AI API needed)
7. 📧 **Sends** a premium HTML email + Excel report to all recipients
8. 🗑️ **Deletes** all temporary files and scraped data
9. 💾 **Saves** only `processed_urls.json` to prevent future duplicates

**Cost: $0** · No server · No database · No paid APIs

---

## Quick Setup (5 Steps)

### Step 1 — Push to GitHub

```bash
cd "g:\PGP glass news automation"
git init
git add .
git commit -m "Initial commit: PGP Glass Intelligence Engine"
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/pgp-glass-intelligence.git
git push -u origin main
```

### Step 2 — Get Gmail App Password

1. Go to your Google Account → **Security**
2. Enable **2-Step Verification** (if not already enabled)
3. Go to **App Passwords**
4. Select **"Mail"** and **"Windows Computer"** → Click **Generate**
5. Copy the 16-character password (e.g., `abcd efgh ijkl mnop`)

### Step 3 — Add GitHub Secrets

Go to your GitHub repo → **Settings** → **Secrets and variables** → **Actions** → **New repository secret**

Add these 3 secrets:

| Secret Name | Value | Example |
|---|---|---|
| `GMAIL_USER` | Your Gmail address | `reports@gmail.com` |
| `GMAIL_APP_PASSWORD` | App Password from Step 2 | `abcd efgh ijkl mnop` |
| `RECIPIENTS` | Comma-separated recipient emails | `person1@email.com,person2@email.com` |

### Step 4 — Enable GitHub Actions

Go to your GitHub repo → **Actions** tab → If prompted, click **"I understand my workflows, go ahead and enable them"**

### Step 5 — Test the Pipeline

**Option A: Manual trigger (recommended first test)**
1. Go to GitHub repo → **Actions** tab
2. Click **"PGP Glass Intelligence — Daily Run"**
3. Click **"Run workflow"** → **"Run workflow"**
4. Watch the logs in real-time
5. Check your inbox in ~3–5 minutes

**Option B: Local test**
```bash
pip install -r requirements.txt

# Windows
set GMAIL_USER=your@gmail.com
set GMAIL_APP_PASSWORD=xxxx xxxx xxxx xxxx
set RECIPIENTS=you@email.com
python main.py

# Linux/Mac
GMAIL_USER=your@gmail.com GMAIL_APP_PASSWORD="xxxx xxxx xxxx xxxx" RECIPIENTS=you@email.com python main.py
```

---

## Project Structure

```
PGP glass news automation/
│
├── main.py              # Master pipeline orchestrator
├── scraper.py           # RSS + BeautifulSoup news collector
├── filter.py            # Glass keyword relevance filter
├── deduplicator.py      # URL duplicate detection
├── extractor.py         # Company / State / City extractor
├── classifier.py        # Category classifier
├── summarizer.py        # Free extractive summarizer
├── reporter.py          # HTML email + Excel generator
├── email_service.py     # Gmail SMTP sender
│
├── data/
│   ├── keywords.json    # 100+ glass industry keywords (editable)
│   ├── sources.json     # 30+ news sources (editable)
│   ├── companies.json   # Known glass companies list
│   └── india_locations.json  # States / cities / districts
│
├── processed_urls.json  # ← ONLY persisted file (auto-updated after each run)
│
├── .github/
│   └── workflows/
│       └── daily_run.yml  # GitHub Actions (8 AM IST daily)
│
├── requirements.txt
├── .env.example
└── README.md
```

---

## Customization

### Add or Remove Keywords

Edit `data/keywords.json` — add your keywords to any group:

```json
{
  "factory_plant_types": [
    "glass factory",
    "your new keyword here",
    ...
  ]
}
```

### Add or Remove Sources

Edit `data/sources.json`:

**Add a new RSS feed:**
```json
{
  "name": "My Custom Source",
  "url": "https://example.com/rss.xml",
  "tier": 2,
  "type": "rss",
  "enabled": true
}
```

**Add a new Google News query:**
```json
"google_news_queries": [
  "glass factory India",
  "your new search query"
]
```

**Disable a source (without deleting):**
```json
{
  "enabled": false
}
```

### Add or Remove Recipients

Add/change emails in GitHub Secret **`RECIPIENTS`**:
```
person1@company.com,person2@company.com,reports@pgpglass.com
```

### Add Known Companies

Edit `data/companies.json` — add company names to the list:
```json
[
  "Saint-Gobain India",
  "Your New Company Name",
  ...
]
```

---

## Report Output

### Email Report
- Premium HTML email with dark navy header
- Sections per category (New Factory, Expansion, Investment, Approval, Acquisition, Industry Update)
- Per article: Title, Company, Location, Summary, Source, Read More link
- Stats: Total articles, States covered, Companies found

### Excel Report (4 sheets)
| Sheet | Contents |
|---|---|
| All Articles | Full data: Title, Company, State, District, City, Category, Summary, Source, Date, URL |
| State Summary | State-wise breakdown of all categories |
| Category Breakdown | Count per category |
| Source Coverage | Articles found per source |

---

## Schedule

The workflow runs at **`30 2 * * *` UTC = 8:00 AM IST**.

To change the time, edit `.github/workflows/daily_run.yml`:
```yaml
- cron: '30 2 * * *'   # Change this line
```

[Cron expression reference →](https://crontab.guru/)

**IST to UTC conversion:**
- 7:00 AM IST = 1:30 AM UTC → `30 1 * * *`
- 8:00 AM IST = 2:30 AM UTC → `30 2 * * *`
- 9:00 AM IST = 3:30 AM UTC → `30 3 * * *`

---

## How Deduplication Works

`processed_urls.json` stores a SHA-256 hash of every URL that has been emailed.

- **Level 1**: Exact URL match (normalized — UTM params stripped)
- **Level 2**: URL hash comparison (fast, storage-efficient)
- **Level 3**: Title similarity ≥85% (catches reposts of same article)

The file auto-prunes to 50,000 URLs to stay lean (roughly 2+ years of daily runs).

---

## Data Privacy

- All scraped article data is processed **in memory only**
- The only file written to disk is the temporary Excel `.xlsx` file
- The Excel file is **deleted immediately** after the email is sent
- `processed_urls.json` stores only **URL hashes** (not article content)
- No database, no cloud storage, no third-party services

---

## Troubleshooting

| Problem | Solution |
|---|---|
| Gmail authentication failed | Re-generate App Password. Ensure 2FA is enabled. |
| No articles found | Check internet connection. Run manually to see logs. |
| Workflow not triggering | Check Actions tab is enabled. GitHub may delay cron by ~15 min. |
| Articles missing states | Add missing cities to `data/india_locations.json` |
| Wrong category assigned | Edit keyword rules in `classifier.py` |

---

## Requirements

- Python 3.11+
- GitHub account (free)
- Gmail account with 2FA enabled
- Internet connection (for scraping)

**Python packages** (all free, open source):
```
feedparser, beautifulsoup4, requests, lxml, openpyxl, python-dateutil
```

---

## License

Internal use — PGP Glass Pvt. Ltd.
