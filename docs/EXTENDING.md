# Extending SMM-Autopilot

Most additions are a node, a prompt, and one edge, or a config change; the core does not need to be
forked.

- [Add an analysis lens](#add-an-analysis-lens)
- [Add a data source](#add-a-data-source)
- [Add an output adapter](#add-an-output-adapter)
- [Add or swap an LLM provider](#add-or-swap-an-llm-provider)
- [Re-enable compliance revision](#re-enable-compliance-revision)
- [Wire a warmed session into the scraper](#wire-a-warmed-session-into-the-scraper)
- [Tune relevance & thresholds](#tune-relevance--thresholds)
- [Test your extension](#test-your-extension)

---

## Add an analysis lens

A new lens (say, "audio/sound trends") is one node, one prompt, one edge.

1. **Prompt.** Drop `src/smm_autopilot/prompts/sound_analyzer_system.txt`. Write it concrete, and
   mark integrator-tunable parts with `# ADD: your …` comments (the house style).
2. **State.** Add the output key to `PipelineState` in
   [`models/state.py`](../src/smm_autopilot/models/state.py), e.g. `sound_report: SoundReport | None`.
3. **Node.** Add `engine/nodes/sound.py`:
   ```python
   async def sound_analyzer_node(state, *, settings, router):
       posts = state.get("filtered_posts") or []
       if not posts:
           return {"sound_report": None}        # fail soft on empty
       result = await router.call_resilient(
           LLMRole.ANALYST, SoundReport, messages, nonempty=lambda r: bool(r.items)
       )
       return {"sound_report": result}
   ```
4. **Wire it** in [`engine/graph.py`](../src/smm_autopilot/engine/graph.py): register with
   `partial(sound_analyzer_node, settings=settings, router=router)` and add one `add_edge`. If it can
   run alongside others, give it its **own** state key so the parallel write stays lock-free.
5. **Render.** Surface it in `report_node` or the Markdown renderer.

---

## Add a data source

Ingestion consumes Apify dataset ids today, but nothing forces that.

- **Another Apify actor:** add a `_*_dataset(...)` helper in
  [`engine/scrape.py`](../src/smm_autopilot/engine/scrape.py) and include it in the `asyncio.gather`,
  returning `(dataset_id, source)`. Add a matching `engagement_floor` for the new `source`.
- **A non-Apify source** (an API, a CSV, another network): produce normalized
  [`Post`](../src/smm_autopilot/models/post.py) objects and inject them into the pipeline state so the
  filter/analysis nodes pick them up. Keep the normalize step
  ([`engine/normalize.py`](../src/smm_autopilot/engine/normalize.py)) as the single shape-converter.

---

## Add an output adapter

Markdown + JSON ship today, written by `report_node` via
[`integrations/output/`](../src/smm_autopilot/integrations/output/). To add Slack/Sheets/Telegram/etc.:

1. Add a renderer in `integrations/output/your_adapter.py` that takes the `Report` model.
2. Call it from `report_node` (or add a small post-report node) behind a config/env flag so it's opt-in.

Optional adapters are gated as install extras in `pyproject.toml` (`[telegram]`, `[sheets]`), so the
core stays dependency-light.

---

## Add or swap an LLM provider

- **Any OpenAI-compatible endpoint** (OpenAI, a local Ollama, [imago.market](https://imago.market)) is
  config only, no code:
  ```yaml
  llm:
    analyst:
      primary: { provider: openai, model: your-model, base_url_env: OPENAI_BASE_URL }
  ```
  Set `OPENAI_API_KEY` (+ `OPENAI_BASE_URL`) in `.env`.
- **A brand-new SDK provider.** Add a branch to `_build_chat_model` in
  [`llm/router.py`](../src/smm_autopilot/llm/router.py) and a value to the `Provider` literal in
  [`llm/config.py`](../src/smm_autopilot/llm/config.py). Import the SDK lazily so it stays an optional
  extra.

---

## Re-enable compliance revision

The compliance gate approves or rejects each brief/idea in a single pass. Every `ComplianceResult`
already carries a `suggestion` (how to fix a rejected item), but the report doesn't consume it yet.
Wiring a "revise rejected items once, then re-check" loop in
[`engine/nodes/compliance.py`](../src/smm_autopilot/engine/nodes/compliance.py): send the failed
item back to the model with its `suggestion`, re-run the gate, and approve if it now passes. That is
a natural extension.

---

## Wire a warmed session into the scraper

By default `engine/scrape.py` passes only usernames/hashtags + result limits to the Apify actor, so
warmed-account cookies are handled on the Apify side (see [SETUP.md](SETUP.md#3-warmed-account--anti-detect-optional-but-recommended)).
To pass a session through the engine instead, extend the actor `run_input`. For example:

```python
# in _profile_dataset(...), build run_input from env:
import os, json
run_input = {"usernames": usernames, "resultsLimit": _RESULTS_LIMIT_PROFILE}
if cookies := os.environ.get("INSTAGRAM_COOKIES"):
    run_input["cookies"] = json.loads(cookies)   # shape per the actor's input schema
    run_input["proxy"] = {"useApifyProxy": True, "apifyProxyGroups": ["RESIDENTIAL"]}
```

Check the actor's input schema for the exact `cookies` and `proxy` field names. Never commit real
cookies; keep them in `.env` and treat the account as disposable.

---

## Tune relevance & thresholds

No code needed; it is all in `tenant.yaml`:

- **Too little gets through the filter?** Broaden `niche.keywords_l1/l2/l3` and `niche.hashtags`.
- **Too much noise?** Tighten the keywords and raise `thresholds.min_views_discovery` /
  `min_likes_discovery`, or the per-source `engagement_floors`.
- **Outlier ER from giveaways?** Lower `thresholds.er_cap`.
- **Report too long/short?** `top_trends_count`, `briefs_count`.

See [CONFIGURATION.md](CONFIGURATION.md#thresholds-pipeline-tunables).

---

## Test your extension

The suite is fully mocked, with no keys and no network. Follow the existing patterns in
[`tests/`](../tests/):

- Swap the router with a fake (`monkeypatch.setattr(router, "call_resilient", fake)`), as in
  `test_resilience_regressions.py`.
- For a full end-to-end check, extend the demo fixtures in `engine/demo.py` and assert on the report,
  as in `test_demo.py`.

```bash
make lint && make test     # ruff + mypy + pytest, all offline
```
