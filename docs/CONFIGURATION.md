# Configuration

Everything that makes SMM-Autopilot yours lives in a single `config/tenant.yaml`. Nodes never read
globals or hardcoded brand/region data; they read a validated
[`Settings`](../src/smm_autopilot/config.py) object built from this file. Secrets never go in the
YAML; API keys and the Apify token come from `.env` (see [`.env.example`](../.env.example)).

```bash
make init                 # writes config/tenant.yaml from the bundled example (Barkwell)
$EDITOR config/tenant.yaml
```

The bundled example, a fictional US dog-food brand, is a complete, working reference:
[`src/smm_autopilot/templates/tenant.example.yaml`](../src/smm_autopilot/templates/tenant.example.yaml).

---

## `brand`: who you are and how you speak

| Field | Type | Notes |
|---|---|---|
| `name` | string **(required)** | Brand name; appears in the report title. |
| `region` | string | Free-form (e.g. `US`, `DACH`). Surfaces in prompts and the regional lens. |
| `content_language` | string | Language the **briefs & ideas** are written in. Default `English`. |
| `report_language` | string | Language of the **report prose**. Default `English`. |
| `positioning` | string | One paragraph: what you sell and your angle. Feeds strategy + content. |
| `audience` | string | Who you're talking to. |
| `tone` | string | Voice rules. Honored by content + compliance. |
| `ctas` | list[string] | Approved calls-to-action the content node draws from. |
| `forbidden_keywords` | list[string] | Words the brand must never use (e.g. `cure`, `guaranteed`). Enforced at compliance. |

> `content_language` ≠ `report_language` is intentional: write Spanish posts while a US manager
> reads an English summary.

---

## `niche`: what's relevant to your vertical

The relevance filter uses a **three-tier keyword model** so it can tell direct signal from noise.

| Field | Type | Notes |
|---|---|---|
| `topic_whitelist` | list[string] | Topic categories briefs/ideas are tagged with. |
| `keywords_l1` | list[string] | **Direct** niche signal (high weight). |
| `keywords_l2` | list[string] | **Adjacent** terms (medium). |
| `keywords_l3` | list[string] | **Tangential** terms (low). |
| `hashtags` | map[group → list[string]] | Discovery hashtags, grouped (e.g. `food:`, `community:`). All groups are scraped. |
| `search_queries` | list[string] | Free-text discovery queries. |

---

## `region`: events and news

| Field | Type | Notes |
|---|---|---|
| `timezone` | string | IANA tz (e.g. `America/New_York`). Default `UTC`. |
| `events` | list[Event] | Recurring/one-off moments (below). |
| `news_feeds` | list[url] | RSS feeds pulled for region-relevant news. **Leave empty to skip news.** |
| `news_keywords` | list[string] | Only news matching these surfaces. |

**Event** fields:

| Field | Type | Notes |
|---|---|---|
| `name` | string **(required)** | |
| `month` | int 1–12 **(required)** | |
| `day` | int 1–31 **(required)** | Clamped to the month's length (a Feb-29 event resolves to Feb-28 in non-leap years). |
| `relevance_tags` | list[string] | Ties the event to your topics. |
| `social_potential` | `high`/`medium`/`low` | Default `medium`. |
| `window_days` | int | How many days ahead it counts as "upcoming". Default `14`. |

---

## `competitors` & `discovery_targets`

Two lists of Instagram accounts. **Competitors** are analyzed for cadence + topics; **discovery
targets** are creators mined for viral formats and signal posts.

```yaml
competitors:
  - name: Competitor One
    instagram_url: https://www.instagram.com/competitor_one/
discovery_targets:
  - name: Creator One
    instagram_url: https://www.instagram.com/creator_one/
    note: optional free-text note
```

The handle is parsed from the URL, so query tails (`?igsh=…`) are fine.

---

## `thresholds`: pipeline tunables

Sensible defaults ship; override only what you need.

| Field | Default | Meaning |
|---|---|---|
| `max_posts_per_run` | 1500 | Hard volume/cost backstop across all sources. |
| `max_posts_after_filter` | 250 | Cap on posts entering analysis. |
| `max_post_age_days` | 90 | Posts older than this are ignored. |
| `top_trends_count` | 10 | Trends in the report. |
| `briefs_count` | 3 | Content briefs generated. |
| `min_views_discovery` | 5000 | Floor for a discovery post to count. |
| `min_likes_discovery` | 2000 | Floor for likes. |
| `viral_engagement_threshold` | 0.03 | ER above which a post is "viral". |
| `er_cap` | 0.5 | Hard cap on ER (clips giveaway/contest outliers). Must be > 0. |
| `er_norm_ceiling` | 0.1 | ER that maps to a normalized score of 1.0. Must be > 0. |
| `likes_to_reach_multiplier` | 10 | Non-Reel reach proxy = `likes × this`. Must be > 0. |
| `engagement_floors` | per-source | `source → [min_views_reels, min_likes_non_reel]`. Each must be a 2-list. |
| `default_engagement_floor` | `[20000, 1000]` | Fallback floor for unlisted sources. |

---

## `safety_blocklist`

Substrings that drop a trend outright, an early backstop before the main compliance gate.

```yaml
safety_blocklist:
  - animal cruelty
  - dog fighting
```

---

## `llm`: per-role model routing (inline)

The LLM router maps three roles to providers. There is no separate `llm.yaml`; this block lives
inside `tenant.yaml`. Each role has a `primary` and an optional `fallback`.

```yaml
llm:
  filter:                          # cheap, high-volume relevance filtering
    primary: { provider: anthropic, model: claude-haiku-4-5-20251001 }
  analyst:                         # the heavy analysis + synthesis
    primary: { provider: anthropic, model: claude-sonnet-4-6 }
    fallback: { provider: openai, model: gpt-4o-mini }   # any OpenAI-compatible endpoint
  compliance:                      # the safety/brand gate
    primary: { provider: anthropic, model: claude-sonnet-4-6 }
```

**Provider config** fields: `provider` (`anthropic`/`openai`/`mistral`/`google`), `model`,
`api_key_env` (defaults to the provider's standard var), `base_url_env` (default `OPENAI_BASE_URL`,
used only by the OpenAI-compatible provider), `max_tokens` (8192), `timeout` (120s),
`max_retries` (3).

| Provider | API-key env | Install |
|---|---|---|
| `anthropic` | `ANTHROPIC_API_KEY` | core |
| `openai` (+ any OpenAI-compatible: OpenAI, Ollama, [imago.market](https://imago.market)) | `OPENAI_API_KEY` (+ `OPENAI_BASE_URL`) | core |
| `mistral` | `MISTRAL_API_KEY` | `pip install "smm-autopilot[mistral]"` |
| `google` | `GOOGLE_API_KEY` | `pip install "smm-autopilot[google]"` |

If you set nothing, the engine defaults to Anthropic-only and auto-adds an OpenAI-compatible
analyst fallback when `OPENAI_API_KEY` is present. See
[`llm/config.py`](../src/smm_autopilot/llm/config.py).

---

## Secrets (`.env`)

Never in YAML. Copy `.env.example` → `.env` and fill what your config uses:

- `APIFY_TOKEN`: required for live runs (not for `make demo`).
- One LLM key matching your `llm:` block (e.g. `ANTHROPIC_API_KEY`).
- Storage is local SQLite (`./data/state.db`) by default; Postgres ships as an optional extra (`pip install "smm-autopilot[postgres]"`).
- Optional output adapters (Sheets, Telegram) and `LOG_LEVEL`.

See **[SETUP.md](SETUP.md)** for the live-run playbook.
