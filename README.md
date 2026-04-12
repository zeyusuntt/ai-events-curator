# 🤖 AI Events Curator — South Bay & SF

An automated Luma event scraper and curator for AI/LLM engineers in the South Bay Area.

## What It Does

- **Scrapes Luma** twice a week (Tuesday & Friday at 9 AM PT) for new AI events
- **Filters** by location (South Bay / San Francisco), AI relevance, and quality
- **Scores** events using GPT-4.1-mini for relevance to AI/LLM engineers
- **Deploys** updated results automatically to GitHub Pages (free, permanent URL)

## Priority Criteria

| Priority | Criteria |
|----------|----------|
| 🔴 High | Stanford-hosted events (Stanford AI Club, StartX, etc.) |
| 🔴 High | Hackathons with AI/ML focus |
| 🔴 High | Top company/VC events (OpenAI, NVIDIA, Sequoia, a16z, etc.) |
| 🟡 Medium | General AI meetups, workshops, networking in South Bay/SF |

## Monitored Luma Calendars

- [Bond AI — SF & Bay Area](https://lu.ma/genai-sf) — most active AI community
- [Stanford AI Club](https://lu.ma/stanfordaiclub)
- [StartX & Friends](https://lu.ma/StartX)
- [Intuit Open Source Meetup](https://lu.ma/intuit-open-source-meetup)

## Setup Instructions

### 1. Fork / Clone this repo

```bash
git clone https://github.com/YOUR_USERNAME/ai-events-curator.git
cd ai-events-curator
```

### 2. Add your OpenAI API key as a GitHub Secret

Go to: **Settings → Secrets and variables → Actions → New repository secret**

- Name: `OPENAI_API_KEY`
- Value: your OpenAI API key (used for LLM-based event scoring)

### 3. Enable GitHub Pages

Go to: **Settings → Pages**
- Source: **Deploy from a branch**
- Branch: `gh-pages` / `/ (root)`

Your site will be live at: `https://YOUR_USERNAME.github.io/ai-events-curator/`

### 4. Enable GitHub Actions

The workflow runs automatically on schedule. You can also trigger it manually:
**Actions → Update AI Events → Run workflow**

## Local Development

```bash
# Install dependencies
pip install requests beautifulsoup4 openai python-dateutil

# Run scraper locally
export OPENAI_API_KEY=your_key_here
python scripts/scrape_luma.py

# Preview site locally
cd site && python -m http.server 8080
```

## File Structure

```
├── scripts/
│   └── scrape_luma.py          # Main scraper + LLM filter
├── site/
│   ├── index.html              # Interactive event dashboard
│   ├── events_data.js          # Auto-updated event data (JSON)
│   └── .github/
│       └── workflows/
│           └── update-events.yml  # GitHub Actions schedule
├── README.md
└── seen_events.json            # Cache to avoid re-processing
```

## Schedule

| Day | Time | Action |
|-----|------|--------|
| Tuesday | 9:00 AM PT | Scrape + update + deploy |
| Friday | 9:00 AM PT | Scrape + update + deploy |

## Cost

- **GitHub Pages**: Free (unlimited for public repos)
- **GitHub Actions**: Free (2,000 min/month for public repos; this job uses ~5 min/run = ~40 min/month)
- **OpenAI API**: ~$0.01–0.05 per run (GPT-4.1-mini is very cheap)
