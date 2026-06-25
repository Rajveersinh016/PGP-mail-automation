"""
gemini.py — PGP Container Glass Intelligence Platform
AI analysis module using Gemini 2.5 Flash.
Handles relevance filtering, company/country extraction, categorization,
and business impact analysis.
"""

import json
import logging
import os
import time
import requests

log = logging.getLogger(__name__)

GEMINI_API_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent"

PROMPT_TEMPLATE = """You are a Senior Market Intelligence Director specializing in the global Container Glass Industry.
Analyze the article only from the perspective of the container glass ecosystem.

We are interested in developments that have a direct or indirect business impact on:
- Container glass manufacturers (e.g. O-I, Verallia, Ardagh, BA Glass, Vidrala, Vetropack, Stoelzle, HNG, Piramal)
- Luxury perfume & cosmetic packaging or premium alcoholic beverage glass packaging
- IS machines, glass furnaces, inspection equipment, and plant expansions
- Glass bottle demand, capacity changes, and M&A

Reject general glass, architecture/float glass, automotive, solar glass, consumer glassware, or unrelated manufacturing.

Article Title: {title}
Article Source: {source}
Article URL: {url}
Article Text: {raw_text}

You MUST return a JSON object in this exact format:
{{
  "relevance": "RELEVANT" or "NOT RELEVANT",
  "company": "Main company name from the article, or 'Unknown'",
  "country": "Detected country of the development, or 'Unknown'",
  "category": "Must be exactly one of: 🏭 New Container Glass Factory, 🏗 Plant Expansion, 🔥 Furnace Rebuild, ⚙ Machinery & Equipment, 🤝 Customer Partnership, 💰 Investment, 🌱 Sustainability, 🍾 Beverage Industry, 🌸 Luxury Packaging, 📦 Container Glass Packaging, 🔬 Technology, 🌍 Industry Update",
  "summary": "Executive summary of the news, max 120 words. Focus on business facts.",
  "business_impact": "1-2 sentence business impact on the industry or the company"
}}
"""

def analyze_article(article: dict) -> dict | None:
    """
    Call Gemini 2.5 Flash to analyze a single article.
    Returns the parsed JSON response, or None if failed or marked not relevant.
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

    url = f"{GEMINI_API_URL}?key={api_key}"
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "responseMimeType": "application/json"
        }
    }
    headers = {"Content-Type": "application/json"}

    for attempt in range(3):
        try:
            resp = requests.post(url, json=payload, headers=headers, timeout=25)
            if resp.status_code == 429:
                log.warning("Gemini API rate limited (429). Retrying in 4 seconds...")
                time.sleep(4)
                continue

            resp.raise_for_status()
            result = resp.json()
            text = result["candidates"][0]["content"]["parts"][0]["text"]
            
            analysis = json.loads(text)
            if analysis.get("relevance", "NOT RELEVANT").upper() == "RELEVANT":
                return analysis
            return None # Discard if AI marks not relevant

        except Exception as e:
            log.warning(f"Gemini analysis attempt {attempt+1} failed: {e}")
            time.sleep(1.5)

    return None
