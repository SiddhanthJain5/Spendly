# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project overview

**Spendly** — a Flask expense-tracker app, structured as a step-by-step student project. Many routes and the database layer are intentional stubs to be filled in across numbered steps.

## Commands

```bash
# Run the development server (port 5001)
venv/bin/python3 app.py

# Install dependencies
venv/bin/pip install -r requirements.txt

# Run tests
venv/bin/python3 -m pytest

# Run a single test file
venv/bin/python3 -m pytest tests/test_auth.py

# Run a single test by name
venv/bin/python3 -m pytest -k "test_login"
```

Always use the project's `venv/` — not the system Python.

## Architecture

### Entry point

`app.py` — registers all Flask routes and runs the dev server. Route stubs are marked with "coming in Step N" comments indicating which implementation step they belong to.

### Database layer (`database/db.py`)

Currently a stub. Must implement three functions:
- `get_db()` — returns a SQLite connection with `row_factory = sqlite3.Row` and `PRAGMA foreign_keys = ON`
- `init_db()` — creates all tables using `CREATE TABLE IF NOT EXISTS`
- `seed_db()` — inserts sample data for development

Auth uses **Werkzeug** (`werkzeug.security`) for password hashing — it's already in `requirements.txt`.

### Templates

All pages extend `templates/base.html`, which provides the navbar, footer, and script blocks. The landing page additionally loads `static/css/landing.css` via `{% block head %}`.

### CSS

- `static/css/style.css` — shared styles: navbar, footer, base typography, buttons
- `static/css/landing.css` — landing-page-only styles (hero, feature cards, CTA, modal)

The video modal on the landing page (`#how-modal`) is wired entirely in an inline `<script>` block at the bottom of `landing.html` — not in `main.js`.

### JavaScript

`static/js/main.js` is a placeholder. Feature JS goes here as steps are completed.

## Implementation steps (for context)

The project is built incrementally:
1. Database setup (`get_db`, `init_db`, `seed_db`)
2. Registration
3. Login / logout
4. Profile page
5–6. Expense listing / dashboard
7. Add expense
8. Edit expense
9. Delete expense
