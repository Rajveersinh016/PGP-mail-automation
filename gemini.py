"""
gemini.py — PGP Container Glass Intelligence Platform
AI analysis module using Gemini 2.5 Flash.
Version 5.2: Dual-section output (Executive Summary + Key Details), quality
validation with one retry, full-article context, and improved prompt.
"""

import json
import logging
import os
import re
import time
import requests

log = logging.getLogger(__name__)

GEMINI_API_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent"

PROMPT_TEMPLATE = """You are a Senior Container Glass Market Intelligence Analyst.

Your role is to analyze industry news and produce structured executive intelligence for the global container glass sector.

We monitor developments that directly or indirectly impact:
- Container glass manufacturers (O-I, Verallia, Ardagh, BA Glass, Vidrala, Vetropack, Stoelzle, HNG, Piramal, Owens Corning, etc.)
- Luxury perfume, cosmetic and premium alcoholic beverage glass packaging
- IS machines, glass furnaces, inspection equipment, and plant expansions
- Glass bottle demand, capacity changes, investment, sustainability, and M&A

REJECT: general flat glass, architectural glass, automotive glass, solar glass, consumer glassware, or unrelated manufacturing.

---

Article Title: {title}
Article Source: {source}
Article URL: {url}

Article Text:
{raw_text}

---

INSTRUCTIONS:

1. Read the ENTIRE article text above before generating any output.
2. Do NOT summarize paragraph by paragraph. Understand the complete context first.
3. Generate a JSON response in EXACTLY the format below.

EXECUTIVE SUMMARY rules:
- Maximum 80 words. Count carefully.
- Completely rewrite in your own words. Do NOT copy any sentence from the article.
- Focus only on the single most important business outcome.
- No background information. No repetition of company history.
- Write as if briefing a CEO who has 20 seconds to read.

KEY DETAILS rules:
- Write ONLY as concise bullet points starting with •
- Each bullet must introduce NEW information NOT mentioned in the Executive Summary.
- Do NOT repeat or paraphrase anything from the Executive Summary.
- Include any available: investment values, production capacity, plant location, countries, companies, customers, equipment suppliers, technology, furnace details, sustainability initiatives, product launches, expansion plans, key dates, important numbers, strategic announcements.
- If a fact is in the Executive Summary, it MUST NOT appear in Key Details.

BUSINESS IMPACT rules:
- 1-2 sentences specific to the container glass industry.
- Describe the commercial or operational significance.

Return ONLY a valid JSON object with no markdown, no code fences, no extra text:
{{
  "is_relevant": true or false,
  "Company": "Main company name from the article, or 'Unknown'",
  "Country": "Country of the primary development, or 'Unknown'",
  "Category": "Must be exactly one of: 🏭 New Container Glass Factory, 🏗 Plant Expansion, 🔥 Furnace Rebuild, ⚙ Machinery & Equipment, 🤝 Customer Partnership, 💰 Investment, 🌱 Sustainability, 🍾 Beverage Industry, 🌸 Luxury Packaging, 📦 Container Glass Packaging, 🔬 Technology, 🌍 Industry Update",
  "Executive Summary": "Max 80 words. Original rewrite. Most important business outcome only.",
  "Key Details": "• Bullet point 1\\n• Bullet point 2\\n• Bullet point 3",
  "Business Impact": "1-2 sentence business impact specific to container glass industry.",
  "Priority": "Must be exactly one of: High, Medium, Low",
  "Confidence": "Must be exactly one of: High, Medium, Low"
}}

Priority guide: High = new plant, furnace fire/rebuild, M&A, major investment; Medium = partnerships, tech updates, sustainability programs; Low = generic news.
Confidence guide: High = clearly container glass; Medium = likely relevant; Low = uncertain.
"""

RETRY_PROMPT_SUFFIX = """

IMPORTANT CORRECTION REQUIRED:
Your previous response failed quality validation. Please fix the following:
- Executive Summary must be 80 words or fewer. Count every word.
- Key Details must contain ONLY bullet points (• prefix) with NEW facts not already in the Executive Summary.
- Do NOT repeat any sentence or fact between Executive Summary and Key Details.
- Return ONLY the JSON object.
"""


def _count_words(text: str) -> int:
    """Count words in a string."""
    return len(text.split()) if text.strip() else 0


def _validate_output(analysis: dict) -> tuple[bool, str]:
    """
    Validate Gemini output quality.

    Checks:
    1. Executive Summary is ≤ 80 words.
    2. Key Details is non-empty and contains at least one bullet (•).
    3. No sentence from Executive Summary appears verbatim in Key Details.

    Returns (is_valid, reason).
    """
    summary = analysis.get("Executive Summary", "")
    key_details = analysis.get("Key Details", "")

    # Check 1: word count
    word_count = _count_words(summary)
    if word_count > 80:
        return False, f"Executive Summary is {word_count} words (max 80)"

    # Check 2: Key Details must have bullets
    if not key_details or "•" not in key_details:
        return False, "Key Details is empty or missing bullet points (•)"

    # Check 3: No verbatim sentence overlap
    summary_sentences = [s.strip().lower() for s in re.split(r'[.!?]+', summary) if len(s.strip()) > 20]
    details_lower = key_details.lower()
    for sentence in summary_sentences:
        # Check for substantial overlap (80%+ of words matching)
        words = sentence.split()
        if len(words) >= 5:
            # Use a sliding window: if 5+ consecutive words from summary appear in details, flag it
            for i in range(len(words) - 4):
                chunk = " ".join(words[i:i+5])
                if chunk in details_lower:
                    return False, f"Sentence fragment repeated between Executive Summary and Key Details: '{chunk}'"

    return True, "OK"


