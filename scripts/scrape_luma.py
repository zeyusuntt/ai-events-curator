#!/usr/bin/env python3
"""
Luma AI Events Scraper & Curator
Runs twice a week (Tue + Fri) to discover new AI/LLM events on Luma
matching the user's criteria (South Bay / SF, Stanford priority, hackathons,
startup/VC sessions) and updates the static site's events_data.js.

Works both locally and inside GitHub Actions.
"""

import os
import re
import json
import time
import logging
import hashlib
from datetime import datetime, date
from dateutil import parser as dateparser
from typing import Optional

import requests
from bs4 import BeautifulSoup
from openai import OpenAI

# ─── Paths (relative to repo root, works in GitHub Actions) ──────────────────
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT   = os.path.dirname(SCRIPT_DIR)
SITE_DIR    = os.path.join(REPO_ROOT, "site")
DATA_FILE   = os.path.join(SITE_DIR, "events_data.js")
CACHE_FILE  = os.path.join(SCRIPT_DIR, "seen_events.json")
LOG_FILE    = os.path.join(REPO_ROOT, "scrape.log")

# ─── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger(__name__)

# ─── Config ───────────────────────────────────────────────────────────────────

# Luma calendar slugs to monitor
LUMA_CALENDARS = [
    "genai-sf",                   # Bond AI — SF & Bay Area (most active)
    "stanfordaiclub",             # Stanford AI Club
    "StartX",                     # StartX & Friends (Stanford accelerator)
    "intuit-open-source-meetup",  # Intuit / Mountain View tech
]

# Luma search queries
LUMA_SEARCHES = [
    "Stanford AI",
    "AI hackathon Bay Area",
    "LLM San Jose",
    "AI startup Palo Alto",
    "machine learning Mountain View",
    "AI agents Sunnyvale",
    "GenAI Menlo Park",
    "AI meetup South Bay",
]

# South Bay cities
SOUTH_BAY_CITIES = [
    "san jose", "mountain view", "sunnyvale", "palo alto", "menlo park",
    "santa clara", "cupertino", "los altos", "atherton", "redwood city",
    "stanford", "east palo alto", "campbell", "milpitas",
]

SF_CITIES = ["san francisco", "sf,", "soma", "mission district"]

# AI relevance keywords
AI_KEYWORDS = [
    "ai", "llm", "machine learning", "deep learning", "neural", "gpt",
    "openai", "anthropic", "gemini", "claude", "llama", "mistral",
    "generative", "genai", "agentic", "agent", "rag", "vector",
    "transformer", "diffusion", "multimodal", "nlp", " ml,", "ml ",
    "huggingface", "langchain", "pytorch", "tensorflow", "vllm",
    "inference", "fine-tun", "embedding", "foundation model",
    "hackathon", "founder", "vc ", "venture capital", "startup",
]

# Disqualifying keywords
DISQUALIFY_KEYWORDS = [
    "yoga", "meditation", "cooking", "dance", "fitness", "wedding",
    "real estate", "crypto", "nft", "blockchain", "forex", "trading",
    "religion", "church", "spiritual", "dating", "speed dating",
]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

# ─── Helpers ──────────────────────────────────────────────────────────────────

def load_seen_events() -> dict:
    if os.path.exists(CACHE_FILE):
        with open(CACHE_FILE) as f:
            return json.load(f)
    return {}


def save_seen_events(seen: dict):
    with open(CACHE_FILE, "w") as f:
        json.dump(seen, f, indent=2)


def event_id(url: str) -> str:
    return hashlib.md5(url.encode()).hexdigest()[:12]


def fetch_page(url: str, retries: int = 3) -> Optional[str]:
    for attempt in range(retries):
        try:
            resp = requests.get(url, headers=HEADERS, timeout=15)
            if resp.status_code == 200:
                return resp.text
            log.warning(f"HTTP {resp.status_code} for {url}")
        except Exception as e:
            log.warning(f"Attempt {attempt+1} failed for {url}: {e}")
        time.sleep(2 ** attempt)
    return None


def is_south_bay(location: str) -> bool:
    loc = location.lower()
    return any(city in loc for city in SOUTH_BAY_CITIES)


def is_sf(location: str) -> bool:
    loc = location.lower()
    return any(city in loc for city in SF_CITIES)


def is_relevant_area(location: str) -> bool:
    return is_south_bay(location) or is_sf(location)


def is_ai_relevant(text: str) -> bool:
    t = text.lower()
    if any(kw in t for kw in DISQUALIFY_KEYWORDS):
        return False
    return any(kw in t for kw in AI_KEYWORDS)


