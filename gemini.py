"""
gemini.py — PGP Container Glass Intelligence Platform
AI analysis module using Gemini 2.5 Flash.
Handles relevance filtering, company/country extraction, categorization,
business impact analysis, priority scoring, confidence rating, and Market Pulse generation.
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

Reject general glass, flat/architecture glass, automotive, solar glass, consumer glassware, or unrelated manufacturing.

Article Title: {title}
Article Source: {source}
Article URL: {url}
Article Text: {raw_text}

You MUST return a JSON object in this exact format:
{{
  "is_relevant": true or false,
  "Company": "Main company name from the article, or 'Unknown'",
  "Country": "Detected country of the development, or 'Unknown'",
  "Category": "Must be exactly one of: 🏭 New Container Glass Factory, 🏗 Plant Expansion, 🔥 Furnace Rebuild, ⚙ Machinery & Equipment, 🤝 Customer Partnership, 💰 Investment, 🌱 Sustainability, 🍾 Beverage Industry, 🌸 Luxury Packaging, 📦 Container Glass Packaging, 🔬 Technology, 🌍 Industry Update",
  "Summary": "Executive summary of the news, max 120 words. Focus on business facts.",
  "Business Impact": "1-2 sentence business impact on the industry or the company",
  "Priority": "Must be exactly one of: High, Medium, Low (High = plant builds, furnace fires, M&A; Medium = partnerships, tech updates; Low = generic news)",
  "Confidence": "Must be exactly one of: High, Medium, Low (How confident are you that this is container-glass industry related)"
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
            # Check relevance boolean
            if analysis.get("is_relevant") is True:
                return analysis
            return None # Discard if AI marks not relevant

        except Exception as e:
            log.warning(f"Gemini analysis attempt {attempt+1} failed: {e}")
            time.sleep(1.5)

    return None


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
    
    prompt = f"""You are a Senior Market Intelligence Director.
Generate a concise, professional executive paragraph (Market Pulse) summarizing today's container glass developments.
Provide a high-level strategic overview of these updates. Keep it strictly to one cohesive paragraph (max 150 words).
Focus on trends, capital investment, or significant industry moves.

Today's articles:
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
            resp = requests.post(url, json=payload, headers=headers, timeout=25)
            if resp.status_code == 429:
                time.sleep(4)
                continue
            resp.raise_for_status()
            result = resp.json()
            pulse = result["candidates"][0]["content"]["parts"][0]["text"]
            return pulse.strip()
        except Exception as e:
            log.warning(f"Failed to generate Market Pulse (attempt {attempt+1}): {e}")
            time.sleep(1.5)
            
    return "Error compiling today's Market Pulse summary."
