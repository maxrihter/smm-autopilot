# Contributing to SMM-Autopilot

Thanks for your interest. Issues and PRs are welcome, whether it's a bug, a new analysis lens, a
data source, or an output adapter.

## Development setup

```bash
git clone https://github.com/maxrihter/smm-autopilot && cd smm-autopilot
make install      # uv sync --extra dev
make demo         # full pipeline on fixtures; no keys, no network
make test         # 51 mocked tests, offline
```

You'll need [uv](https://github.com/astral-sh/uv) and Python 3.11+. Nothing else for development;
the test suite and demo run without any keys.

## Project structure

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the node-by-node design, and
[docs/EXTENDING.md](docs/EXTENDING.md) for the extension seams (lens / source / output / provider).

## Code style

- **Python 3.11+, full type hints.** `async def` for all I/O.
- **Linted + typed.** `make lint` (ruff + mypy) and `make fmt` (ruff format) must be clean.
- **No hardcoded brand / region / vertical.** Everything tunable lives in `tenant.yaml`; prompts use
  `# ADD: your …` bullets to mark what an integrator customizes.
- **No secrets, ever.** Keys and cookies come from `.env`; never commit real values, and never commit
  client data or a real brand's strategy.
- **One node per file** in `engine/nodes/`; one Pydantic model group per file in `models/`.
- **Read before you edit.** Match the surrounding style.

## Pull requests

1. Branch from `main`.
2. Make your change; add or extend a test (the suite is fully mocked; see `tests/`).
3. Ensure `make lint && make test` pass, and `make demo` still runs if you touched the engine.
4. Write a clear PR description explaining the **why**. The template has a checklist.

## Reporting issues

Use [GitHub Issues](../../issues) with the provided templates: Bug Report or Feature Request.

## Security

If you find a security vulnerability, please report it privately to the maintainer instead of opening
a public issue.

## License

By contributing, you agree your contributions are licensed under the [MIT License](LICENSE).