def is_future_event(date_str: str) -> bool:
    try:
        d = dateparser.parse(date_str, fuzzy=True)
        if d:
            return d.date() >= date.today()
    except Exception:
        pass
    return True  # keep if we can't parse


def extract_iso_date(date_str: str) -> str:
    try:
        d = dateparser.parse(date_str, fuzzy=True)
        if d:
            return d.strftime("%Y-%m-%d")
    except Exception:
        pass
    return str(date.today())


# ─── Luma Scrapers ────────────────────────────────────────────────────────────

def scrape_luma_calendar(slug: str) -> set:
    url = f"https://lu.ma/{slug}"
    log.info(f"Scraping calendar: {url}")
    html = fetch_page(url)
    if not html:
        return set()

    soup = BeautifulSoup(html, "html.parser")
    event_links = set()
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if re.match(r'^/[a-z0-9][a-z0-9\-]{3,}$', href):
            event_links.add("https://lu.ma" + href)
        elif re.match(r'^https://lu\.ma/[a-z0-9][a-z0-9\-]{3,}$', href):
            event_links.add(href)

    log.info(f"  Found {len(event_links)} links in {slug}")
    return event_links


def scrape_luma_search(query: str) -> set:
    url = f"https://lu.ma/search?q={requests.utils.quote(query)}"
    log.info(f"Searching: {query}")
    html = fetch_page(url)
    if not html:
        return set()

    soup = BeautifulSoup(html, "html.parser")
    links = set()
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if re.match(r'^/[a-z0-9]{6,}$', href):
            links.add("https://lu.ma" + href)
        elif re.match(r'^https://lu\.ma/[a-z0-9]{6,}$', href):
            links.add(href)
    log.info(f"  Found {len(links)} links for '{query}'")
    return links


def scrape_event_detail(url: str) -> Optional[dict]:
    html = fetch_page(url)
    if not html:
        return None

    soup = BeautifulSoup(html, "html.parser")

    # Try JSON-LD structured data first
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string)
            if isinstance(data, list):
                data = data[0]
            if data.get("@type") in ("Event", "SocialEvent"):
                loc_obj = data.get("location", {})
                addr = loc_obj.get("address", {})
                location = " ".join(filter(None, [
                    loc_obj.get("name", ""),
                    addr.get("addressLocality", ""),
                    addr.get("addressRegion", ""),
                ])).strip()
                return {
                    "title": data.get("name", ""),
                    "date_raw": data.get("startDate", ""),
                    "location": location,
                    "description": data.get("description", ""),
                    "url": url,
                    "organizer": data.get("organizer", {}).get("name", "") if isinstance(data.get("organizer"), dict) else "",
                    "attendees": None,
                }
        except Exception:
            pass

    # Fallback: HTML parsing
    title_el = soup.find("h1")
    title = title_el.get_text(strip=True) if title_el else ""
    if not title:
        return None

    date_raw = ""
    for el in soup.find_all(["time", "span", "div"]):
        txt = el.get_text(strip=True)
        if re.search(r'\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\b', txt) and len(txt) < 80:
            date_raw = txt
            break

    location = ""
    for el in soup.find_all(["span", "div", "p"]):
        txt = el.get_text(strip=True)
        if any(city.title() in txt for city in SOUTH_BAY_CITIES + ["San Francisco"]) and len(txt) < 120:
            location = txt
            break

    desc = ""
    for el in soup.find_all(["p", "div"]):
        txt = el.get_text(strip=True)
        if len(txt) > 100:
            desc = txt[:600]
            break

    attendees = None
    for el in soup.find_all(string=re.compile(r'\d+\s+Going', re.I)):
        m = re.search(r'(\d+)\s+Going', str(el), re.I)
        if m:
            attendees = int(m.group(1))
            break

    return {
        "title": title,
        "date_raw": date_raw,
        "location": location,
        "description": desc,
        "url": url,
        "organizer": "",
        "attendees": attendees,
    }


# ─── LLM Scoring ─────────────────────────────────────────────────────────────

