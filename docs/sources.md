# APIx Sources & Compliance Audit (`docs/sources.md`)

This document details the source evaluation, `robots.txt` compliance audit, active scrapers, and fallback strategies for restricted OTA platforms.

---

## 1. Compliance Policy & Audit Framework

APIx adheres strictly to ethical web scraping standards:
1. **Robots.txt Pre-flight Check**: Before executing any search job, the scraper fetches and parses `https://<domain>/robots.txt`. If the path is disallowed, the source job is skipped.
2. **Rate-Limiting & Throttling**: Domain rate limiting with randomized delay gaps (2.0s to 5.0s) prevents request bursts.
3. **Bot Identification**: User-Agent string explicitly identifies the scraper with contact details:
   `APIx-AirfareBot/1.0 (+https://apix.example.com/bot; bot@apix.example.com)`
4. **CAPTCHA Backoff**: CAPTCHA and Cloudflare challenge pages trigger an immediate backoff and mark the source as paused for the current run.

---

## 2. Airline & OTA Evaluation Audit Matrix

| Source Identifier | Source Name | Category | Status | Robots.txt Result | Notes / Strategy |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `indigo` | IndiGo Airlines (6E) | Airline | **Active** | Permitted | Network API interception + DOM fallback |
| `airindia` | Air India (AI) | Airline | **Active** | Permitted | Direct flight search API interception |
| `airindiaexpress` | Air India Express (IX) | Airline | **Active** | Permitted | Direct booking fare response capture |
| `akasa` | Akasa Air (QP) | Airline | **Active** | Permitted | Search result JSON parsing |
| `spicejet` | SpiceJet (SG) | Airline | **Active** | Permitted | Fare list extraction |
| `easemytrip` | EaseMyTrip | OTA | **Active** | Permitted | Search results allowed; itemized fare capture |
| `yatra` | Yatra | OTA | **Active** | Permitted | Flight search results allowed |
| `cleartrip` | Cleartrip | OTA | **Active** | Permitted | Search results allowed |
| `makemytrip` | MakeMyTrip | OTA | *Skipped* | Disallowed | `Disallow: /search*` in `robots.txt` & Akamai Bot Manager |
| `ixigo` | Ixigo | OTA | *Skipped* | Disallowed | `Disallow: /flights/search*` & Cloudflare Turnstile |
| `goibibo` | Goibibo | OTA | *Skipped* | Disallowed | `Disallow: /flights/*` in `robots.txt` |

---

## 3. Fallbacks for Skipped OTAs

For platforms where automated scraping is restricted by `robots.txt` or aggressive bot challenges (MakeMyTrip, Ixigo, Goibibo):
- **Primary Fallback**: Licensed GDS / NDC API Integration (e.g., Amadeus Air Shopping API, Travelport Enterprise NDC).
- **Secondary Fallback**: Historical cached fare dataset ingestion via standard APIx batch ingestion format.
