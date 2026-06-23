# SMM-Autopilot — Project Rules

Generalized, open-source growth-intelligence engine. Extracted and generalized from a
private production system — **no client data, names, or secrets ever belong in this repo.**

## Conventions
- Python 3.11+, full type hints, `async def` for all I/O.
- Pydantic v2 models in `models/`; one LangGraph node per file in `engine/nodes/`.
- Prompts live in `src/smm_autopilot/prompts/*.txt` — concrete, with `# ADD: your …`
  bullets marking what an integrator customizes. Never hardcode brand / region / vertical.
- All tunables (brand, competitors, niche, events, safety, LLM, pipeline) live in
  `config/*.yaml`, never in source.
- Secrets only via env (`.env`, see `.env.example`); never commit real values.
- LLM access goes through `llm/router.py` (provider-agnostic) — no vendor hardcoding.

## Layout
- `src/smm_autopilot/` — engine, nodes, integrations, models, llm router, storage, cli
- `src/smm_autopilot/prompts/` — system prompts (`.txt`, shipped in the wheel)
- `src/smm_autopilot/templates/` — bundled example tenant (a fictional brand)
- `src/smm_autopilot/engine/demo.py` — hermetic, no-keys demo runner
- `config/` — where `init` scaffolds your tenant config
- `docs/` — SETUP · CONFIGURATION · EXTENDING · ARCHITECTURE
- `tests/` — mocked unit tests (no API keys needed)