def score_event_with_llm(event: dict) -> Optional[dict]:
    """Score and enrich an event using GPT-4.1-mini."""
    client = OpenAI()

    prompt = f"""You are helping an AI/LLM software engineer in the South Bay Area (San Jose, Mountain View, Sunnyvale, Palo Alto, Menlo Park) find relevant events on Luma.

The engineer wants:
1. Stanford-hosted AI events (HIGHEST priority — Stanford AI Club, StartX, Stanford faculty talks)
2. Hackathons with AI/ML focus in South Bay or SF
3. Startup/VC/company-hosted AI talks, meetups, networking (South Bay preferred, SF acceptable)
4. Job/hiring events in AI
5. Technical AI talks (LLM, agents, RAG, inference, fine-tuning, multimodal)

Event details:
Title: {event.get('title', '')}
Date: {event.get('date_raw', '')}
Location: {event.get('location', '')}
Host/Organizer: {event.get('organizer', '')}
Description: {event.get('description', '')[:700]}
URL: {event.get('url', '')}

Respond with ONLY a raw JSON object (no markdown fences) with these exact fields:
{{
  "relevant": true/false,
  "priority": "High" | "Medium" | "Low",
  "priority_score": 1-10,
  "type": "<one of: Hackathon | Speaker Series | Conference / Summit | Tech Meetup | Tech Talk | Hiring Event | Job Fair / Networking | VC / Research Networking | Workshop | Startup Pitch / Fireside Chat | Pitch Competition | Founders & Builders Night | Startup Networking | Tech Networking | Networking / Happy Hour | Lecture / Panel>",
  "tags": ["array", "of", "tags"],
  "area": "South Bay" | "San Francisco" | "Other",
  "why_attend": "One sentence why an AI/LLM engineer should attend",
  "cost": "Free" | "$XX" | "Paid",
  "status": "Open" | "Waitlist" | "Approval Required",
  "date_display": "Mon, Apr 14",
  "time_display": "5:00 PM – 8:00 PM PDT",
  "reason_skip": "reason if not relevant"
}}

Tags to choose from: Stanford, Hackathon, LLM, AI Agents, RAG, VC, Startup, AI Startup, Hiring, NVIDIA, OpenAI, Google, Meta, HuggingFace, Multimodal AI, AI Infrastructure, South Bay, San Francisco, Networking, Workshop, Speaker Series, AI Research, Frontier AI

Mark relevant=false if: not AI-related, outside Bay Area, past event, or low-signal social event."""

    try:
        client_obj = OpenAI()
        resp = client_obj.chat.completions.create(
            model="gpt-4.1-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
            max_tokens=500,
        )
        raw = resp.choices[0].message.content.strip()
        raw = re.sub(r'^```(?:json)?\s*', '', raw)
        raw = re.sub(r'\s*```$', '', raw)
        return json.loads(raw)
    except Exception as e:
        log.warning(f"LLM scoring failed for {event.get('url', '')}: {e}")
        return None


# ─── Pipeline ─────────────────────────────────────────────────────────────────

def collect_event_urls() -> set:
    urls = set()

    for slug in LUMA_CALENDARS:
        urls.update(scrape_luma_calendar(slug))
        time.sleep(1.5)

    for query in LUMA_SEARCHES:
        urls.update(scrape_luma_search(query))
        time.sleep(1.5)

    # Always include the user's original high-quality example events
    pinned = {
        "https://luma.com/vllhjgoh",
        "https://luma.com/cccdyj4k",
        "https://luma.com/ip1wjj8i",
        "https://luma.com/72sd6k37",
        "https://luma.com/btrvfgdh",
        "https://luma.com/8fvs6pnw",
        "https://luma.com/fceysyuy",
        "https://luma.com/beelieve",
        "https://luma.com/genaisummit26",
    }
    urls.update(pinned)

    # Filter out calendar/profile/utility pages
    skip_slugs = set(LUMA_CALENDARS) | {
        "discover", "search", "pricing", "help", "blog",
        "terms", "privacy", "about", "login", "signup",
    }
    event_urls = set()
    for url in urls:
        slug = url.rstrip("/").split("/")[-1].split("?")[0]
        if slug not in skip_slugs and not slug.startswith("user"):
            event_urls.add(url)

    log.info(f"Total candidate URLs: {len(event_urls)}")
    return event_urls


