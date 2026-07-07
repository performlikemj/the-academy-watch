# Backend — Flask patterns & gotchas

- Run: `cd academy-watch-backend && python src/main.py` (port 5001). Venv lives
  at repo root: `.loan/` (`../.loan/bin/python` from the backend dir).
- The prod image is **python:3.11-slim** while CI lints on 3.12 — code and every
  dependency must stay 3.11-compatible (this is why numpy is pinned <2.5).
- **Blueprint registration order in `src/main.py` matters**: `players_bp` is
  registered before `api_bp` so `/players/*` routes win conflicts. When adding a
  blueprint, check for path overlap before picking a registration position.
- Ruff config is `academy-watch-backend/pyproject.toml` (py312, line-length 120,
  `E/F/I/UP/B/SIM` with a deliberate ignore list). The ignores are policy, not
  debt to clean: don't mass-"fix" bare excepts, SIM readability rules, etc.
- Sharp edge: `ruff check --fix` (run by the edit hook) deletes unused imports.
  Add an import and its first usage **in the same edit**, or the autofixer strips
  it before you use it.
- Admin endpoints authenticate via `ADMIN_API_KEY` bearer token. Public
  submission endpoints use Flask-Limiter rate limits + `bleach` sanitization —
  follow that pattern for any new public write endpoint.
- Team ID → name/logo resolution: `resolve_team_name_and_logo()` in
  `src/routes/api.py`, caching to `TeamProfile`. Don't re-implement.
- Environment: `env.template` lists the variables. Before concluding a credential
  isn't configured, **read the actual `.env`** — grepping the source tree lies.
- Newsletter emails embed images as base64 — newsletters rows are large by
  design; don't "fix" that without checking the email-delivery path.
- `api_cache` is purged daily by pg_cron in prod; don't build a second purge.
- Timing/size debugging: when data "isn't showing", time the API call AND check
  payload size — oversized/slow responses can prevent rendering even when the
  data is correct (see `docs/agents/debugging.md`).
