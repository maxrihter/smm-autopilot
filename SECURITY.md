# Security Policy

## Reporting a vulnerability

Please **do not** open a public issue for security problems.

Use GitHub's private vulnerability reporting on this repo: the **Security** tab →
**Report a vulnerability** (or open a [draft advisory](https://github.com/maxrihter/smm-autopilot/security/advisories/new)).
I'll respond as soon as I can.

## Handling secrets

This tool talks to third-party services with your credentials, so keep them safe:

- API keys (`APIFY_TOKEN`, your LLM provider key) and any Instagram session live in `.env`, which is
  git-ignored. Never commit real secrets; `.env.example` ships only empty placeholders.
- Treat any warmed Instagram account as disposable, and never commit its cookies.
- Scraped data is stored locally (SQLite) and Apify datasets are deleted after each read.

## Supported versions

This is a pre-1.0 project; security fixes land on `main`.
