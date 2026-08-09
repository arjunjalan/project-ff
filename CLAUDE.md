# CLAUDE.md — project-ff

Architectural brief for every Claude Code session in this repo. Read `start_prompt.md` for full product/roadmap context first if this is a new session.

---

## What This Is

A personal agent system to run Arjun's ESPN fantasy football league end to end: pre-draft research, draft strategy, a live draft helper, and in-season team management. The gap it fills is synthesis, not data access — turning trusted inputs into Arjun's own explainable point of view, grounded in his specific league.

---

## Stack

| Layer | Technology |
|---|---|
| Backend | FastAPI (Python 3.12), managed with `uv` |
| Persistence | Local JSON files under `data/` (gitignored) — no database for v1 |
| Frontend | Plain HTML/JS served as static files by FastAPI — no build tooling until a horizon actually needs it |
| ESPN access | `espn-api` package via `app/adapters/espn.py` — never call ESPN's undocumented endpoints directly, never browser-automate |
| Auth | ESPN session cookies (`espn_s2`, `SWID`) in a gitignored `.env` |
| Hosting | Localhost only — never cloud |

---

## Project Structure

```
project-ff/
├── app/
│   ├── routers/     # FastAPI route handlers — thin, no business logic
│   ├── services/     # Business logic (orchestrates adapters + storage)
│   ├── adapters/      # External provider wrappers (EspnAdapter normalizes espn-api → our models)
│   ├── models/         # Pydantic domain models (League, Team, Player, DraftPick, Transaction) — also the persistence shape
│   ├── storage/         # JsonStore — local JSON read/write
│   ├── config.py         # pydantic-settings Settings, reads .env
│   ├── dependencies.py    # FastAPI DI wiring (adapter + store → service)
│   └── main.py             # FastAPI app entry point
├── frontend/          # Static HTML/JS, served at "/"
├── scripts/            # One-off spikes/scripts, not part of the app
├── tests/
└── data/                # gitignored — synced league JSON lives here
```

---

## Architecture Principles

1. **Adapter-first** — all ESPN access sits behind `EspnAdapter`. Routers/services never touch `espn_api` directly.
2. **Models double as persistence shape** — no separate ORM layer, so Pydantic models in `app/models/` are both the API contract and what gets written to JSON. Split them only if/when that stops being true.
3. **Four independent subsystems** (Research, Strategy, Live Draft Helper, Season Management), not one monolithic agent — each matched to its own reliability needs. The live draft helper especially must stay simple and bulletproof.
4. **Secrets in env vars only** — nothing sensitive committed; this matters more than usual since the repo is public.
5. **Explainability by design** — recommendations should surface reasoning/sources, not just a final answer.
6. **Human-in-the-loop** — the system recommends, Arjun approves. No autonomous roster moves in v1.
7. **Phase-appropriate complexity** — build only what the current horizon needs.
8. **Ship UI alongside logic, per horizon** — never defer all UI to a refactor at the end (this specifically protects H4, which needs to be familiar well before draft day).

---

## Conventions

- Python `logging`, no print statements
- `pyproject.toml` / `uv` for dependency management
- Pytest for tests; prefer fakes (`SimpleNamespace`) over hitting the live ESPN API in unit tests
- Push commits to `main` directly for this repo (single-user, low blast radius) — no worktree/PR ceremony unless a change is large enough to want review

---

## Known Constraints

- **ESPN transaction history (adds/drops/trades) is not reliably queryable for past seasons** — confirmed via `scripts/spike_historical_data.py` (see issue #1 comment). Draft, roster, and standings history all work fine. H3's retrospective should lean on those, not on transaction-level history, unless this gets re-verified.

---

## Navigation

- Product brief, roadmap, competitive landscape: GitHub Project README — `gh project view 3 --owner arjunjalan`
- GitHub issues (epics per horizon): https://github.com/arjunjalan/project-ff/issues
- Original kickoff doc: `start_prompt.md`
