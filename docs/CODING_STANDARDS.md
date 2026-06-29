# Coding Standards

These reflect the conventions already used in the codebase. Match the surrounding
style over any personal preference.

## Python

- **Style:** PEP 8, 4-space indent. Keep lines readable (~100 cols). The code uses
  aligned keyword arguments in a few places (e.g. the `save_prediction(...)` call) —
  fine where it aids readability.
- **Type hints:** used on public function signatures and return types
  (`-> int`, `-> list[dict]`, `str | None`). Add them to new public functions.
- **Docstrings:** triple-quoted, describing purpose, args, returns, and raised
  exceptions. Follow the existing tone (see `inference.py`, `queries.py`).
- **Logging, not print:** use a module logger
  (`logger = logging.getLogger(__name__)`). The app configures logging in `main.py`.
  Use `logger.warning` / `logger.exception` for handled failures.
- **Imports:** stdlib, then third-party, then local (`from . import ...`).
- **Comments:** explain *why*, especially for non-obvious fixes. The codebase marks
  important fixes with a leading `# FIX:` comment that explains the bug being
  prevented — keep these; they are load-bearing context (e.g. the font absolute path,
  the frame lock, the thread join).

## Error handling

- Prefer graceful degradation for side effects; fail fast for startup
  misconfiguration. See [ERROR_HANDLING.md](ERROR_HANDLING.md).
- Catch narrowly where you can; use broad `except Exception` only for genuinely
  best-effort paths (DB save in `/predict`, camera control set), and **log** it.
- Never let a persistence or annotation failure crash a prediction response.

## Database

- All SQL is **parameterized** (`?` placeholders) — never string-format user data
  into SQL.
- Open a connection per operation via `get_connection()` and close it in `finally`.
- Keep all DB access in `app/db/queries.py` / `database.py`; don't scatter SQL into
  route handlers.

## API

- Routes live on the `router` in `app/api.py`; return `JSONResponse` (or the
  appropriate response type) with explicit status codes for error cases.
- Validate/allow-list inputs (see `PUT /settings`, WebSocket controls).
- Keep response shapes stable and documented in [API_SPEC.md](API_SPEC.md); update it
  when you change them.

## Domain invariants (do not break)

- `Yellow_Bubble` → 1; everything else → 0.
- Never report more than 9 tubes; no MPN unless exactly 9.
- Internal frames are BGR; encode camera stills with PIL.

See [BUSINESS_RULES.md](BUSINESS_RULES.md).

## Frontend

- Vanilla JS, no framework or build step. Keep DOM logic in
  `static/js/script.js` and styles in `static/css/style.css`.
- Respect the existing `state` object and helper-function structure
  (`navigateTo`, `loadSettings`, `saveSettings`, etc.).
- Honor the responsive breakpoints (desktop / mobile / RPi 7" LCD) and the design
  system colors in [ARCHITECTURE.md](ARCHITECTURE.md).

## Shell scripts (Raspberry Pi)

- Target `bash`; keep them idempotent where possible (the setup script is run-once
  but safe to re-run).
- Be mindful of CRLF — the Pi setup script converts line endings; author scripts with
  LF.

## Documentation

- Update the relevant `docs/*` file and [../CHANGELOG.md](../CHANGELOG.md) in the same
  change as any behavior change.
- Use clickable relative links between docs.
