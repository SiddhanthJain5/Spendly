"""
tests/test_07-edit-expense.py

Pytest test suite for the Spendly "Edit Expense" feature on
/expenses/<id>/edit (Step 07).

All test logic is derived exclusively from the feature specification in
.claude/specs/07-edit-expense.md.  Source files were read only to identify
fixture helpers, the Flask app object, the DB connection helper, the fixed
category list constant, and the DB helper signatures (`get_expense_by_id`,
`update_expense`, `create_expense`, `create_user`, `get_user_by_email`) —
never to mirror the edit_expense view's internal implementation.

Spec highlights exercised here:
  - GET/POST /expenses/<id>/edit: auth-guarded (redirect to /login)
  - Ownership guard: 404 for an expense that doesn't exist or belongs to
    another user (applies to both GET and POST)
  - GET renders a form pre-filled with the expense's current
    amount/category/date/description
  - POST with valid data updates the row in `expenses` (scoped to user_id)
    and redirects to /profile
  - POST with invalid amount (non-numeric, zero, negative) re-renders the
    form with an inline error AND preserves the submitted (not stale DB)
    values
  - POST with invalid/future date re-renders the form with an inline error
  - POST with empty/unknown category re-renders the form with an inline error
  - The updated values are reflected on /profile afterward (transaction
    history / summary / category breakdown)

Seed data (from database/db.py seed_db):
  - Demo user: demo@spendly.com / demo123
  - 8 expenses, all dated in May 2026, ids assigned in insertion order
"""

import re
from datetime import date, timedelta

import pytest

from app import app as flask_app
from database.db import get_db, get_user_by_email, create_user, create_expense


FIXED_CATEGORIES = [
    "Food", "Transport", "Bills", "Health", "Entertainment", "Shopping", "Other",
]


# ---------------------------------------------------------------------------
# Date helpers
# ---------------------------------------------------------------------------

def _today_iso():
    return date.today().isoformat()


def _yesterday_iso():
    return (date.today() - timedelta(days=1)).isoformat()


def _tomorrow_iso():
    return (date.today() + timedelta(days=1)).isoformat()


def _far_future_iso():
    return date(date.today().year + 1, 1, 1).isoformat()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def app():
    """
    Fresh Flask app configured for testing.

    NOTE: db.py's helpers each open their own sqlite3 connection to the
    on-disk DB_PATH ("spendly.db"); there is no per-request app-context DB
    attachment, so ':memory:' cannot be used here (connections wouldn't
    share state). We rely on the real spendly.db that app.py initialises
    and seeds at import time. seed_db() is idempotent.
    """
    flask_app.config.update({
        'TESTING': True,
        'SECRET_KEY': 'test-secret-07',
        'WTF_CSRF_ENABLED': False,
    })
    yield flask_app


@pytest.fixture()
def client(app):
    """Unauthenticated test client."""
    return app.test_client()


@pytest.fixture()
def auth_client(client):
    """
    Test client authenticated as the demo user via the dev autologin route.
    Relies on the demo seed data being present (seed_db is idempotent).
    """
    resp = client.get('/dev/autologin', follow_redirects=False)
    assert resp.status_code in (301, 302), (
        "Expected redirect from /dev/autologin, got %d" % resp.status_code
    )
    return client


@pytest.fixture()
def demo_user_id(app):
    """The id of the seeded demo user — used to scope DB assertions."""
    with app.app_context():
        user = get_user_by_email("demo@spendly.com")
    assert user is not None, "Expected seeded demo user to exist"
    return user["id"]


# ---------------------------------------------------------------------------
# Raw, read-only / setup DB helpers (parameterised SQL only)
# ---------------------------------------------------------------------------