import threading

gemini_lock = threading.Lock()
last_call_time = 0.0

def _call_gemini(prompt: str, api_key: str, timeout: int = 30) -> dict | None:
    """
    Make a single Gemini API call. Returns parsed JSON dict or None on failure.
    Includes thread-safe client-side rate limiting to stay under 15 RPM.
    """
    global last_call_time
    url = f"{GEMINI_API_URL}?key={api_key}"
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "responseMimeType": "application/json"
        }
    }
    headers = {"Content-Type": "application/json"}

    for attempt in range(5):
        # Client-side rate limiting (max 10 requests per minute, spacing calls by >= 6.0 seconds)
        with gemini_lock:
            now = time.time()
            elapsed = now - last_call_time
            if elapsed < 6.0:
                time.sleep(6.0 - elapsed)
            last_call_time = time.time()

        try:
            resp = requests.post(url, json=payload, headers=headers, timeout=timeout)
            if resp.status_code == 429:
                import random
                sleep_time = 15 + random.uniform(2.0, 6.0)
                log.warning(f"Gemini API rate limited (429). Retrying in {sleep_time:.1f} seconds (attempt {attempt+1}/5)...")
                time.sleep(sleep_time)
                continue

            resp.raise_for_status()
            result = resp.json()
            text = result["candidates"][0]["content"]["parts"][0]["text"]
            return json.loads(text)

        except json.JSONDecodeError as e:
            log.warning(f"Gemini JSON parse error on attempt {attempt+1}: {e}")
            time.sleep(2.0)
        except Exception as e:
            log.warning(f"Gemini API call attempt {attempt+1} failed: {e}")
            time.sleep(2.0)

    return None


def analyze_article(article: dict) -> dict | None:
    """
    Call Gemini 2.5 Flash to analyze a single article.

    Returns the parsed and validated JSON response (with Executive Summary +
    Key Details), or None if the article is not relevant or analysis failed.
    """
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        log.error("GEMINI_API_KEY environment variable is missing. Cannot perform AI analysis.")
        raise ValueError("GEMINI_API_KEY is not set.")

    prompt = PROMPT_TEMPLATE.format(
        title=article.get("title", ""),
        source=article.get("source", ""),
        url=article.get("url", ""),
        raw_text=article.get("raw_text", "")
    )

    # First attempt
    analysis = _call_gemini(prompt, api_key)
    if analysis is None:
        return None

    if analysis.get("is_relevant") is not True:
        return None

    # Quality validation
    is_valid, reason = _validate_output(analysis)

    if not is_valid:
        log.warning(f"Gemini output failed quality validation: {reason}. Retrying once...")
        retry_prompt = prompt + RETRY_PROMPT_SUFFIX
        retry_analysis = _call_gemini(retry_prompt, api_key)

        if retry_analysis is not None and retry_analysis.get("is_relevant") is True:
            retry_valid, retry_reason = _validate_output(retry_analysis)
            if retry_valid:
                log.info("Retry produced valid output.")
                return retry_analysis
            else:
                log.warning(f"Retry also failed validation ({retry_reason}). Accepting original result.")
                return analysis  # Accept original rather than discard
        else:
            # Retry failed entirely or marked not relevant — return original
            return analysis

    return analysis


def generate_market_pulse(articles: list[dict]) -> str:
    """
    Generate a cohesive daily market pulse summary (1 paragraph, max 150 words)
    describing today's global container glass industry news from all curated articles.
    """
    if not articles:
        return "No significant container glass developments reported today."

    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        return "Market Pulse generation skipped: GEMINI_API_KEY missing."

    summaries = []
    for i, a in enumerate(articles, 1):
        summaries.append(
            f"{i}. [{a.get('company', 'Unknown')} in {a.get('country', 'Unknown')}] "
            f"Category: {a.get('category', 'General')}. Summary: {a.get('summary', '')}"
        )

    text_content = "\n".join(summaries)

    prompt = f"""You are a Senior Container Glass Market Intelligence Analyst.
Generate a concise, professional executive paragraph (Market Pulse) summarizing today's container glass industry developments.
Write a high-level strategic overview of the key themes, capital movements, and industry signals.
Keep it strictly to one cohesive paragraph (max 150 words). No bullet points.
Focus on trends, capital investment, geographic movements, or significant strategic industry shifts.

Today's curated developments:
{text_content}
"""

    url = f"{GEMINI_API_URL}?key={api_key}"
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "responseMimeType": "text/plain"
        }
    }
    headers = {"Content-Type": "application/json"}

    for attempt in range(3):
        try:
            resp = requests.post(url, json=payload, headers=headers, timeout=30)
            if resp.status_code == 429:
                time.sleep(5)
                continue
            resp.raise_for_status()
            result = resp.json()
            pulse = result["candidates"][0]["content"]["parts"][0]["text"]
            return pulse.strip()
        except Exception as e:
            log.warning(f"Failed to generate Market Pulse (attempt {attempt+1}): {e}")
            time.sleep(1.5)

    return "Error compiling today's Market Pulse summary."
