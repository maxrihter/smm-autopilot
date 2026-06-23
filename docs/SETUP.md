# Live-run setup

`make demo` needs nothing. A live run scrapes real Instagram data and calls a real LLM, so it needs
three things: an Apify token, one LLM key, and, for reliable scraping of the accounts you follow, a
warmed Instagram account wired into Apify.

> **TL;DR for the engine:** it reads `APIFY_TOKEN` and your LLM key from `.env`. The warmed
> account / cookies / proxy live on the **Apify side** (the actor's session + proxy), not in the
> engine. See [Warmed account](#3-warmed-account--anti-detect-optional-but-recommended) for why and how.

---

## 1. Apify token

Apify is the one hard dependency for Instagram data; there is no self-hosted equivalent.

1. Create an account at [apify.com](https://apify.com).
2. Copy your token from **Settings → Integrations → API token**.
3. Put it in `.env`:
   ```dotenv
   APIFY_TOKEN=apify_api_xxx
   ```

The engine triggers two public actors, `apify/instagram-profile-scraper` (competitors and discovery
targets) and `apify/instagram-hashtag-scraper` (niche hashtags), defined in
[`engine/scrape.py`](../src/smm_autopilot/engine/scrape.py). They run on your Apify account, so costs
and rate limits are yours; `thresholds.max_posts_per_run` is the volume and cost backstop.

---

## 2. One LLM key

Set the key for whichever provider your tenant's `llm:` block uses (Anthropic by default):

```dotenv
ANTHROPIC_API_KEY=sk-ant-...
# or an OpenAI-compatible endpoint (OpenAI / Ollama / imago.market):
# OPENAI_API_KEY=...
# OPENAI_BASE_URL=https://...
```

Routing and provider options are documented in [CONFIGURATION.md](CONFIGURATION.md#llm-per-role-model-routing-inline).

---

## 3. Warmed account & anti-detect (optional but recommended)

Public profile/hashtag scraping often works with Apify's defaults. But Instagram increasingly gates
content behind a logged-in session, and fresh datacenter sessions get throttled fast. For **reliable,
repeatable** scraping of the creators and competitors you track, use a warmed session:

1. **Get a warmed account.** An aged account with normal activity history, not a freshly created one.
   Keep it separate from any personal or business account.
2. **Log in through an anti-detect browser** (e.g. a multi-login/anti-detect tool) over a clean
   **residential proxy**, and **follow your `discovery_targets`** so their content is reachable.
3. **Export the session cookies** from that browser profile.
4. **Attach the session to Apify**, not to the engine:
   - simplest: configure the actor's **proxy + session/cookies in the Apify console** (the Instagram
     actors accept a login session / proxy configuration in their input), or
   - keep the cookie string in `.env` as `INSTAGRAM_COOKIES` and pass it through by extending the
     actor `run_input` in `engine/scrape.py` (a few lines); see
     [EXTENDING.md](EXTENDING.md#wire-a-warmed-session-into-the-scraper).

> **Why the engine doesn't read cookies today:** `engine/scrape.py` passes only usernames/hashtags +
> result limits to the actor. Session handling is intentionally left at the Apify layer so credentials
> never flow through (or get logged by) the engine. Treat the warmed account as disposable and never
> commit its cookies.

---

## 4. Configure your tenant & run

```bash
make init                      # config/tenant.yaml from the example
$EDITOR config/tenant.yaml     # your brand, niche, region, competitors, discovery_targets
cp .env.example .env           # add APIFY_TOKEN + your LLM key
make run                       # writes output/<run_id>.md and .json
```

See [CONFIGURATION.md](CONFIGURATION.md) for every field.

---

## Cadence & cost

- Weekly is the intended rhythm; the report is a "what to do this week" briefing.
- Cost scales with `max_posts_per_run`, `top_trends_count`, `briefs_count`, and your model choice.
  Start small (low post cap, Haiku filter) and scale up once the output looks right.
- Scraped datasets are **deleted right after they're read** (in `fetch_dataset`), so you don't
  accumulate Apify storage.

---

## Troubleshooting

| Symptom | Likely cause / fix |
|---|---|
| `APIFY_TOKEN is required for a live run` | Token missing from `.env`. (Or just use `make demo`.) |
| `Config not found` | Run `make init`, or pass `--config path/to/tenant.yaml`. |
| Run aborts: "no relevant posts" | Filter found nothing on-niche; widen `niche.keywords_*` or `hashtags`, or check the accounts scraped. |
| Empty/short sections in the report | An LLM role kept returning empty; the run degrades gracefully. Check your key and the `llm:` routing. |
| Throttled / empty scrapes | Add the warmed-account session + residential proxy (step 3). |
