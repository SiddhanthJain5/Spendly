# Spec: Edit Expense

## Overview
Edit Expense replaces the `/expenses/<id>/edit` stub with a real form-driven flow
that lets a logged-in user update an existing expense they own: amount, category,
date, and description. The form is pre-filled with the expense's current values.
On submission the server validates the input, updates the matching row in the
`expenses` table (scoped to the current user so nobody can edit someone else's
data), and redirects back to the profile page where the change is reflected
immediately in the transaction history, summary stats, and category breakdown.

## Depends on
- Step 01 — Database setup (`expenses` table, `get_db`)
- Step 03 — Login / logout (session must be set; route must be protected)
- Step 04 — Profile page design (`profile.html`, `profile.css`, category badge classes)
- Step 05 — Date filter for profile page (existing query helpers operate on the
  `expenses` table by `user_id`)
- Step 06 — Add expense (`add_expense.html` and its form/validation pattern;
  `CATEGORIES` list and `_parse_date` helper in `app.py` are reused here)

## Routes
- `GET /expenses/<int:id>/edit` — render the edit form pre-filled with the
  expense's current values — logged-in only (redirect to `/login` if not
  authenticated; return 404 if the expense doesn't exist or doesn't belong to
  the current user)
- `POST /expenses/<int:id>/edit` — validate input, update the expense, redirect
  to `/profile` — logged-in only (same ownership check as above)

## Database changes
No schema changes. The `expenses` table already exists:
```
expenses (id, user_id, amount, category, date, description, created_at)
```
Two new helpers are needed in `database/db.py`:

```python
def get_expense_by_id(expense_id, user_id):
    # SELECT * FROM expenses WHERE id = ? AND user_id = ?
    # returns None if not found / not owned by this user

def update_expense(expense_id, user_id, amount, category, date, description):
    # UPDATE expenses SET amount = ?, category = ?, date = ?, description = ?
    # WHERE id = ? AND user_id = ?
```

## Templates
- **Create:** `templates/edit_expense.html` — form page extending `base.html`,
  modeled on `add_expense.html`, with the same fields (Amount, Category, Date,
  Description) pre-filled from the existing expense, a "Save changes" submit
  button, an inline error display area, and a "Back to profile" link
- **Modify:** `templates/profile.html` — add an edit link/icon (using the
  existing `lucide` icon set already loaded on the page, e.g. `pencil` or
  `edit-2`) to each row in the transaction table (`.txn-row`, around line 94-101)
  that points to `url_for('edit_expense', id=exp.id)`

## Files to change
- `app.py` — replace the stub `GET /expenses/<int:id>/edit` route with a
  two-method route (`GET`, `POST`) that:
  - Redirects unauthenticated users to `/login`
  - Looks up the expense via `get_expense_by_id`; returns a 404 if it doesn't
    exist or isn't owned by the current user
  - On `GET`, renders the form pre-filled with the expense's current values
  - On `POST`, validates and updates via `update_expense`, then redirects to `/profile`
- `database/db.py` — add `get_expense_by_id(expense_id, user_id)` and
  `update_expense(expense_id, user_id, amount, category, date, description)`
- `templates/profile.html` — add the per-row edit link described above
- `static/css/profile.css` — add styles for the new edit link/icon so it matches
  the existing `.txn-row` layout (using existing CSS variables)

## Files to create
- `templates/edit_expense.html`
- `static/css/edit_expense.css` — page-specific styles (form layout, inline
  errors); link it via `{% block head %}` the same way `add_expense.html` would
  link `add_expense.css` (verify whether `add_expense.html` already has its own
  stylesheet block — if the add-expense form reuses `auth-section`/`auth-card`
  styles from `style.css` with no dedicated CSS file, mirror that approach
  instead of creating a redundant stylesheet)

## New dependencies
No new dependencies.

## Rules for implementation
- No SQLAlchemy or ORMs — use raw `sqlite3` via `get_db()`
- Parameterised queries only — never use string formatting in SQL
- Passwords hashed with werkzeug (no auth changes in this step)
- Use CSS variables — never hardcode hex values
- All templates extend `base.html`
- Authentication guard: check `session.get("user_id")`; if absent,
  `redirect(url_for("login"))`
- Ownership guard: every lookup and update must filter by `user_id` so a user
  can never view or modify another user's expense; return HTTP 404 on mismatch
- Reuse the fixed category list `CATEGORIES` already defined in `app.py`:
  `Food, Transport, Bills, Health, Entertainment, Shopping, Other`
- Server-side validation (identical rules to Add Expense, reuse `_parse_date`):
  - `amount` is required, must parse as a positive number (> 0)
  - `category` is required and must be one of the fixed list above
  - `date` is required and must match `YYYY-MM-DD`; reject dates in the future
  - `description` is optional, stripped of leading/trailing whitespace
- On any validation failure, re-render `edit_expense.html` with the entered
  values preserved (not the stale DB values) and a single inline error message
- Always close the DB connection in the new helpers (use `try/finally`)
- After a successful update, redirect to `url_for("profile")` so the change is
  visible immediately in the existing summary/category/recent-expense panels

## Definition of done
- [ ] Visiting `/expenses/<id>/edit` while logged out redirects to `/login`
- [ ] Visiting `/expenses/<id>/edit` for an expense that doesn't exist, or that
      belongs to another user, returns HTTP 404
- [ ] Visiting `/expenses/<id>/edit` for your own expense returns HTTP 200 with
      a form pre-filled with that expense's amount, category, date, and description
- [ ] Submitting valid changes updates the row in `expenses` and redirects to `/profile`
- [ ] The updated expense reflects the new values immediately in the profile
      page's transaction history, summary stats, and category breakdown
- [ ] Submitting a non-numeric or zero/negative amount re-renders the form with
      a validation error and preserves the entered values (not the old DB values)
- [ ] Submitting an invalid or future date re-renders the form with a validation error
- [ ] Submitting an empty/unknown category re-renders the form with a validation error
- [ ] An edit link/icon is visible on each row of the transaction table on `/profile`
      and navigates to the correct `/expenses/<id>/edit` URL
- [ ] No hex colour values appear in any new or modified template/stylesheet —
      only CSS variables
