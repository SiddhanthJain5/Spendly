# Spec: Add Expense

## Overview
Add Expense is Step 6 of the Spendly roadmap. It replaces the `/expenses/add` stub
with a real form-driven flow that lets a logged-in user record a new expense:
amount, category, date, and an optional description. On submission the server
validates the input, inserts a row into the `expenses` table tied to the current
user, and redirects back to the profile page where the new entry immediately shows
up in the transaction history, summary stats, and category breakdown.

## Depends on
- Step 01 — Database setup (`expenses` table, `get_db`)
- Step 03 — Login / logout (session must be set; route must be protected)
- Step 04 — Profile page design (`profile.html`, `profile.css`, category badge classes)
- Step 05 — Date filter for profile page (`get_recent_expenses`, `get_expense_summary`,
  `get_expenses_by_category` already query the `expenses` table by `user_id`)

## Routes
- `GET /expenses/add` — render the add-expense form — logged-in only (redirect to `/login` if not authenticated)
- `POST /expenses/add` — validate input, insert expense, redirect to `/profile` — logged-in only

## Database changes
No schema changes. The `expenses` table already exists:
```
expenses (id, user_id, amount, category, date, description, created_at)
```
A new write helper is needed in `database/db.py`:

```python
def create_expense(user_id, amount, category, date, description):
    # INSERT INTO expenses (user_id, amount, category, date, description) VALUES (?, ?, ?, ?, ?)
```

## Templates
- **Create:** `templates/add_expense.html` — form page extending `base.html` with fields:
  Amount, Category (select, fixed list below), Date (date picker, defaults to today),
  Description (optional), Submit button, and an inline error display area
- **Modify:** `templates/base.html` — only if the navbar/quick-action link to
  `/expenses/add` is missing or points to the wrong place (verify first; likely
  already correct from Step 4 design work)

## Files to change
- `app.py` — replace the stub `GET /expenses/add` route with a two-method route
  (`GET`, `POST`) that:
  - Redirects unauthenticated users to `/login`
  - On `GET`, renders the form (date field defaults to today's ISO date)
  - On `POST`, validates and inserts via `create_expense`, then redirects to `/profile`
- `database/db.py` — add `create_expense(user_id, amount, category, date, description)`

## Files to create
- `templates/add_expense.html`
- `static/css/add_expense.css` — page-specific styles (form layout, inline errors);
  link it via `{% block head %}` the same way `landing.html` links `landing.css`

## New dependencies
No new dependencies.

## Rules for implementation
- No SQLAlchemy or ORMs — use raw `sqlite3` via `get_db()`
- Parameterised queries only — never use string formatting in SQL
- Passwords hashed with werkzeug (no auth changes in this step)
- Use CSS variables — never hardcode hex values in templates or stylesheets
- All templates extend `base.html`
- Authentication guard: check `session.get("user_id")`; if absent, `redirect(url_for("login"))`
- Use the fixed category list (must match the badge classes already used in
  `profile.html`, e.g. `cat-food`, `cat-transport`):
  `Food, Transport, Bills, Health, Entertainment, Shopping, Other`
- Server-side validation:
  - `amount` is required, must parse as a positive number (> 0)
  - `category` is required and must be one of the fixed list above
  - `date` is required and must match `YYYY-MM-DD` (reuse the `_parse_date` pattern
    already in `app.py`); reject dates in the future
  - `description` is optional, stripped of leading/trailing whitespace
- On any validation failure, re-render `add_expense.html` with the entered values
  preserved and a single inline error message — do not lose the user's input
- Always close the DB connection in `create_expense` (use `try/finally`)
- After a successful insert, redirect to `url_for("profile")` so the new expense is
  visible immediately in the existing summary/category/recent-expense panels

## Definition of done
- [ ] Visiting `/expenses/add` while logged out redirects to `/login`
- [ ] Visiting `/expenses/add` while logged in returns HTTP 200 with a form
- [ ] The Date field defaults to today's date
- [ ] The Category field offers exactly the seven fixed categories
- [ ] Submitting valid data inserts a row into `expenses` for the current user and
      redirects to `/profile`
- [ ] The newly added expense appears in the profile page's transaction history,
      summary stats, and category breakdown without a page-specific reload hack
- [ ] Submitting a non-numeric or zero/negative amount re-renders the form with a
      validation error and preserves the entered category/date/description
- [ ] Submitting an invalid or future date re-renders the form with a validation error
- [ ] Submitting an empty/unknown category re-renders the form with a validation error
- [ ] No hex colour values appear in `add_expense.html` or `add_expense.css` —
      only CSS variables
