# Spec: Login and Logout

## Overview
Login and Logout is Step 3 of the Spendly roadmap. It lets a registered user authenticate with their email and password, establishes a server-side session so subsequent requests know who is logged in, and provides a logout route that clears that session. The login form already exists as a template stub (`login.html`); this step wires it to a real POST handler that verifies credentials with Werkzeug's `check_password_hash` and stores the user's `id` in Flask's signed cookie session.

## Depends on
- Step 1 — Database setup (`get_db`, `users` table must exist)
- Step 2 — Registration (`create_user`, `users` rows with hashed passwords)

## Routes
- `GET /login` — render the login form — public
- `POST /login` — validate credentials, set session, redirect to `/profile` — public
- `GET /logout` — clear session, redirect to `/login` — logged-in (but safe to call when logged out too)

## Database changes
No new tables or columns. A new read helper is needed in `database/db.py`:

```python
def get_user_by_email(email):
    # Returns a sqlite3.Row or None
```

Query: `SELECT * FROM users WHERE email = ?`

## Templates
- **Modify:** `templates/login.html` — already exists and has the correct form markup; no HTML changes needed (the `{% if error %}` block is already present)
- **Modify:** `templates/base.html` — update the navbar `nav-links` block to show "Sign out" + username when `session.user_id` is set, and "Sign in" + "Get started" when logged out

## Files to change
- `app.py`
  - Add `session` to the Flask import
  - Add `check_password_hash` to the Werkzeug import
  - Add `get_user_by_email` to the `database.db` import
  - Set `app.secret_key` (use a hard-coded dev string; document that it must be an env var in production)
  - Replace the stub `GET /login` route with a two-method route handling `GET` and `POST`
  - Replace the stub `GET /logout` route with a real implementation
- `database/db.py`
  - Add `get_user_by_email(email)` function

## Files to create
No new files.

## New dependencies
No new dependencies. `werkzeug.security.check_password_hash` and `flask.session` are already available.

## Rules for implementation
- No SQLAlchemy or ORMs — use raw `sqlite3` via `get_db()`
- Parameterised queries only — never use string formatting in SQL
- Passwords verified with `werkzeug.security.check_password_hash` — never compare plaintext
- Use CSS variables — never hardcode hex values in templates or stylesheets
- All templates extend `base.html`
- Store only `user_id` (integer) in `session` — do not store the full row or password hash
- On bad credentials show a single generic error: "Invalid email or password." — do not distinguish between "email not found" and "wrong password"
- `app.secret_key` must be set before any session use; use a fixed dev string (e.g. `"dev-secret-change-in-production"`)
- After successful login redirect to `url_for("profile")`; after logout redirect to `url_for("login")`
- Always close the DB connection in `get_user_by_email` (use `try/finally`)

## Definition of done
- [ ] `GET /login` renders the login form with Email and Password fields
- [ ] Submitting valid credentials sets `session["user_id"]` and redirects to `/profile`
- [ ] Submitting an unknown email re-renders the form with "Invalid email or password."
- [ ] Submitting a correct email but wrong password re-renders the form with "Invalid email or password."
- [ ] `GET /logout` clears the session and redirects to `/login`
- [ ] After logout, `session.get("user_id")` is `None`
- [ ] The navbar shows "Sign out" (linking to `/logout`) when a user is logged in, and "Sign in" / "Get started" when logged out
- [ ] The demo account (`demo@spendly.com` / `demo123`) can log in successfully
