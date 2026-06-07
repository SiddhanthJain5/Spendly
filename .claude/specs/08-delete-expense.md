# Spec: Delete Expense

## Overview
Delete Expense replaces the `/expenses/<id>/delete` stub with a real
destructive action that lets a logged-in user permanently remove an
expense they own. It is the final CRUD operation in the Spendly roadmap,
completing the add → edit → delete lifecycle for transactions. Deletion
is triggered from the transaction row on the profile page, guarded by a
confirmation prompt so a misclick can't silently destroy data, and the
result is reflected immediately in the transaction history, summary
stats, and category breakdown via a redirect back to `/profile`.

## Depends on
- Step 01 — Database setup (`expenses` table, `get_db`)
- Step 03 — Login / logout (session must be set; route must be protected)
- Step 04 — Profile page design (`profile.html`, `profile.css`, `.txn-row`,
  `.txn-actions` layout)
- Step 05 — Date filter for profile page (existing query helpers operate on
  the `expenses` table by `user_id`)
- Step 07 — Edit expense (`get_expense_by_id` ownership-check pattern,
  `.txn-edit` icon-link styling to mirror for the delete icon)

## Routes
- `POST /expenses/<int:id>/delete` — delete the expense if it exists and
  belongs to the current user, flash a confirmation message, and redirect
  to `/profile` — logged-in only (redirect to `/login` if not authenticated;
  return 404 if the expense doesn't exist or doesn't belong to the current user)

The existing stub is a bare `GET` route returning placeholder text; it must
be changed to `POST` so deletion can never be triggered by a simple link
visit, prefetch, or crawler.

## Database changes
No schema changes. The `expenses` table already exists:
```
expenses (id, user_id, amount, category, date, description, created_at)
```
One new helper is needed in `database/db.py`:

```python
def delete_expense(expense_id, user_id):
    # DELETE FROM expenses WHERE id = ? AND user_id = ?
```

`get_expense_by_id(expense_id, user_id)` (added in Step 07) is reused to
confirm ownership before deleting and to return 404 on mismatch.

## Templates
- **Create:** No new templates.
- **Modify:** `templates/profile.html` — add a delete icon/button to the
  `.txn-actions` span of each row in the transaction table (around
  line 102-106, alongside the existing `.txn-edit` link), using the
  `lucide` icon set already loaded on the page (e.g. `trash-2`). Since
  deletion must be a `POST`, this must be a small inline `<form
  method="POST" action="{{ url_for('delete_expense', id=exp.id) }}">`
  containing a submit `<button>` styled to look like an icon-link
  (matching `.txn-edit`), not an `<a>` tag.

## Files to change
- `app.py` — replace the stub `GET /expenses/<int:id>/delete` route with a
  `POST`-only route that:
  - Redirects unauthenticated users to `/login`
  - Looks up the expense via `get_expense_by_id`; returns a 404 if it
    doesn't exist or isn't owned by the current user
  - Deletes the row via `delete_expense`
  - Flashes a success message (e.g. "Expense deleted.", category `"success"`,
    matching the pattern used by `add_expense`/`edit_expense`)
  - Redirects to `url_for("profile")`
- `database/db.py` — add `delete_expense(expense_id, user_id)`
- `templates/profile.html` — add the per-row delete form/button described above
- `static/css/profile.css` — add styles for the new delete button so it
  matches the existing `.txn-edit` icon-link layout (reuse/extend the
  `.txn-actions` rules, using existing CSS variables; a `.txn-delete`
  class mirroring `.txn-edit` with a hover state in the destructive/error
  color already defined as a CSS variable)

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
- Authentication guard: check `session.get("user_id")`; if absent,
  `redirect(url_for("login"))`
- Ownership guard: the lookup and delete must filter by `user_id` so a
  user can never delete another user's expense; return HTTP 404 on mismatch
- The route must only accept `POST` (no `GET` handler) — deletion must
  never be reachable via a plain link click, browser prefetch, or bookmark
- Add a client-side confirmation (e.g. `onsubmit="return confirm(...)"` on
  the delete form, or an equivalent small script in `main.js`) so users
  can't delete an expense with a single accidental click
- Always close the DB connection in the new helper (use `try/finally`)
- After a successful delete, redirect to `url_for("profile")` and flash a
  `"success"`-category message so the toast system already wired in
  `base.html`/`main.js` displays it
- Reuse the existing `get_expense_by_id` helper from Step 07 — do not
  duplicate the ownership-check query

## Definition of done
- [ ] Visiting `/expenses/<id>/delete` while logged out (via a direct POST,
      e.g. with curl or a form) redirects to `/login`
- [ ] Sending `POST /expenses/<id>/delete` for an expense that doesn't exist,
      or that belongs to another user, returns HTTP 404
- [ ] Sending `GET /expenses/<id>/delete` returns HTTP 405 (Method Not Allowed)
- [ ] Submitting the delete form for your own expense removes the row from
      the `expenses` table and redirects to `/profile`
- [ ] After deletion, the removed expense no longer appears in the profile
      page's transaction history, and the summary stats and category
      breakdown update to reflect the new totals
- [ ] A success toast/flash message appears on `/profile` after a
      successful deletion
- [ ] A delete icon/button is visible on each row of the transaction table
      on `/profile`, asks for confirmation before submitting, and removes
      only the corresponding expense
- [ ] No hex colour values appear in any new or modified template/stylesheet
      — only CSS variables