def run_pipeline() -> list:
    seen = load_seen_events()
    new_events = []
    skipped = irrelevant = 0

    candidate_urls = collect_event_urls()
    log.info(f"Processing {len(candidate_urls)} candidates...")

    for url in sorted(candidate_urls):
        eid = event_id(url)

        # Skip recently cached events (< 3 days old)
        if eid in seen:
            try:
                days_ago = (date.today() - dateparser.parse(seen[eid]["last_seen"]).date()).days
                if days_ago < 3:
                    skipped += 1
                    continue
            except Exception:
                pass

        # Skip very short slugs (likely not event pages)
        slug = url.rstrip("/").split("/")[-1].split("?")[0]
        if len(slug) < 5:
            continue

        detail = scrape_event_detail(url)
        if not detail or not detail.get("title"):
            continue

        combined = f"{detail['title']} {detail['description']} {detail['location']}"

        # Quick pre-filter
        if not is_ai_relevant(combined):
            irrelevant += 1
            seen[eid] = {"url": url, "last_seen": str(date.today()), "status": "irrelevant"}
            continue

        if not is_future_event(detail.get("date_raw", "")):
            seen[eid] = {"url": url, "last_seen": str(date.today()), "status": "past"}
            continue

        # LLM scoring
        scored = score_event_with_llm(detail)
        if not scored or not scored.get("relevant"):
            reason = scored.get("reason_skip", "Not relevant") if scored else "LLM error"
            log.info(f"  SKIP: {detail['title'][:55]} — {reason}")
            irrelevant += 1
            seen[eid] = {"url": url, "last_seen": str(date.today()), "status": "irrelevant"}
            continue

        record = {
            "id": eid,
            "title": detail["title"],
            "date": extract_iso_date(detail.get("date_raw", "")),
            "dateDisplay": scored.get("date_display", ""),
            "time": scored.get("time_display", ""),
            "location": detail["location"] or "See Luma for details",
            "area": scored.get("area", "Other"),
            "host": detail.get("organizer", ""),
            "type": scored.get("type", "Tech Meetup"),
            "tags": scored.get("tags", []),
            "priority": scored.get("priority", "Medium"),
            "priorityScore": scored.get("priority_score", 5),
            "description": (detail["description"] or "")[:400],
            "url": url,
            "attendees": detail.get("attendees"),
            "status": scored.get("status", "Open"),
            "whyAttend": scored.get("why_attend", ""),
            "cost": scored.get("cost", "Free"),
        }
        new_events.append(record)
        seen[eid] = {"url": url, "last_seen": str(date.today()), "status": "included", "title": detail["title"][:55]}
        log.info(f"  ✓ [{scored.get('priority')}] {detail['title'][:55]}")
        time.sleep(0.5)

    save_seen_events(seen)
    log.info(f"Done: {len(new_events)} new, {skipped} cached-skip, {irrelevant} filtered")
    return new_events


# ─── Merge & Write ────────────────────────────────────────────────────────────

def load_existing_events() -> list:
    if not os.path.exists(DATA_FILE):
        return []
    with open(DATA_FILE) as f:
        content = f.read()
    m = re.search(r'const eventsData\s*=\s*(\[.*?\]);', content, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1))
        except Exception as e:
            log.warning(f"Could not parse existing events: {e}")
    return []


def merge_events(existing: list, new_events: list) -> list:
    today = date.today()

    # Drop past events
    kept = []
    for ev in existing:
        try:
            d = dateparser.parse(ev.get("date", ""), fuzzy=True)
            if d and d.date() >= today:
                kept.append(ev)
        except Exception:
            kept.append(ev)

    existing_ids  = {str(ev.get("id", "")) for ev in kept}
    existing_urls = {ev.get("url", "") for ev in kept}

    added = 0
    for ev in new_events:
        if str(ev.get("id", "")) not in existing_ids and ev.get("url", "") not in existing_urls:
            kept.append(ev)
            added += 1

    kept.sort(key=lambda e: dateparser.parse(e.get("date", "9999-12-31"), fuzzy=True) or datetime.max)
    log.info(f"Merged: {len(kept)} total ({added} new added)")
    return kept


def write_events_js(events: list):
    now = datetime.now().strftime("%Y-%m-%d %H:%M PDT")
    stats = {
        "total": len(events),
        "stanfordEvents": sum(1 for e in events if "Stanford" in e.get("tags", [])),
        "hackathons": sum(1 for e in events if e.get("type") == "Hackathon"),
        "southBay": sum(1 for e in events if e.get("area") == "South Bay"),
        "hiringEvents": sum(1 for e in events if "Hiring" in e.get("tags", [])),
        "freeEvents": sum(1 for e in events if e.get("cost") == "Free"),
        "lastUpdated": now,
    }
    content = f"""// Auto-generated by Luma AI Events Scraper
// Last updated: {now}
// Schedule: Tuesday & Friday 9:00 AM PT

const eventsData = {json.dumps(events, indent=2, ensure_ascii=False)};

const eventStats = {json.dumps(stats, indent=2)};
"""
    os.makedirs(SITE_DIR, exist_ok=True)
    with open(DATA_FILE, "w") as f:
        f.write(content)
    log.info(f"Written {len(events)} events → {DATA_FILE}")


# ─── Entry Point ─────────────────────────────────────────────────────────────

def main():
    log.info("=" * 60)
    log.info(f"Luma Scraper — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    log.info("=" * 60)

    new_events = run_pipeline()
    existing   = load_existing_events()
    merged     = merge_events(existing, new_events)
    write_events_js(merged)

    log.info(f"✅ Complete — {len(merged)} events in site.")
    return len(merged)


if __name__ == "__main__":
    main()
