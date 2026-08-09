# project-ff

A personal agent system to run Arjun's ESPN fantasy football league — pre-draft research, draft strategy, a live draft helper, and in-season team management. See `start_prompt.md` and the [GitHub Project](https://github.com/users/arjunjalan/projects/3) for full product context and roadmap.

## Setup

```bash
cp .env.example .env   # fill in ESPN_LEAGUE_ID, ESPN_SEASON_YEAR, ESPN_S2, ESPN_SWID
uv sync
```

## Running locally

```bash
uv run uvicorn app.main:app --reload
```

- App: http://localhost:8000
- API docs: http://localhost:8000/docs

## Tests

```bash
uv run pytest
```
