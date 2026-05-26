# Spec: Registration

## Overview
Registration is Step 2 of the Spendly roadmap and introduces the first user-facing data-entry flow. It allows a new visitor to create an account by submitting their name, email, and password. The form POSTs to the server, validates the input, hashes the password with Werkzeug, and inserts a row into the `users` table. On success the user is redirected to the login page; on failure the form re-renders with an inline error message.

## Depends on
- Step 1 — Database setup (`get_db`, `init_db`, `users` table must exist)

## Routes
- `GET /register` — render the registration form — public
- `POST /register` — validate input, insert user, redirect to `/login` — public

## Database changes
No database changes. The `users` table already exists:
```
users (id, name, email, password_hash, created_at)
```
`email` has a `UNIQUE` constraint — use it to detect duplicate accounts.

## Templates
- **Create:** `templates/register.html` — registration form (name, email, password, confirm password fields; error display area)
- **Modify:** `templates/base.html` — ensure the "Register" navbar link points to `/register` (already present; verify it is correct)

## Files to change
- `app.py` — replace the stub `GET /register` route with a two-method route that handles both `GET` and `POST`

## Files to create
- `templates/register.html` — registration form template

## New dependencies
No new dependencies. `werkzeug.security.generate_password_hash` is already available.

## Rules for implementation
- No SQLAlchemy or ORMs — use raw `sqlite3` via `get_db()`
- Parameterised queries only — never use string formatting in SQL
- Hash passwords with `werkzeug.security.generate_password_hash` before inserting
- Use CSS variables — never hardcode hex colour values in templates or stylesheets
- All templates extend `base.html`
- Validate server-side: name non-empty, valid email format, password ≥ 8 characters, password matches confirmation
- On duplicate email catch the `sqlite3.IntegrityError` and show a user-friendly error ("An account with that email already exists.")
- Always close the DB connection (use a `try/finally` or `with` block)
- Do not log the user in after registration — redirect to `/login` with a success flash or query-param message

## Definition of done
- [ ] `GET /register` renders a form with fields: Name, Email, Password, Confirm Password, and a Submit button
- [ ] Submitting the form with valid, unique data inserts a row into `users` and redirects to `/login`
- [ ] The stored `password_hash` is a Werkzeug hash, not plaintext (verify via `sqlite3` CLI or DB browser)
- [ ] Submitting with a duplicate email re-renders the form with the message "An account with that email already exists."
- [ ] Submitting with mismatched passwords re-renders the form with a validation error
- [ ] Submitting with a password shorter than 8 characters re-renders the form with a validation error
- [ ] Submitting with an empty name or email re-renders the form with a validation error
- [ ] The register page is accessible at `/register` without being logged in
