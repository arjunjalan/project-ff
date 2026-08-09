# Start Prompt — project-ff

Use this to initialize a new Claude Code session in this folder (`~/projects/project-ff`) and have it build out the project.

**You own this repo from here.** `arjunjalan/project-ff` already exists on GitHub and is cloned into this folder, but it's an empty shell — just the initial `.gitignore` commit, nothing else. Full ownership and maintenance of this repo (structure, commits, branches, whatever it needs) is yours going forward, not the vault/planning session's. Don't hold back on repo-level decisions waiting for permission — the product/technical direction below is already decided; how you implement and organize the actual repo is up to you.

---

## What This Is

A personal agent system to run Arjun's ESPN fantasy football league end to end: pre-draft research, draft strategy, a live draft helper, and in-season team management. Not a rankings tool — the actual gap it fills is **synthesis**, not data access: existing tools (FantasyPros, etc.) aggregate expert opinion, but Arjun still ends up manually reconciling 7-8 sources himself. This turns trusted inputs into Arjun's own personalized, explainable point of view — his own ADP, his own draft plan — grounded in his specific league.

It's also explicitly a dual-purpose project: a competitive edge for Arjun's league, and a hands-on vehicle for learning to build agentic applications. Arjun is a fantasy football novice, not an expert — favor transparency (show reasoning/sources) over polish.

---

## Where Things Live

| System | URL | What's there |
|---|---|---|
| This folder | `~/projects/project-ff` | Cloned from the repo below, currently empty except `.gitignore` — build starts here |
| GitHub repo | https://github.com/arjunjalan/project-ff | Code (public) |
| GitHub Project | https://github.com/users/arjunjalan/projects/3 | Public board with epics #1-#6 for horizons H1-H6. **Its README contains the full product brief, roadmap, and competitive landscape** — read it first (`gh project view 3 --owner arjunjalan` or the web URL) for full product context before writing code. |

Full technical ADRs live in Arjun's private vault and are **not** on GitHub — the key decisions from them are summarized below so this session doesn't need vault access.

---

## Key Decisions Already Made (don't re-litigate these)

- **Four independent subsystems**, not one monolithic agent — Research, Strategy, Live Draft Helper, Season Management — each matched to its own reliability needs and cadence. The live draft helper especially must stay simple and bulletproof; it runs once, live, under real time pressure.
- **Language: Python**, confirmed.
- **ESPN access**: use the open-source `espn-api` package, wrapped in a project-ff adapter that normalizes results into project-ff's own `League`/`Team`/`Player`/`DraftPick`/`Transaction` types. Don't hand-roll HTTP calls against ESPN's undocumented endpoints, and don't use browser automation/DOM scraping — both were explicitly rejected.
- **Auth**: ESPN session cookies (`espn_s2`, `SWID`), extracted manually from Arjun's browser session, stored in a **gitignored `.env`** — never commit these. This matters more than usual since the repo is public.
- **Persistence (v1)**: local JSON files (one per data type — league config, rosters, draft history, transaction history), not a database. Revisit only if H5's ongoing season-long state outgrows flat files.
- **Application architecture**: a real lightweight app — FastAPI backend + minimal frontend — not a script collection, but hosted on **localhost only** (Arjun's machine), never the cloud. A second Mac is available later as a local-network host if needed, not now.
- **Build sequencing — important**: each horizon ships its core logic first, then its own thin UI view immediately after. Never defer all UI work to one refactor at the end — this specifically protects H4 (live draft helper), which needs to be tested and familiar well before the hard deadline, not built under pressure for the first time.
- **Explainability by design**: every agent recommendation should show its reasoning and sources, not just a final answer — this serves both trust and Arjun's goal of building his own fantasy intuition.
- **Platform scope**: ESPN only for v1. Keep the data model platform-agnostic (behind the adapter) so Sleeper/Yahoo could be added later without a rewrite — but don't build that now.
- **Human-in-the-loop**: the system recommends; Arjun approves. No fully autonomous roster moves (waiver claims, trades) in v1.

---

## Timeline

- **Draft day: September 3, 2026** — hard deadline for H4 (live draft helper), no exceptions.
- Arjun wants to be actively using the system for prep **within 7 days of Aug 9, 2026** (by ~Aug 16) — meaning H1 (foundation) and H2 (research agent) effectively need to ship together in the first week, not sequentially.

---

## Open Risk — Resolve First

It's **not yet confirmed** whether ESPN's unofficial API actually retains full historical draft/transaction/standings data across a year boundary for a private league. H3 (the season retrospective) depends on this. **First task: a small spike** — authenticate with Arjun's cookies and attempt to pull last season's (2025) league data via `espn-api`. If it doesn't work, the retrospective needs a fallback (e.g., Arjun manually supplies last year's draft results) — flag that back to Arjun rather than silently dropping the feature.

---

## Suggested First Steps

1. Read the GitHub Project README (link above) for full product context.
2. Skim `arjunjalan/bookshelf` (https://github.com/arjunjalan/bookshelf) for backend conventions worth reusing — it's Arjun's other project, also FastAPI-based, and he's already familiar with its patterns. Useful to borrow: FastAPI app/router structure, coding style, testing conventions. **Don't** carry over what doesn't fit project-ff's intentionally lighter scope: no database (Bookshelf uses Postgres/Supabase + Alembic migrations, project-ff uses local JSON files per ADR 001), no Docker, no deployment tooling (Render/Vercel) — project-ff is localhost-only. Match the code style, not the infrastructure.
3. Get Arjun's ESPN league ID and season year, and have him extract `espn_s2`/`SWID` cookies.
4. Run the historical-data spike described above. Report what actually works before building the full adapter around assumptions.
5. Build H1 (issue #1): the `espn-api`-based adapter + league config/roster pull + historical data pull, plus the minimal app skeleton (FastAPI health-check endpoint, bare frontend page).
6. Check in with Arjun before moving to H2 — the 7-day target means scope for week one should be the minimum that makes the research agent (H2) genuinely usable, not the full pipeline.

Push commits to `main` as you go (per this repo's normal workflow) and keep the GitHub issues (#1-#6) updated as horizons progress — that's the active project-management muscle Arjun wants exercised from day one.
