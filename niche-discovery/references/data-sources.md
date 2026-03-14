# Data Sources Reference

All 21 data sources used by the `niche-discovery` skill.

---

## Source Summary Table

| # | Source | Script | Auth Env Var(s) | Rate Limit | Monthly Budget | Signal Quality |
|---|--------|--------|-----------------|------------|----------------|----------------|
| 1 | Google Autocomplete | `autocomplete.py` | None | Unlimited (use 0.5s delays) | $0 | Medium |
| 2 | Google SERP + PAA | `serp.py` | `GOOGLE_CSE_KEY` + `GOOGLE_CSE_CX` | 100 req/day | $0 (free tier) | High |
| 3 | Google SERP (fallback) | `serp.py` | `SERPAPI_KEY` | 250 req/mo (first month) | $0 | High |
| 4 | Google SERP (fallback) | `serp.py` | `SERPER_KEY` | 2,500 one-time free credits | $0 | High |
| 5 | Google Trends | `trends.py` | None (pytrends) | ~10 req/min | $0 | Medium |
| 6 | Reddit | `reddit.py` | Optional: `REDDIT_CLIENT_ID`, `REDDIT_CLIENT_SECRET`, `REDDIT_USERNAME`, `REDDIT_PASSWORD` | 10 req/min anon, 60 req/min OAuth | $0 | High |
| 7 | YouTube Comments | `youtube_comments.py` | `YOUTUBE_API_KEY` | 10,000 quota units/day | $0 | Medium |
| 8 | YouTube Transcripts | `youtube_transcripts.py` | Optional `YOUTUBE_API_KEY` (for search) | Moderate (use 1s delays) | $0 | Medium |
| 9 | Google Play Store | `playstore.py` | None (google-play-scraper) | Can get 503 with aggressive use | $0 | High |
| 10 | Stack Overflow | `stackoverflow.py` | Optional `STACKEXCHANGE_KEY` | 10,000 req/day with key, 300/day without | $0 | High |
| 11 | GitHub Issues | `github_issues.py` | Optional `GITHUB_TOKEN` | 5,000 req/hr with token, 60/hr without | $0 | High |
| 12 | WordPress.org Plugins | `wordpress.py` | None | Generous (use 1s delays for review scraping) | $0 | Medium |
| 13 | Hacker News | `hackernews.py` | None (Algolia API) | Generous (use 0.5s delays) | $0 | Medium |
| 14 | Ubersuggest CPC | `cpc.py` | Optional `UBERSUGGEST_COOKIE` | 3 free lookups/day | $0 | Medium |
| 15 | G2 Reviews | `apify_scrape.py --actor g2` | `APIFY_TOKEN` | $5/mo credit | ~$2-3/run | High |
| 16 | Trustpilot Reviews | `apify_scrape.py --actor trustpilot` | `APIFY_TOKEN` | $5/mo credit | ~$1/run | High |
| 17 | Amazon Reviews | `apify_scrape.py --actor amazon` | `APIFY_TOKEN` | $5/mo credit | ~$1/run | High |
| 18 | Meta Ad Library | `apify_scrape.py --actor meta-ads` | `APIFY_TOKEN` | $5/mo credit | ~$0.50/run | Medium |
| 19 | AlternativeTo | `scraperapi_scrape.py --target alternativeto` | `SCRAPERAPI_KEY` | 1,000 req/mo | ~500 req | High |
| 20 | Shopify App Store | `scraperapi_scrape.py --target shopify` | `SCRAPERAPI_KEY` | 1,000 req/mo | ~300 req | Medium |
| 21 | Chrome Web Store | `scraperapi_scrape.py --target chromewebstore` | `SCRAPERAPI_KEY` | 1,000 req/mo | ~200 req | Medium |

---

## Detailed Source Documentation

### 1. Google Autocomplete
- **Endpoint:** `https://suggestqueries.google.com/complete/search?client=firefox&q={query}`
- **Response format:** `[query, [suggestion1, suggestion2, ...], ...]`
- **Auth:** None required
- **Rate limit:** Technically unlimited, but be reasonable. 0.5s delay between requests.
- **What it returns:** Search suggestion strings for any query prefix
- **Best for:** Understanding how people phrase their problems, finding variation keywords

