# Spec: Date Filter for Profile Page

## Overview
Step 05 adds date-range filtering to the profile page. Currently the page aggregates
all of a user's expenses with no time boundaries. This step lets the user scope every
panel — summary stats, transaction list, and category breakdown — to a chosen period:
preset shortcuts (This Month, Last Month, Last 3 Months, All Time) and an optional
custom date-range picker. Filtering is done server-side via GET query params so it
is bookmarkable, shareable, and works without JavaScript.

## Depends on
- Step 01 — Database setup (`expenses` table must exist)
- Step 03 — Login / logout (session must be set; `/profile` must be a protected route)
- Step 04 — Profile page design (profile.html and profile.css must exist)

## Routes
- `GET /profile?from=YYYY-MM-DD&to=YYYY-MM-DD` — same `/profile` route with two
  optional query params; both default to "all time" when absent — logged-in only

No new routes.

## Database changes
No new tables or columns. Three existing functions in `database/db.py` must accept
optional `date_from` and `date_to` parameters and add a `WHERE date BETWEEN ? AND ?`
clause when those params are provided:

- `get_expense_summary(user_id, date_from=None, date_to=None)`
- `get_expenses_by_category(user_id, date_from=None, date_to=None)`
- `get_recent_expenses(user_id, limit=10, date_from=None, date_to=None)`

When `date_from` is supplied but `date_to` is not (or vice versa), treat the missing
bound as open-ended (use `'0000-01-01'` as the floor and `'9999-12-31'` as the ceiling
rather than skipping the clause, so the query stays parameterised).

## Templates
- **Modify:** `templates/profile.html`
  - Add a filter bar above the stats row with four preset buttons (This Month,
    Last Month, Last 3 Months, All Time) and a "Custom" section with two
    `<input type="date">` fields plus an Apply button
  - Highlight the active preset using a CSS class (e.g. `filter-btn--active`)
  - Display the active date range as a human-readable label beneath the filter bar
    (e.g. "Showing: 01 May 2026 – 31 May 2026")
  - The custom date form POSTs to `GET /profile` via `method="get"`

## Files to change
- `app.py`
  - In the `/profile` view, read `request.args.get("from")` and
    `request.args.get("to")` and pass them through to each DB helper
  - Compute the active `label` string and `active_preset` name in Python and
    pass both to the template
  - All four preset names: `this_month`, `last_month`, `last_3_months`, `all_time`
- `database/db.py`
  - Update `get_expense_summary`, `get_expenses_by_category`, and
    `get_recent_expenses` signatures and SQL as described above
- `templates/profile.html` — add filter bar (see Templates section)
- `static/css/profile.css` — add styles for `.filter-bar`, `.filter-btn`,
  `.filter-btn--active`, `.filter-label`, `.custom-range`

## Files to create
No new files.

## New dependencies
No new dependencies.

## Rules for implementation
- No SQLAlchemy or ORMs — use raw `sqlite3` via `get_db()`
- Parameterised queries only — never use string formatting in SQL
- Passwords hashed with werkzeug (no auth changes in this step)
- Use CSS variables — never hardcode hex values
- All templates extend `base.html`
- Date bounds must be validated in `app.py` before being passed to DB helpers:
  accept only strings matching `YYYY-MM-DD`; ignore malformed values silently and
  fall back to "all time"
- Preset date arithmetic must use Python's `datetime` / `calendar` modules —
  no hard-coded date strings in `app.py`
- The filter form must be a plain HTML `<form method="get">` — no fetch/AJAX
- Keep `get_recent_expenses` limit at 10; the date filter narrows within that limit
- Do not change the function signatures of `create_user`, `get_user_by_email`, or
  `get_user_by_id`

## Definition of done
- [ ] Visiting `/profile` with no query params shows all expenses (behaviour unchanged from Step 04)
- [ ] Clicking "This Month" reloads the page with `?from=` and `?to=` set to the first and last day of the current calendar month
- [ ] Clicking "Last Month" reloads the page scoped to the previous calendar month
- [ ] Clicking "Last 3 Months" reloads the page scoped to the 3-month window ending today
- [ ] Clicking "All Time" reloads the page with no date params (or clears them)
- [ ] Submitting the custom date form with a valid from/to range filters all three panels (stats, transactions, categories) to that range
- [ ] The active preset button is visually highlighted (has the `filter-btn--active` class)
- [ ] The human-readable date label below the filter bar reflects the active range
- [ ] Passing a malformed date in the URL (e.g. `?from=not-a-date`) falls back gracefully to "all time" with no 500 error
- [ ] Passing `?from=2026-05-01&to=2026-05-31` returns only May 2026 expenses for the demo user (verify with seed data)
- [ ] All three panels (summary stats, recent transactions, category breakdown) update together when a filter is applied
- [ ] No hex colour values appear in the new CSS — only CSS variables