def _get_expense_row(expense_id):
    conn = get_db()
    try:
        row = conn.execute(
            "SELECT id, user_id, amount, category, date, description FROM expenses WHERE id = ?",
            (expense_id,)
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def _insert_expense_for(user_id, amount=10.0, category="Food",
                        expense_date=None, description="seed-owned-expense"):
    """Create a fresh expense for a given user and return its id."""
    expense_date = expense_date or _yesterday_iso()
    before_ids = _expense_ids_for(user_id)
    create_expense(user_id, amount, category, expense_date, description)
    after_ids = _expense_ids_for(user_id)
    new_ids = after_ids - before_ids
    assert len(new_ids) == 1, "Expected exactly one new expense id to appear after insert"
    return new_ids.pop()


def _expense_ids_for(user_id):
    conn = get_db()
    try:
        rows = conn.execute("SELECT id FROM expenses WHERE user_id = ?", (user_id,)).fetchall()
        return {r["id"] for r in rows}
    finally:
        conn.close()


def _delete_expense(expense_id):
    conn = get_db()
    try:
        conn.execute("DELETE FROM expenses WHERE id = ?", (expense_id,))
        conn.commit()
    finally:
        conn.close()


def _delete_user(user_id):
    conn = get_db()
    try:
        conn.execute("DELETE FROM expenses WHERE user_id = ?", (user_id,))
        conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
        conn.commit()
    finally:
        conn.close()


def _max_expense_id():
    conn = get_db()
    try:
        row = conn.execute("SELECT MAX(id) AS m FROM expenses").fetchone()
        return row["m"] or 0
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Fixture: an expense owned by the demo user, cleaned up afterward, with its
# original values captured so we can assert against "stale DB values".
# ---------------------------------------------------------------------------

@pytest.fixture()
def own_expense(demo_user_id):
    """
    Insert a fresh expense owned by the demo user with known starting values,
    yield its id and original field dict, then delete it after the test.
    """
    original = {
        "amount": 55.25,
        "category": "Bills",
        "date": _yesterday_iso(),
        "description": "Original description ABC123",
    }
    expense_id = _insert_expense_for(
        demo_user_id,
        amount=original["amount"],
        category=original["category"],
        expense_date=original["date"],
        description=original["description"],
    )
    yield {"id": expense_id, **original}
    _delete_expense(expense_id)


@pytest.fixture()
def other_user_expense(app):
    """
    Create a second user with their own expense (not the demo user), yield
    its id, and clean up both the expense and the user afterward.
    """
    with app.app_context():
        existing = get_user_by_email("other-edit-tester@example.com")
        if existing is None:
            create_user("Other Tester", "other-edit-tester@example.com",
                        "pbkdf2:sha256:placeholderhashvalueplaceholder")
            other_user = get_user_by_email("other-edit-tester@example.com")
        else:
            other_user = existing
    other_user_id = other_user["id"]

    expense_id = _insert_expense_for(
        other_user_id, amount=77.0, category="Shopping",
        expense_date=_yesterday_iso(), description="Belongs to someone else"
    )

    yield expense_id

    _delete_expense(expense_id)
    _delete_user(other_user_id)


def _payload(**overrides):
    data = {
        "amount": "60.00",
        "category": "Food",
        "date": _yesterday_iso(),
        "description": "Updated description XYZ789",
    }
    data.update(overrides)
    return data


def _edit_url(expense_id):
    return "/expenses/%d/edit" % expense_id


# ---------------------------------------------------------------------------
# DoD: auth guard — GET and POST /expenses/<id>/edit require login
# ---------------------------------------------------------------------------

class TestAuthGuard:
    def test_get_edit_redirects_to_login_when_logged_out(self, client, own_expense):
        resp = client.get(_edit_url(own_expense["id"]), follow_redirects=False)
        assert resp.status_code == 302, (
            "Expected 302 redirect for unauthenticated GET /expenses/<id>/edit, got %d"
            % resp.status_code
        )
        assert '/login' in resp.headers.get('Location', ''), (
            "Expected redirect to /login for unauthenticated GET, got Location: '%s'"
            % resp.headers.get('Location', '')
        )

    def test_get_edit_redirect_lands_on_login_page(self, client, own_expense):
        resp = client.get(_edit_url(own_expense["id"]), follow_redirects=True)
        assert resp.status_code == 200
        assert b'Login' in resp.data or b'login' in resp.data, (
            "Expected to land on the login page after following the redirect"
        )

    def test_post_edit_redirects_to_login_when_logged_out(self, client, own_expense):
        resp = client.post(_edit_url(own_expense["id"]), data=_payload(), follow_redirects=False)
        assert resp.status_code == 302, (
            "Expected 302 redirect for unauthenticated POST /expenses/<id>/edit, got %d"
            % resp.status_code
        )
        assert '/login' in resp.headers.get('Location', ''), (
            "Expected redirect to /login for unauthenticated POST, got Location: '%s'"
            % resp.headers.get('Location', '')
        )

    def test_post_edit_does_not_modify_row_when_logged_out(self, client, own_expense):
        """An unauthenticated POST must not write to the expenses table."""
        before = _get_expense_row(own_expense["id"])
        client.post(_edit_url(own_expense["id"]), data=_payload(amount="999.99"), follow_redirects=False)
        after = _get_expense_row(own_expense["id"])
        assert after == before, (
            "Expected the expense row to be unchanged after an unauthenticated POST"
        )

    def test_get_edit_after_logout_redirects(self, auth_client, own_expense):
        auth_client.get('/logout')
        resp = auth_client.get(_edit_url(own_expense["id"]), follow_redirects=False)
        assert resp.status_code == 302, (
            "Expected redirect for /expenses/<id>/edit after logout, got %d" % resp.status_code
        )
        assert '/login' in resp.headers.get('Location', ''), (
            "Expected redirect target to be /login after logout"
        )


# ---------------------------------------------------------------------------
# DoD: ownership guard — 404 for missing or other-user expenses
# ---------------------------------------------------------------------------

class TestOwnershipGuard:
    def test_get_edit_nonexistent_expense_returns_404(self, auth_client):
        nonexistent_id = _max_expense_id() + 100000
        resp = auth_client.get(_edit_url(nonexistent_id))
        assert resp.status_code == 404, (
            "Expected 404 for GET on a non-existent expense id, got %d" % resp.status_code
        )

    def test_post_edit_nonexistent_expense_returns_404(self, auth_client):
        nonexistent_id = _max_expense_id() + 100001
        resp = auth_client.post(_edit_url(nonexistent_id), data=_payload())
        assert resp.status_code == 404, (
            "Expected 404 for POST on a non-existent expense id, got %d" % resp.status_code
        )

    def test_get_edit_other_users_expense_returns_404(self, auth_client, other_user_expense):
        resp = auth_client.get(_edit_url(other_user_expense))
        assert resp.status_code == 404, (
            "Expected 404 when the logged-in user tries to view another user's "
            "expense edit form, got %d" % resp.status_code
        )

    def test_post_edit_other_users_expense_returns_404(self, auth_client, other_user_expense):
        resp = auth_client.post(_edit_url(other_user_expense), data=_payload(amount="123.45"))
        assert resp.status_code == 404, (
            "Expected 404 when the logged-in user tries to submit edits for "
            "another user's expense, got %d" % resp.status_code
        )

    def test_post_edit_other_users_expense_does_not_modify_row(self, auth_client, other_user_expense):
        """Ownership guard must prevent any DB mutation, not just hide the page."""
        before = _get_expense_row(other_user_expense)
        auth_client.post(_edit_url(other_user_expense), data=_payload(amount="123.45", category="Health"))
        after = _get_expense_row(other_user_expense)
        assert after == before, (
            "Expected another user's expense row to remain unchanged after a "
            "blocked edit attempt (ownership guard must prevent mutation)"
        )

    def test_get_edit_nonexistent_id_does_not_redirect_to_login(self, auth_client):
        """A 404 (not a redirect to /login) is expected for a logged-in user
        hitting a missing id — distinguishing the auth guard from the
        ownership guard."""
        nonexistent_id = _max_expense_id() + 100002
        resp = auth_client.get(_edit_url(nonexistent_id), follow_redirects=False)
        assert resp.status_code == 404
        assert resp.status_code != 302, (
            "A logged-in user hitting a non-existent expense id must get 404, not a redirect"
        )


# ---------------------------------------------------------------------------
# DoD: GET happy path — form pre-filled with current values
# ---------------------------------------------------------------------------

class TestGetFormPrefill:
    def test_get_edit_own_expense_returns_200(self, auth_client, own_expense):
        resp = auth_client.get(_edit_url(own_expense["id"]))
        assert resp.status_code == 200, (
            "Expected HTTP 200 for GET on the user's own expense edit form, got %d"
            % resp.status_code
        )

    def test_get_edit_contains_a_form(self, auth_client, own_expense):
        resp = auth_client.get(_edit_url(own_expense["id"]))
        html = resp.data.decode('utf-8')
        assert '<form' in html, "Expected a <form> element on the edit-expense page"

    def test_get_edit_extends_base_template(self, auth_client, own_expense):
        resp = auth_client.get(_edit_url(own_expense["id"]))
        assert b'Spendly' in resp.data, (
            "Expected 'Spendly' (from base.html navbar) on the edit-expense page"
        )

    def test_get_edit_form_has_expected_fields(self, auth_client, own_expense):
        resp = auth_client.get(_edit_url(own_expense["id"]))
        html = resp.data.decode('utf-8')
        for field in ("amount", "category", "date", "description"):
            assert re.search(r'name=["\']%s["\']' % field, html), (
                "Expected a field named '%s' on the edit-expense form" % field
            )

    def test_get_edit_prefills_amount(self, auth_client, own_expense):
        resp = auth_client.get(_edit_url(own_expense["id"]))
        html = resp.data.decode('utf-8')
        # The amount input's value should carry the expense's current amount
        # (rendered as e.g. "55.25" or "55.3" depending on template formatting,
        # so match loosely on the "55.2" / "55.25" prefix as well as the bare value).
        assert re.search(r'name=["\']amount["\'][^>]*value=["\']?55\.2', html) or \
               re.search(r'value=["\']?55\.2[^>]*name=["\']amount["\']', html) or \
               "55.25" in html, (
            "Expected the amount input's value to reflect the expense's current amount (55.25)"
        )

    def test_get_edit_prefills_category(self, auth_client, own_expense):
        resp = auth_client.get(_edit_url(own_expense["id"]))
        html = resp.data.decode('utf-8')
        assert re.search(r'<option[^>]*value=["\']Bills["\'][^>]*selected', html) or \
               re.search(r'selected[^>]*>\s*Bills', html), (
            "Expected the category <select> to have 'Bills' pre-selected "
            "(the expense's current category)"
        )

    def test_get_edit_prefills_date(self, auth_client, own_expense):
        resp = auth_client.get(_edit_url(own_expense["id"]))
        html = resp.data.decode('utf-8')
        expected_date = own_expense["date"]
        assert expected_date in html, (
            "Expected the expense's current date (%s) to appear in the form" % expected_date
        )
        assert re.search(
            r'name=["\']date["\'][^>]*value=["\']%s["\']' % re.escape(expected_date), html
        ) or re.search(
            r'value=["\']%s["\'][^>]*name=["\']date["\']' % re.escape(expected_date), html
        ), (
            "Expected the date <input> to have value='%s' (the expense's current date)" % expected_date
        )

    def test_get_edit_prefills_description(self, auth_client, own_expense):
        resp = auth_client.get(_edit_url(own_expense["id"]))
        html = resp.data.decode('utf-8')
        assert own_expense["description"] in html, (
            "Expected the expense's current description to be pre-filled in the form"
        )

    def test_get_edit_offers_fixed_category_list(self, auth_client, own_expense):
        resp = auth_client.get(_edit_url(own_expense["id"]))
        html = resp.data.decode('utf-8')
        for category in FIXED_CATEGORIES:
            assert category in html, (
                "Expected category option '%s' to appear in the edit form" % category
            )

    def test_get_edit_has_back_to_profile_link(self, auth_client, own_expense, app):
        resp = auth_client.get(_edit_url(own_expense["id"]))
        html = resp.data.decode('utf-8')
        with app.app_context():
            from flask import url_for
            profile_url = url_for('profile')
        assert profile_url in html, (
            "Expected a 'Back to profile' link pointing to %s on the edit form" % profile_url
        )


# ---------------------------------------------------------------------------
# DoD: POST happy path — valid update persists and redirects to /profile
# ---------------------------------------------------------------------------

class TestPostHappyPath:
    def test_valid_update_redirects_to_profile(self, auth_client, own_expense):
        resp = auth_client.post(_edit_url(own_expense["id"]), data=_payload(), follow_redirects=False)
        assert resp.status_code == 302, (
            "Expected redirect after a valid expense update, got %d" % resp.status_code
        )
        assert '/profile' in resp.headers.get('Location', ''), (
            "Expected redirect to /profile after valid update, got Location: '%s'"
            % resp.headers.get('Location', '')
        )

    def test_valid_update_persists_new_values_in_db(self, auth_client, own_expense, demo_user_id):
        new_values = {
            "amount": "88.40",
            "category": "Transport",
            "date": _today_iso(),
            "description": "Brand new description QWERTY42",
        }
        auth_client.post(_edit_url(own_expense["id"]), data=new_values, follow_redirects=False)

        row = _get_expense_row(own_expense["id"])
        assert row is not None, "Expected the expense row to still exist after update"
        assert row["user_id"] == demo_user_id, "Expected the row to remain owned by the same user"
        assert float(row["amount"]) == pytest.approx(88.40), (
            "Expected the updated amount to equal 88.40, got %r" % row["amount"]
        )
        assert row["category"] == "Transport", (
            "Expected the updated category to equal 'Transport', got %r" % row["category"]
        )
        assert row["date"] == _today_iso(), (
            "Expected the updated date to equal today's date, got %r" % row["date"]
        )
        assert row["description"] == "Brand new description QWERTY42", (
            "Expected the updated description to be persisted, got %r" % row["description"]
        )

    def test_valid_update_does_not_change_row_id_or_owner(self, auth_client, own_expense, demo_user_id):
        before = _get_expense_row(own_expense["id"])
        auth_client.post(_edit_url(own_expense["id"]), data=_payload(amount="12.34"), follow_redirects=False)
        after = _get_expense_row(own_expense["id"])

        assert after["id"] == before["id"], "Expected the expense id to remain unchanged after edit"
        assert after["user_id"] == before["user_id"] == demo_user_id, (
            "Expected the expense's owner (user_id) to remain unchanged after edit"
        )

    def test_valid_update_does_not_create_a_new_row(self, auth_client, own_expense, demo_user_id):
        before_ids = _expense_ids_for(demo_user_id)
        auth_client.post(_edit_url(own_expense["id"]), data=_payload(), follow_redirects=False)
        after_ids = _expense_ids_for(demo_user_id)
        assert after_ids == before_ids, (
            "Expected an edit to update the existing row in place, not insert a new one"
        )

    def test_valid_update_reflected_on_profile_page(self, auth_client, own_expense):
        """Per spec, the updated expense must show up immediately on /profile
        in the transaction history."""
        unique_desc = "UniqueEditMarker99001122"
        new_values = {
            "amount": "73.10",
            "category": "Entertainment",
            "date": _today_iso(),
            "description": unique_desc,
        }
        auth_client.post(_edit_url(own_expense["id"]), data=new_values, follow_redirects=False)

        resp = auth_client.get('/profile')
        assert resp.status_code == 200
        html = resp.data.decode('utf-8')
        assert unique_desc in html, (
            "Expected the updated expense's new description to appear on /profile"
        )
        # The stale (pre-edit) description should no longer be visible for this expense
        assert own_expense["description"] not in html, (
            "Expected the original (stale) description to no longer appear on /profile "
            "after the expense was edited"
        )

    def test_valid_update_with_empty_description_clears_it(self, auth_client, own_expense):
        """Per spec, description is optional — an empty description should be
        accepted and persisted (cleared)."""
        new_values = {
            "amount": "20.00",
            "category": "Other",
            "date": _today_iso(),
            "description": "",
        }
        resp = auth_client.post(_edit_url(own_expense["id"]), data=new_values, follow_redirects=False)
        assert resp.status_code == 302, (
            "Expected redirect (success) when description is cleared to empty, got %d"
            % resp.status_code
        )
        row = _get_expense_row(own_expense["id"])
        assert row["description"] in (None, ""), (
            "Expected the stored description to be cleared (None or empty), got %r"
            % row["description"]
        )

    def test_description_is_stripped_of_surrounding_whitespace(self, auth_client, own_expense):
        new_values = _payload(description="   padded edit description   ")
        resp = auth_client.post(_edit_url(own_expense["id"]), data=new_values, follow_redirects=False)
        assert resp.status_code == 302

        row = _get_expense_row(own_expense["id"])
        assert row["description"] == "padded edit description", (
            "Expected the stored description to be stripped of surrounding whitespace, got %r"
            % row["description"]
        )


# ---------------------------------------------------------------------------
# DoD: POST validation — amount
# ---------------------------------------------------------------------------

class TestAmountValidation:
    @pytest.mark.parametrize("bad_amount", [
        "abc",
        "twelve",
        "12,50",
        "$12.50",
        "12.50.30",
        "1e",
        "",
        "   ",
    ])
    def test_non_numeric_amount_rerenders_form_with_error(self, auth_client, own_expense, bad_amount):
        resp = auth_client.post(_edit_url(own_expense["id"]), data=_payload(amount=bad_amount), follow_redirects=False)

        assert resp.status_code == 200, (
            "Expected the form to be re-rendered (HTTP 200) for a non-numeric amount '%s', got %d"
            % (bad_amount, resp.status_code)
        )
        html = resp.data.decode('utf-8')
        assert '<form' in html, "Expected the edit-expense form to be re-rendered"
        assert resp.headers.get('Location') is None or '/profile' not in resp.headers.get('Location', ''), (
            "A validation failure must not redirect to /profile"
        )
        assert re.search(r'error', html, re.IGNORECASE), (
            "Expected an inline error message for non-numeric amount '%s'" % bad_amount
        )

        row = _get_expense_row(own_expense["id"])
        assert float(row["amount"]) == pytest.approx(own_expense["amount"]), (
            "A non-numeric amount ('%s') must not modify the stored amount" % bad_amount
        )

    @pytest.mark.parametrize("bad_amount", ["0", "0.00", "-5", "-0.01", "-100"])
    def test_zero_or_negative_amount_rerenders_form_with_error(self, auth_client, own_expense, bad_amount):
        resp = auth_client.post(_edit_url(own_expense["id"]), data=_payload(amount=bad_amount), follow_redirects=False)

        assert resp.status_code == 200, (
            "Expected the form to be re-rendered (HTTP 200) for amount '%s' (<= 0), got %d"
            % (bad_amount, resp.status_code)
        )
        assert resp.headers.get('Location') is None or '/profile' not in resp.headers.get('Location', ''), (
            "A zero/negative amount must not redirect to /profile"
        )
        html = resp.data.decode('utf-8')
        assert re.search(r'error', html, re.IGNORECASE), (
            "Expected an inline error message for amount '%s'" % bad_amount
        )

        row = _get_expense_row(own_expense["id"])
        assert float(row["amount"]) == pytest.approx(own_expense["amount"]), (
            "A zero/negative amount ('%s') must not modify the stored amount" % bad_amount
        )

    def test_invalid_amount_preserves_entered_values_not_stale_db_values(self, auth_client, own_expense):
        """Spec: on validation failure, re-render with the entered values
        preserved — NOT the stale DB values."""
        payload = {
            "amount": "not-a-number",
            "category": "Health",
            "date": _today_iso(),
            "description": "Freshly typed value 778899",
        }
        resp = auth_client.post(_edit_url(own_expense["id"]), data=payload, follow_redirects=False)
        html = resp.data.decode('utf-8')

        # The freshly typed values must appear...
        assert "Freshly typed value 778899" in html, (
            "Expected the entered description to be preserved on validation failure"
        )
        assert _today_iso() in html, (
            "Expected the entered date to be preserved on validation failure"
        )
        assert re.search(r'<option[^>]*value=["\']Health["\'][^>]*selected', html) or \
               re.search(r'selected[^>]*>\s*Health', html), (
            "Expected the entered category 'Health' to be preserved/selected on validation failure"
        )
        # ...and the stale DB values must NOT reappear in their place
        assert own_expense["description"] not in html, (
            "Expected the stale DB description NOT to reappear after a validation failure "
            "(the user's freshly typed value must win)"
        )
        assert own_expense["date"] not in html, (
            "Expected the stale DB date NOT to reappear after a validation failure"
        )

        # And the DB itself must remain untouched
        row = _get_expense_row(own_expense["id"])
        assert row["category"] == own_expense["category"], (
            "A validation failure must not write any changes to the DB"
        )
        assert row["description"] == own_expense["description"], (
            "A validation failure must not write any changes to the DB"
        )

    def test_non_numeric_amount_shows_inline_error_message(self, auth_client, own_expense):
        resp = auth_client.post(_edit_url(own_expense["id"]), data=_payload(amount="not-a-number"), follow_redirects=False)
        html = resp.data.decode('utf-8')
        assert re.search(r'error', html, re.IGNORECASE), (
            "Expected an inline error message to be displayed for a non-numeric amount"
        )


# ---------------------------------------------------------------------------
# DoD: POST validation — category
# ---------------------------------------------------------------------------

class TestCategoryValidation:
    @pytest.mark.parametrize("bad_category", [
        "",
        "Groceries",
        "food",          # wrong casing — must match the fixed list exactly
        "FOOD",
        "Misc",
        "<script>alert(1)</script>",
        "Food; DROP TABLE expenses;--",
    ])
    def test_invalid_or_unknown_category_rerenders_form_with_error(self, auth_client, own_expense, bad_category):
        resp = auth_client.post(_edit_url(own_expense["id"]), data=_payload(category=bad_category), follow_redirects=False)

        assert resp.status_code == 200, (
            "Expected the form to be re-rendered (HTTP 200) for category '%s', got %d"
            % (bad_category, resp.status_code)
        )
        assert resp.headers.get('Location') is None or '/profile' not in resp.headers.get('Location', ''), (
            "An invalid/unknown category must not redirect to /profile"
        )
        html = resp.data.decode('utf-8')
        assert re.search(r'error', html, re.IGNORECASE), (
            "Expected an inline error message for invalid category '%s'" % bad_category
        )

        row = _get_expense_row(own_expense["id"])
        assert row["category"] == own_expense["category"], (
            "An invalid/unknown category ('%s') must not modify the stored category" % bad_category
        )

    def test_missing_category_field_entirely_rerenders_form(self, auth_client, own_expense):
        payload = {
            "amount": "10.00",
            "date": _today_iso(),
            "description": "no category supplied",
        }
        resp = auth_client.post(_edit_url(own_expense["id"]), data=payload, follow_redirects=False)
        assert resp.status_code == 200, (
            "Expected the form to be re-rendered when category is missing entirely, got %d"
            % resp.status_code
        )
        row = _get_expense_row(own_expense["id"])
        assert row["category"] == own_expense["category"], (
            "Expected no DB modification when the category field is missing"
        )

    def test_invalid_category_preserves_entered_values_not_stale_db_values(self, auth_client, own_expense):
        payload = {
            "amount": "44.44",
            "category": "NotARealCategory",
            "date": _today_iso(),
            "description": "Category preserve check 334455",
        }
        resp = auth_client.post(_edit_url(own_expense["id"]), data=payload, follow_redirects=False)
        html = resp.data.decode('utf-8')

        assert "Category preserve check 334455" in html, (
            "Expected the entered description to be preserved on category validation failure"
        )
        assert "44.44" in html, (
            "Expected the entered amount to be preserved on category validation failure"
        )
        assert own_expense["description"] not in html, (
            "Expected the stale DB description NOT to reappear after a category validation failure"
        )


# ---------------------------------------------------------------------------
# DoD: POST validation — date
# ---------------------------------------------------------------------------

class TestDateValidation:
    @pytest.mark.parametrize("bad_date", [
        "",
        "not-a-date",
        "2026/06/07",     # wrong separator
        "06-07-2026",     # wrong order
        "2026-13-01",     # invalid month
        "2026-02-30",     # invalid day for February
        "2026-6-7",       # missing zero-padding
        "06 June 2026",   # human readable, not ISO
        "' OR 1=1 --",    # SQL injection attempt
    ])
    def test_invalid_date_format_rerenders_form_with_error(self, auth_client, own_expense, bad_date):
        resp = auth_client.post(_edit_url(own_expense["id"]), data=_payload(date=bad_date), follow_redirects=False)

        assert resp.status_code == 200, (
            "Expected the form to be re-rendered (HTTP 200) for invalid date '%s', got %d"
            % (bad_date, resp.status_code)
        )
        assert resp.headers.get('Location') is None or '/profile' not in resp.headers.get('Location', ''), (
            "An invalid date format must not redirect to /profile"
        )
        html = resp.data.decode('utf-8')
        assert re.search(r'error', html, re.IGNORECASE), (
            "Expected an inline error message for invalid date '%s'" % bad_date
        )
        assert b'sqlite3' not in resp.data.lower(), (
            "Response must not leak sqlite3 error details for invalid date '%s'" % bad_date
        )

        row = _get_expense_row(own_expense["id"])
        assert row["date"] == own_expense["date"], (
            "An invalid date ('%s') must not modify the stored date" % bad_date
        )

    @pytest.mark.parametrize("future_date_fn", [_tomorrow_iso, _far_future_iso])
    def test_future_date_rerenders_form_with_error(self, auth_client, own_expense, future_date_fn):
        future_date = future_date_fn()
        resp = auth_client.post(_edit_url(own_expense["id"]), data=_payload(date=future_date), follow_redirects=False)

        assert resp.status_code == 200, (
            "Expected the form to be re-rendered (HTTP 200) for a future date '%s', got %d"
            % (future_date, resp.status_code)
        )
        assert resp.headers.get('Location') is None or '/profile' not in resp.headers.get('Location', ''), (
            "A future date must not redirect to /profile (spec says future dates are rejected)"
        )
        html = resp.data.decode('utf-8')
        assert re.search(r'error', html, re.IGNORECASE), (
            "Expected an inline error message for a future date '%s'" % future_date
        )

        row = _get_expense_row(own_expense["id"])
        assert row["date"] == own_expense["date"], (
            "A future date ('%s') must not modify the stored date" % future_date
        )

    def test_today_is_accepted_not_treated_as_future(self, auth_client, own_expense):
        """Sanity check: today's date must be accepted (the future-date check
        is exclusive of 'today'), matching the Add Expense behaviour."""
        resp = auth_client.post(_edit_url(own_expense["id"]), data=_payload(date=_today_iso()), follow_redirects=False)
        assert resp.status_code == 302, (
            "Expected today's date to be accepted and redirect to /profile, got %d" % resp.status_code
        )
        row = _get_expense_row(own_expense["id"])
        assert row["date"] == _today_iso(), "Expected today's date to be persisted"

    def test_invalid_date_preserves_entered_values_not_stale_db_values(self, auth_client, own_expense):
        payload = {
            "amount": "29.50",
            "category": "Shopping",
            "date": "not-a-real-date",
            "description": "Date preserve check 667788",
        }
        resp = auth_client.post(_edit_url(own_expense["id"]), data=payload, follow_redirects=False)
        html = resp.data.decode('utf-8')

        assert "Date preserve check 667788" in html, (
            "Expected the entered description to be preserved on date validation failure"
        )
        assert "29.50" in html, (
            "Expected the entered amount to be preserved on date validation failure"
        )
        assert re.search(r'<option[^>]*value=["\']Shopping["\'][^>]*selected', html) or \
               re.search(r'selected[^>]*>\s*Shopping', html), (
            "Expected the entered category 'Shopping' to be preserved/selected on date validation failure"
        )
        assert own_expense["description"] not in html, (
            "Expected the stale DB description NOT to reappear after a date validation failure"
        )

    def test_invalid_date_does_not_leak_raw_sql_error(self, auth_client, own_expense):
        resp = auth_client.post(_edit_url(own_expense["id"]), data=_payload(date="' OR '1'='1"), follow_redirects=False)
        assert resp.status_code == 200
        assert b'sqlite3' not in resp.data.lower(), (
            "Response must not leak sqlite3 error details for a malformed date input"
        )


# ---------------------------------------------------------------------------
# Cross-cutting: a single inline error is shown
# ---------------------------------------------------------------------------

class TestSingleInlineError:
    def test_validation_failure_shows_a_single_error_message(self, auth_client, own_expense):
        """Spec: 're-render edit_expense.html ... with a single inline error message'."""
        resp = auth_client.post(_edit_url(own_expense["id"]), data=_payload(amount="not-a-number"), follow_redirects=False)
        html = resp.data.decode('utf-8')
        error_blocks = re.findall(
            r'class=["\'][^"\']*\b(?:error|alert|form-error)\b[^"\']*["\']', html, re.IGNORECASE
        )
        assert len(error_blocks) <= 1 or len(set(error_blocks)) == 1, (
            "Expected at most one distinct inline-error element on a validation failure, "
            "found multiple distinct error containers: %r" % error_blocks
        )


# ---------------------------------------------------------------------------
# DoD: edit link/icon visible on each row of /profile's transaction table
# ---------------------------------------------------------------------------

class TestProfileEditLink:
    def test_profile_transaction_rows_link_to_edit_route(self, auth_client, own_expense, app):
        """Each row in the transaction table should expose a link to
        /expenses/<id>/edit for that row's expense (per spec, using
        url_for('edit_expense', id=exp.id))."""
        resp = auth_client.get('/profile')
        assert resp.status_code == 200
        html = resp.data.decode('utf-8')

        with app.app_context():
            from flask import url_for
            edit_url = url_for('edit_expense', id=own_expense["id"])

        assert edit_url in html, (
            "Expected the profile page's transaction table to contain a link to "
            "%s for the user's expense" % edit_url
        )


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    def test_get_request_does_not_modify_row(self, auth_client, own_expense):
        before = _get_expense_row(own_expense["id"])
        auth_client.get(_edit_url(own_expense["id"]))
        after = _get_expense_row(own_expense["id"])
        assert after == before, "A GET request must never modify the expense row"

    def test_sql_injection_in_description_is_handled_safely(self, auth_client, own_expense):
        """Parameterised queries should make SQL-injection attempts inert; the
        value is simply stored/escaped as a literal string."""
        malicious = "Robert'); DROP TABLE expenses;--"
        payload = _payload(description=malicious)
        resp = auth_client.post(_edit_url(own_expense["id"]), data=payload, follow_redirects=False)

        assert resp.status_code == 302, (
            "Expected a normal successful update even with SQL-meta-characters in description"
        )
        row = _get_expense_row(own_expense["id"])
        assert row is not None, "Expected the expenses table to remain intact after the injection attempt"
        assert row["description"] == malicious, (
            "Expected the malicious string to be stored verbatim (as a literal), not executed"
        )

    def test_long_description_does_not_crash(self, auth_client, own_expense):
        long_desc = "B" * 2000
        payload = _payload(description=long_desc)
        resp = auth_client.post(_edit_url(own_expense["id"]), data=payload, follow_redirects=False)
        assert resp.status_code != 500, "Expected no server error for a very long description"

    def test_missing_amount_field_entirely_rerenders_form_without_modifying_db(self, auth_client, own_expense):
        payload = {
            "category": "Food",
            "date": _today_iso(),
            "description": "no amount field",
        }
        resp = auth_client.post(_edit_url(own_expense["id"]), data=payload, follow_redirects=False)
        assert resp.status_code == 200, (
            "Expected the form to be re-rendered when amount is missing entirely, got %d"
            % resp.status_code
        )
        row = _get_expense_row(own_expense["id"])
        assert float(row["amount"]) == pytest.approx(own_expense["amount"]), (
            "Expected no DB modification when the amount field is missing"
        )

    def test_missing_date_field_entirely_rerenders_form_without_modifying_db(self, auth_client, own_expense):
        payload = {
            "amount": "10.00",
            "category": "Food",
            "description": "no date field",
        }
        resp = auth_client.post(_edit_url(own_expense["id"]), data=payload, follow_redirects=False)
        assert resp.status_code == 200, (
            "Expected the form to be re-rendered when date is missing entirely, got %d"
            % resp.status_code
        )
        row = _get_expense_row(own_expense["id"])
        assert row["date"] == own_expense["date"], (
            "Expected no DB modification when the date field is missing"
        )

    def test_nonexistent_id_path_does_not_500(self, auth_client):
        """A wildly out-of-range id should yield 404, not a server error."""
        resp = auth_client.get('/expenses/999999999/edit')
        assert resp.status_code == 404
        assert resp.status_code != 500


# ---------------------------------------------------------------------------
# DoD: profile summary / category breakdown reflect the edit
# ---------------------------------------------------------------------------

class TestProfileSummaryReflectsEdit:
    def test_changing_amount_updates_profile_summary_total(self, auth_client, own_expense):
        """Per spec, the change must be reflected in the profile's summary
        stats immediately after the edit."""
        # Fetch the summary total before the edit
        before_resp = auth_client.get('/profile')
        assert before_resp.status_code == 200

        # Bump the amount up by a large, easily distinguishable delta
        new_amount = own_expense["amount"] + 500.00
        new_values = _payload(amount="%.2f" % new_amount, date=own_expense["date"],
                              category=own_expense["category"])
        post_resp = auth_client.post(_edit_url(own_expense["id"]), data=new_values, follow_redirects=False)
        assert post_resp.status_code == 302

        after_resp = auth_client.get('/profile')
        assert after_resp.status_code == 200
        after_html = after_resp.data.decode('utf-8')

        # The new amount (or a formatted variant of it) should now be discoverable
        # somewhere on the page (recent expenses / category breakdown / summary).
        assert ("%.2f" % new_amount) in after_html or ("%.0f" % new_amount) in after_html, (
            "Expected the updated amount (%.2f) to be reflected somewhere on /profile "
            "(transaction history, summary, or category breakdown)" % new_amount
        )