### 2. Google SERP + People Also Ask
- **Provider 1: Google Custom Search Engine (CSE)**
  - Endpoint: `https://www.googleapis.com/customsearch/v1?key={KEY}&cx={CX}&q={query}&num=10`
  - Free tier: 100 queries/day
  - Setup: [Google Cloud Console](https://console.cloud.google.com/) → Custom Search API
  - Env vars: `GOOGLE_CSE_KEY` (API key), `GOOGLE_CSE_CX` (search engine ID)
- **Provider 2: SerpAPI**
  - Endpoint: `https://serpapi.com/search?api_key={KEY}&q={query}`
  - Free tier: 250 searches/month (first month only, then paid)
  - Signup: [serpapi.com](https://serpapi.com)
  - Env var: `SERPAPI_KEY`
- **Provider 3: Serper.dev**
  - Endpoint: `https://google.serper.dev/search` (POST with JSON body)
  - Header: `X-API-KEY: {KEY}`
  - Free tier: 2,500 one-time free credits (no expiry)
  - Signup: [serper.dev](https://serper.dev)
  - Env var: `SERPER_KEY`

### 3. Google Trends
- **Library:** `pytrends` (unofficial Python wrapper for Google Trends)
- **Install:** `pip install pytrends`
- **Rate limit:** ~10 requests/minute. Gets temporarily blocked (HTTP 429) with aggressive use.
  - Add 2s delays between calls
  - If blocked, wait 60s before retrying
- **What it returns:**
  - Interest over time (0-100 index, 12 months)
  - Related queries (rising and top)
  - Related topics
- **Trend direction:** Computed by comparing first-quarter vs last-quarter average interest

### 4. Reddit
- **Search endpoint:** `https://www.reddit.com/search.json?q={query}&sort=relevance&limit=100`
- **Subreddit search:** `https://www.reddit.com/r/{sub}/search.json?q={query}&restrict_sr=on`
- **OAuth token endpoint:** `https://www.reddit.com/api/v1/access_token`
- **Auth:**
  - Anonymous: 10 req/min, set a descriptive User-Agent (required)
  - OAuth: 60 req/min — create an app at [reddit.com/prefs/apps](https://www.reddit.com/prefs/apps)
  - Env vars: `REDDIT_CLIENT_ID`, `REDDIT_CLIENT_SECRET`, `REDDIT_USERNAME`, `REDDIT_PASSWORD`
- **User-Agent format required:** `niche-discovery/1.0 (by /u/yourusername)`

### 5. YouTube Data API v3
- **Search:** `https://www.googleapis.com/youtube/v3/search?part=snippet&q={query}&type=video&key={KEY}`
- **Comments:** `https://www.googleapis.com/youtube/v3/commentThreads?part=snippet&videoId={ID}&key={KEY}&maxResults=100`
- **Quota costs:**
  - Search: 100 units
  - CommentThreads: 1 unit per request
  - Default daily quota: 10,000 units → 100 searches OR 10,000 comment pages
- **Setup:** [Google Cloud Console](https://console.cloud.google.com/) → YouTube Data API v3
- **Env var:** `YOUTUBE_API_KEY`

### 6. YouTube Transcripts
- **Library:** `youtube-transcript-api`
- **Install:** `pip install youtube-transcript-api`
- **Auth:** None (uses YouTube's public transcript endpoint)
- **Rate limit:** Moderate — use 1s delays. Can get IP-blocked with aggressive use.
- **Limitations:** Only works for videos with auto-generated or manual subtitles in English

### 7. Google Play Store
- **Library:** `google-play-scraper`
- **Install:** `pip install google-play-scraper`
- **Auth:** None
- **Rate limit:** Can return 503 with no delay. Use `sleep_milliseconds=200` in `reviews()` call.
- **Filtering:** Fetch ratings 1-3 for complaint mining (4-5 for positive signal)

### 8. Stack Exchange API
- **Base URL:** `https://api.stackexchange.com/2.3`
- **Search endpoint:** `GET /search/advanced?q={query}&site={site}&sort=votes&order=desc`
- **Sites:** `stackoverflow`, `softwareengineering`, `ux`, `superuser`, `askubuntu`
- **Auth:**
  - No key: 300 requests/day
  - With key: 10,000 requests/day
  - Register at: [stackapps.com](https://stackapps.com)
- **Env var:** `STACKEXCHANGE_KEY`
- **Backoff:** API returns a `backoff` field when throttled — respect it

### 9. GitHub REST API
- **Search issues:** `GET https://api.github.com/search/issues?q={query}+type:issue+state:open`
- **Sort by reactions:** `&sort=reactions&order=desc`
- **Auth:**
  - No token: 60 req/hr
  - With token: 5,000 req/hr
  - Create at: [github.com/settings/tokens](https://github.com/settings/tokens) (no scopes needed for public data)
- **Env var:** `GITHUB_TOKEN`

### 10. WordPress.org Plugins
- **Plugin search API:** `https://api.wordpress.org/plugins/info/1.2/?action=query_plugins&search={keyword}`
- **Response:** JSON with `plugins` array
- **Review scraping:** HTML scrape of `https://wordpress.org/support/plugin/{slug}/reviews/?filter={1-5}`
- **Requires:** `beautifulsoup4` for HTML parsing
- **Auth:** None
- **Rate limit:** Generous for API; use 1s delays for HTML scraping

### 11. Hacker News (Algolia API)
- **Stories:** `https://hn.algolia.com/api/v1/search?query={q}&tags=story`
- **Ask HN:** `https://hn.algolia.com/api/v1/search?query={q}&tags=ask_hn`
- **Comments:** `https://hn.algolia.com/api/v1/search?query={q}&tags=comment`
- **Auth:** None (Algolia free public endpoint)
- **Rate limit:** Generous. Use 0.5s delays to be polite.

### 12. Ubersuggest (CPC/Volume)
- **URL:** `https://app.neilpatel.com/api/suggest`
- **Free tier:** 3 lookups/day (without account)
- **Auth:** Optional `Cookie` header from a logged-in session
- **Env var:** `UBERSUGGEST_COOKIE`
- **Fallback:** Heuristic estimate based on autocomplete suggestion count

### 13. Apify Platform
- **Base URL:** `https://api.apify.com/v2`
- **Run actor:** `POST /acts/{actor_id}/runs?token={TOKEN}`
- **Poll run:** `GET /actor-runs/{run_id}?token={TOKEN}`
- **Fetch results:** `GET /datasets/{dataset_id}/items?token={TOKEN}`
- **Auth:** `APIFY_TOKEN` — get at [apify.com](https://apify.com)
- **Free tier:** $5/month credit
- **Actor discovery:** Search [apify.com/store](https://apify.com/store) for current actor IDs

### 14. ScraperAPI
- **Proxy URL:** `http://api.scraperapi.com?api_key={KEY}&url={TARGET}`
- **JavaScript rendering:** Add `&render=true` parameter
- **Auth:** `SCRAPERAPI_KEY` — get at [scraperapi.com](https://scraperapi.com)
- **Free tier:** 1,000 requests/month (5 concurrent max)
- **Use case:** Bypasses Cloudflare and bot protection on AlternativeTo, Shopify App Store, Chrome Web Store

---

## Environment Variable Quick Reference

```bash
# SERP (use at least one)
GOOGLE_CSE_KEY=AIza...
GOOGLE_CSE_CX=017...
SERPAPI_KEY=...
SERPER_KEY=...

# Reddit (optional, increases rate limit 6x)
REDDIT_CLIENT_ID=...
REDDIT_CLIENT_SECRET=...
REDDIT_USERNAME=...
REDDIT_PASSWORD=...

# YouTube
YOUTUBE_API_KEY=AIza...

# Stack Exchange
STACKEXCHANGE_KEY=...        # Optional

# GitHub
GITHUB_TOKEN=ghp_...         # Optional

# Budget-gated
APIFY_TOKEN=apify_api_...
SCRAPERAPI_KEY=...
UBERSUGGEST_COOKIE=...       # Optional
```
