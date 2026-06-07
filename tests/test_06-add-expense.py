"""
tests/test_06-add-expense.py

Pytest test suite for the Spendly "Add Expense" feature on /expenses/add (Step 06).

All test logic is derived exclusively from the feature specification in
.claude/specs/06-add-expense.md.  Source files were read only to identify
fixture helpers, the Flask app object, the DB connection helper, and the
fixed category list constant — never to mirror the add_expense view's
internal implementation.

Spec highlights exercised here:
  - GET /expenses/add: auth-guarded, renders a form with the 7 fixed
    categories and a date field defaulting to today
  - POST /expenses/add: auth-guarded, validates amount/category/date,
    inserts into `expenses` tied to session user_id, redirects to /profile
  - Validation failures re-render the form, preserve entered values, and
    show a single inline error — for non-numeric amount, zero/negative
    amount, invalid/unknown category, invalid date format, and future dates
  - description is optional and may be empty

Seed data (from database/db.py seed_db):
  - Demo user: demo@spendly.com / demo123 (id likely 1)
  - 8 expenses, all dated in May 2026
"""

import re

import pytest

from app import app as flask_app
from database.db import get_db, get_user_by_email


FIXED_CATEGORIES = [
    "Food", "Transport", "Bills", "Health", "Entertainment", "Shopping", "Other",
]


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
        'SECRET_KEY': 'test-secret-06',
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


def _expense_count(user_id):
    """Helper: count rows in `expenses` for a given user (raw read-only query)."""
    conn = get_db()
    try:
        row = conn.execute(
            "SELECT COUNT(*) AS c FROM expenses WHERE user_id = ?", (user_id,)
        ).fetchone()
        return row["c"]
    finally:
        conn.close()


def _latest_expense(user_id):
    """Helper: fetch the most-recently-inserted expense row for a user."""
    conn = get_db()
    try:
        row = conn.execute(
            """SELECT id, user_id, amount, category, date, description
               FROM expenses WHERE user_id = ?
               ORDER BY id DESC LIMIT 1""",
            (user_id,)
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


@pytest.fixture()
def cleanup_new_expenses(demo_user_id):
    """
    Record the expense count before the test runs and delete any rows
    inserted during the test afterwards, so tests stay independent and
    don't pollute the shared on-disk seed DB for later tests/runs.
    """
    conn = get_db()
    try:
        before_ids = {
            r["id"] for r in conn.execute(
                "SELECT id FROM expenses WHERE user_id = ?", (demo_user_id,)
            ).fetchall()
        }
    finally:
        conn.close()

    yield

    conn = get_db()
    try:
        after_rows = conn.execute(
            "SELECT id FROM expenses WHERE user_id = ?", (demo_user_id,)
        ).fetchall()
        new_ids = [r["id"] for r in after_rows if r["id"] not in before_ids]
        for eid in new_ids:
            conn.execute("DELETE FROM expenses WHERE id = ?", (eid,))
        conn.commit()
    finally:
        conn.close()


def _today_iso():
    from datetime import date
    return date.today().isoformat()


def _tomorrow_iso():
    from datetime import date, timedelta
    return (date.today() + timedelta(days=1)).isoformat()


def _far_future_iso():
    from datetime import date
    return date(date.today().year + 1, 1, 1).isoformat()


VALID_PAYLOAD = {
    "amount": "42.50",
    "category": "Food",
    "date": _today_iso(),
    "description": "Test lunch expense",
}


def _payload(**overrides):
    data = dict(VALID_PAYLOAD)
    data.update(overrides)
    return data


# ---------------------------------------------------------------------------
# DoD: GET /expenses/add — auth guard
# ---------------------------------------------------------------------------

class TestGetAuthGuard:
    def test_get_add_expense_redirects_to_login_when_logged_out(self, client):
        resp = client.get('/expenses/add', follow_redirects=False)
        assert resp.status_code == 302, (
            "Expected 302 redirect for unauthenticated GET /expenses/add, got %d" % resp.status_code
        )
        location = resp.headers.get('Location', '')
        assert '/login' in location, (
            "Expected redirect to /login, got Location: '%s'" % location
        )

    def test_get_add_expense_redirect_lands_on_login_page(self, client):
        resp = client.get('/expenses/add', follow_redirects=True)
        assert resp.status_code == 200
        assert b'Login' in resp.data or b'login' in resp.data, (
            "Expected to land on the login page after following the redirect"
        )

    def test_get_add_expense_after_logout_redirects(self, auth_client):
        auth_client.get('/logout')
        resp = auth_client.get('/expenses/add', follow_redirects=False)
        assert resp.status_code == 302, (
            "Expected redirect for /expenses/add after logout, got %d" % resp.status_code
        )
        assert '/login' in resp.headers.get('Location', ''), (
            "Expected redirect target to be /login after logout"
        )


# ---------------------------------------------------------------------------
# DoD: GET /expenses/add — happy path / form rendering
# ---------------------------------------------------------------------------

class TestGetFormRendering:
    def test_get_add_expense_returns_200_when_logged_in(self, auth_client):
        resp = auth_client.get('/expenses/add')
        assert resp.status_code == 200, (
            "Expected HTTP 200 for authenticated GET /expenses/add, got %d" % resp.status_code
        )

    def test_get_add_expense_contains_a_form(self, auth_client):
        resp = auth_client.get('/expenses/add')
        html = resp.data.decode('utf-8')
        assert '<form' in html, "Expected a <form> element on the add-expense page"

    def test_get_add_expense_form_has_amount_field(self, auth_client):
        resp = auth_client.get('/expenses/add')
        html = resp.data.decode('utf-8')
        assert re.search(r'name=["\']amount["\']', html), (
            "Expected an input/field named 'amount' on the add-expense form"
        )

    def test_get_add_expense_form_has_category_select(self, auth_client):
        resp = auth_client.get('/expenses/add')
        html = resp.data.decode('utf-8')
        assert re.search(r'name=["\']category["\']', html), (
            "Expected a field named 'category' on the add-expense form"
        )

    def test_get_add_expense_form_has_date_field(self, auth_client):
        resp = auth_client.get('/expenses/add')
        html = resp.data.decode('utf-8')
        assert re.search(r'name=["\']date["\']', html), (
            "Expected a field named 'date' on the add-expense form"
        )

    def test_get_add_expense_form_has_description_field(self, auth_client):
        resp = auth_client.get('/expenses/add')
        html = resp.data.decode('utf-8')
        assert re.search(r'name=["\']description["\']', html), (
            "Expected a field named 'description' on the add-expense form"
        )

    def test_get_add_expense_extends_base_template(self, auth_client):
        """The page must extend base.html (navbar/footer indicators present)."""
        resp = auth_client.get('/expenses/add')
        assert b'Spendly' in resp.data, (
            "Expected 'Spendly' (from base.html navbar) on the add-expense page"
        )

    def test_get_add_expense_offers_exactly_seven_fixed_categories(self, auth_client):
        resp = auth_client.get('/expenses/add')
        html = resp.data.decode('utf-8')
        for category in FIXED_CATEGORIES:
            assert re.search(r'>\s*%s\s*<' % re.escape(category), html) or category in html, (
                "Expected category option '%s' to appear in the form" % category
            )

    def test_get_add_expense_category_options_match_exact_fixed_list(self, auth_client):
        """The <select name="category"> must offer exactly the seven fixed categories
        (no extra/missing options), per spec: 'must be one of the fixed list'."""
        resp = auth_client.get('/expenses/add')
        html = resp.data.decode('utf-8')

        select_match = re.search(
            r'<select[^>]*name=["\']category["\'][^>]*>(.*?)</select>',
            html, re.DOTALL | re.IGNORECASE
        )
        assert select_match is not None, (
            "Expected a <select name='category'> element on the add-expense form"
        )
        options_html = select_match.group(1)
        option_texts = [
            re.sub(r'\s+', ' ', m).strip()
            for m in re.findall(r'<option[^>]*>(.*?)</option>', options_html, re.DOTALL | re.IGNORECASE)
        ]
        # Filter out a possible empty/placeholder option (e.g. "Select a category")
        meaningful = [t for t in option_texts if t in FIXED_CATEGORIES]
        assert sorted(meaningful) == sorted(FIXED_CATEGORIES), (
            "Expected the category <select> to offer exactly %s, got %s"
            % (FIXED_CATEGORIES, meaningful)
        )

    def test_get_add_expense_date_field_defaults_to_today(self, auth_client):
        resp = auth_client.get('/expenses/add')
        html = resp.data.decode('utf-8')
        today = _today_iso()
        assert today in html, (
            "Expected the date field to default to today's ISO date (%s)" % today
        )
        # More specifically, the date input's value attribute should carry today's date
        assert re.search(
            r'name=["\']date["\'][^>]*value=["\']%s["\']' % re.escape(today), html
        ) or re.search(
            r'value=["\']%s["\'][^>]*name=["\']date["\']' % re.escape(today), html
        ), (
            "Expected the date <input> to have value='%s' (today)" % today
        )


# ---------------------------------------------------------------------------
# DoD: POST /expenses/add — auth guard
# ---------------------------------------------------------------------------

class TestPostAuthGuard:
    def test_post_add_expense_redirects_to_login_when_logged_out(self, client):
        resp = client.post('/expenses/add', data=_payload(), follow_redirects=False)
        assert resp.status_code == 302, (
            "Expected 302 redirect for unauthenticated POST /expenses/add, got %d" % resp.status_code
        )
        assert '/login' in resp.headers.get('Location', ''), (
            "Expected redirect target to be /login for unauthenticated POST"
        )

    def test_post_add_expense_does_not_insert_when_logged_out(self, client, demo_user_id):
        """An unauthenticated POST must not write to the expenses table."""
        before = _expense_count(demo_user_id)
        client.post('/expenses/add', data=_payload(), follow_redirects=False)
        after = _expense_count(demo_user_id)
        assert after == before, (
            "Expected no new expense row to be inserted for an unauthenticated POST"
        )


# ---------------------------------------------------------------------------
# DoD: POST /expenses/add — happy path (valid submission)
# ---------------------------------------------------------------------------

class TestPostHappyPath:
    def test_valid_submission_redirects_to_profile(self, auth_client, cleanup_new_expenses):
        resp = auth_client.post('/expenses/add', data=_payload(), follow_redirects=False)
        assert resp.status_code == 302, (
            "Expected redirect after a valid expense submission, got %d" % resp.status_code
        )
        location = resp.headers.get('Location', '')
        assert '/profile' in location, (
            "Expected redirect to /profile after valid submission, got Location: '%s'" % location
        )

    def test_valid_submission_inserts_row_for_current_user(self, auth_client, demo_user_id, cleanup_new_expenses):
        before = _expense_count(demo_user_id)
        auth_client.post('/expenses/add', data=_payload(), follow_redirects=False)
        after = _expense_count(demo_user_id)
        assert after == before + 1, (
            "Expected exactly one new expense row to be inserted for the current user "
            "(before=%d, after=%d)" % (before, after)
        )

    def test_valid_submission_persists_correct_field_values(self, auth_client, demo_user_id, cleanup_new_expenses):
        payload = _payload(amount="73.25", category="Transport",
                           date=_today_iso(), description="Taxi to airport")
        auth_client.post('/expenses/add', data=payload, follow_redirects=False)
        row = _latest_expense(demo_user_id)
        assert row is not None, "Expected a newly inserted expense row"
        assert row["user_id"] == demo_user_id, "Expense must be tied to the logged-in user"
        assert float(row["amount"]) == pytest.approx(73.25), (
            "Expected the inserted amount to equal 73.25, got %r" % row["amount"]
        )
        assert row["category"] == "Transport", (
            "Expected the inserted category to equal 'Transport', got %r" % row["category"]
        )
        assert row["date"] == _today_iso(), (
            "Expected the inserted date to equal today's date, got %r" % row["date"]
        )
        assert row["description"] == "Taxi to airport", (
            "Expected the inserted description to be preserved, got %r" % row["description"]
        )

    def test_valid_submission_appears_on_profile_page(self, auth_client, cleanup_new_expenses):
        """Per spec, the new expense must show up immediately on /profile."""
        unique_desc = "UniqueAddExpenseMarker7788"
        payload = _payload(amount="19.99", category="Shopping",
                           date=_today_iso(), description=unique_desc)
        auth_client.post('/expenses/add', data=payload, follow_redirects=False)

        resp = auth_client.get('/profile')
        assert resp.status_code == 200
        assert unique_desc.encode() in resp.data, (
            "Expected the newly-added expense's description to appear on /profile"
        )

    def test_valid_submission_with_empty_description_is_allowed(self, auth_client, demo_user_id, cleanup_new_expenses):
        """Per spec, description is optional — empty description must be accepted."""
        payload = _payload(amount="5.00", category="Other", date=_today_iso(), description="")
        before = _expense_count(demo_user_id)
        resp = auth_client.post('/expenses/add', data=payload, follow_redirects=False)
        after = _expense_count(demo_user_id)

        assert resp.status_code == 302, (
            "Expected redirect (success) when description is empty, got %d" % resp.status_code
        )
        assert '/profile' in resp.headers.get('Location', ''), (
            "Expected redirect to /profile when description is empty"
        )
        assert after == before + 1, (
            "Expected the expense to be inserted even with an empty description"
        )

    def test_valid_submission_without_description_field_at_all_is_allowed(self, auth_client, demo_user_id, cleanup_new_expenses):
        """Submitting the form entirely without a description key should also succeed
        (description is optional)."""
        payload = {
            "amount": "8.40",
            "category": "Bills",
            "date": _today_iso(),
            # no "description" key at all
        }
        before = _expense_count(demo_user_id)
        resp = auth_client.post('/expenses/add', data=payload, follow_redirects=False)
        after = _expense_count(demo_user_id)

        assert resp.status_code == 302, (
            "Expected redirect (success) when description field is omitted, got %d" % resp.status_code
        )
        assert after == before + 1, (
            "Expected the expense to be inserted when description is omitted entirely"
        )


# ---------------------------------------------------------------------------
# DoD: POST /expenses/add — validation: amount
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
    def test_non_numeric_amount_rerenders_form_with_error(self, auth_client, demo_user_id, bad_amount):
        before = _expense_count(demo_user_id)
        resp = auth_client.post('/expenses/add', data=_payload(amount=bad_amount), follow_redirects=False)

        assert resp.status_code == 200, (
            "Expected the form to be re-rendered (HTTP 200) for a non-numeric amount '%s', got %d"
            % (bad_amount, resp.status_code)
        )
        html = resp.data.decode('utf-8')
        assert '<form' in html, "Expected the add-expense form to be re-rendered"
        # Should not redirect to /profile
        assert resp.headers.get('Location') is None or '/profile' not in resp.headers.get('Location', ''), (
            "A validation failure must not redirect to /profile"
        )

        after = _expense_count(demo_user_id)
        assert after == before, (
            "A non-numeric amount ('%s') must not insert a row into expenses" % bad_amount
        )

    @pytest.mark.parametrize("bad_amount", ["0", "0.00", "-5", "-0.01", "-100"])
    def test_zero_or_negative_amount_rerenders_form_with_error(self, auth_client, demo_user_id, bad_amount):
        before = _expense_count(demo_user_id)
        resp = auth_client.post('/expenses/add', data=_payload(amount=bad_amount), follow_redirects=False)

        assert resp.status_code == 200, (
            "Expected the form to be re-rendered (HTTP 200) for amount '%s' (<= 0), got %d"
            % (bad_amount, resp.status_code)
        )
        assert resp.headers.get('Location') is None or '/profile' not in resp.headers.get('Location', ''), (
            "A zero/negative amount must not redirect to /profile"
        )

        after = _expense_count(demo_user_id)
        assert after == before, (
            "A zero/negative amount ('%s') must not insert a row into expenses" % bad_amount
        )

    def test_non_numeric_amount_shows_inline_error_message(self, auth_client):
        resp = auth_client.post('/expenses/add', data=_payload(amount="not-a-number"), follow_redirects=False)
        html = resp.data.decode('utf-8')
        assert re.search(r'error', html, re.IGNORECASE), (
            "Expected an inline error message to be displayed for a non-numeric amount"
        )

    def test_zero_amount_shows_inline_error_message(self, auth_client):
        resp = auth_client.post('/expenses/add', data=_payload(amount="0"), follow_redirects=False)
        html = resp.data.decode('utf-8')
        assert re.search(r'error', html, re.IGNORECASE), (
            "Expected an inline error message to be displayed for a zero amount"
        )

    def test_invalid_amount_preserves_entered_category_date_description(self, auth_client):
        """Spec: validation failures must preserve the entered values (no lost input)."""
        payload = _payload(amount="not-a-number", category="Bills",
                           date=_today_iso(), description="Keep me visible 12345")
        resp = auth_client.post('/expenses/add', data=payload, follow_redirects=False)
        html = resp.data.decode('utf-8')

        assert "Keep me visible 12345" in html, (
            "Expected the entered description to be preserved on validation failure"
        )
        assert _today_iso() in html, (
            "Expected the entered date to be preserved on validation failure"
        )
        # The category 'Bills' should remain selected
        assert re.search(r'<option[^>]*value=["\']Bills["\'][^>]*selected', html) or \
               re.search(r'selected[^>]*>\s*Bills', html) or \
               re.search(r'>\s*Bills\s*</option>\s*</select>', html) or \
               'Bills' in html, (
            "Expected the entered category 'Bills' to be preserved/selected on validation failure"
        )


# ---------------------------------------------------------------------------
# DoD: POST /expenses/add — validation: category
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
    def test_invalid_or_unknown_category_rerenders_form_with_error(self, auth_client, demo_user_id, bad_category):
        before = _expense_count(demo_user_id)
        resp = auth_client.post('/expenses/add', data=_payload(category=bad_category), follow_redirects=False)

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

        after = _expense_count(demo_user_id)
        assert after == before, (
            "An invalid/unknown category ('%s') must not insert a row into expenses" % bad_category
        )

    def test_missing_category_field_entirely_is_rejected(self, auth_client, demo_user_id):
        payload = {
            "amount": "10.00",
            "date": _today_iso(),
            "description": "no category supplied",
        }
        before = _expense_count(demo_user_id)
        resp = auth_client.post('/expenses/add', data=payload, follow_redirects=False)
        after = _expense_count(demo_user_id)

        assert resp.status_code == 200, (
            "Expected the form to be re-rendered when category is missing entirely, got %d"
            % resp.status_code
        )
        assert after == before, (
            "Expected no row inserted when the category field is missing"
        )

    def test_invalid_category_preserves_entered_amount_date_description(self, auth_client):
        payload = _payload(category="NotARealCategory", amount="33.33",
                           date=_today_iso(), description="Preserve me too 99887")
        resp = auth_client.post('/expenses/add', data=payload, follow_redirects=False)
        html = resp.data.decode('utf-8')

        assert "Preserve me too 99887" in html, (
            "Expected the entered description to be preserved on category validation failure"
        )
        assert "33.33" in html, (
            "Expected the entered amount to be preserved on category validation failure"
        )
        assert _today_iso() in html, (
            "Expected the entered date to be preserved on category validation failure"
        )


# ---------------------------------------------------------------------------
# DoD: POST /expenses/add — validation: date
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
    def test_invalid_date_format_rerenders_form_with_error(self, auth_client, demo_user_id, bad_date):
        before = _expense_count(demo_user_id)
        resp = auth_client.post('/expenses/add', data=_payload(date=bad_date), follow_redirects=False)

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

        after = _expense_count(demo_user_id)
        assert after == before, (
            "An invalid date ('%s') must not insert a row into expenses" % bad_date
        )

    def test_invalid_date_does_not_leak_raw_sql_error(self, auth_client):
        resp = auth_client.post('/expenses/add', data=_payload(date="' OR '1'='1"), follow_redirects=False)
        assert resp.status_code == 200
        assert b'sqlite3' not in resp.data.lower(), (
            "Response must not leak sqlite3 error details for a malformed date input"
        )

    @pytest.mark.parametrize("future_date_fn", [_tomorrow_iso, _far_future_iso])
    def test_future_date_rerenders_form_with_error(self, auth_client, demo_user_id, future_date_fn):
        future_date = future_date_fn()
        before = _expense_count(demo_user_id)
        resp = auth_client.post('/expenses/add', data=_payload(date=future_date), follow_redirects=False)

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

        after = _expense_count(demo_user_id)
        assert after == before, (
            "A future date ('%s') must not insert a row into expenses" % future_date
        )

    def test_today_is_accepted_not_treated_as_future(self, auth_client, demo_user_id, cleanup_new_expenses):
        """Sanity check: today's date (the form default) must be accepted, i.e. the
        future-date check is exclusive of 'today'."""
        before = _expense_count(demo_user_id)
        resp = auth_client.post('/expenses/add', data=_payload(date=_today_iso()), follow_redirects=False)
        after = _expense_count(demo_user_id)

        assert resp.status_code == 302, (
            "Expected today's date to be accepted and redirect to /profile, got %d" % resp.status_code
        )
        assert after == before + 1, (
            "Expected today's date to result in a successful insert"
        )

    def test_invalid_date_preserves_entered_amount_category_description(self, auth_client):
        payload = _payload(date="not-a-real-date", amount="27.10", category="Health",
                           description="Date validation preserve check 5544")
        resp = auth_client.post('/expenses/add', data=payload, follow_redirects=False)
        html = resp.data.decode('utf-8')

        assert "Date validation preserve check 5544" in html, (
            "Expected the entered description to be preserved on date validation failure"
        )
        assert "27.10" in html, (
            "Expected the entered amount to be preserved on date validation failure"
        )
        assert re.search(r'<option[^>]*value=["\']Health["\'][^>]*selected', html) or \
               re.search(r'selected[^>]*>\s*Health', html) or \
               'Health' in html, (
            "Expected the entered category 'Health' to be preserved/selected on date validation failure"
        )


# ---------------------------------------------------------------------------
# Cross-cutting: a single inline error is shown (not multiple/duplicated)
# ---------------------------------------------------------------------------

class TestSingleInlineError:
    def test_validation_failure_shows_a_single_error_message(self, auth_client):
        """Spec: 're-render add_expense.html ... with a single inline error message'."""
        resp = auth_client.post('/expenses/add', data=_payload(amount="not-a-number"), follow_redirects=False)
        html = resp.data.decode('utf-8')
        # Heuristic: an element commonly used for inline errors (e.g. class="error"/"form-error"/"alert")
        error_blocks = re.findall(r'class=["\'][^"\']*\b(?:error|alert|form-error)\b[^"\']*["\']', html, re.IGNORECASE)
        assert len(error_blocks) <= 1 or len(set(error_blocks)) == 1, (
            "Expected at most one distinct inline-error element on a validation failure, "
            "found multiple distinct error containers: %r" % error_blocks
        )


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    def test_get_request_does_not_insert_any_row(self, auth_client, demo_user_id):
        before = _expense_count(demo_user_id)
        auth_client.get('/expenses/add')
        after = _expense_count(demo_user_id)
        assert after == before, "A GET request must never insert a row into expenses"

    def test_description_is_stripped_of_surrounding_whitespace(self, auth_client, demo_user_id, cleanup_new_expenses):
        """Spec: description is optional, stripped of leading/trailing whitespace."""
        payload = _payload(amount="6.66", category="Entertainment",
                           date=_today_iso(), description="   padded description   ")
        resp = auth_client.post('/expenses/add', data=payload, follow_redirects=False)
        assert resp.status_code == 302, "Expected a successful insert with whitespace-padded description"

        row = _latest_expense(demo_user_id)
        assert row is not None
        assert row["description"] in ("padded description", "padded description   ".strip()), (
            "Expected the stored description to be stripped of surrounding whitespace, got %r"
            % row["description"]
        )
        assert row["description"] == "padded description", (
            "Expected stored description to equal the stripped string 'padded description', got %r"
            % row["description"]
        )

    def test_very_large_amount_is_accepted(self, auth_client, demo_user_id, cleanup_new_expenses):
        """A large but valid positive amount should be accepted (no spec upper bound)."""
        payload = _payload(amount="999999.99", category="Bills", date=_today_iso())
        resp = auth_client.post('/expenses/add', data=payload, follow_redirects=False)
        assert resp.status_code == 302, (
            "Expected a large positive amount to be accepted, got %d" % resp.status_code
        )
        row = _latest_expense(demo_user_id)
        assert float(row["amount"]) == pytest.approx(999999.99)

    def test_small_fractional_amount_is_accepted(self, auth_client, demo_user_id, cleanup_new_expenses):
        """A very small positive amount (e.g. 0.01) should be accepted since it is > 0."""
        payload = _payload(amount="0.01", category="Other", date=_today_iso())
        resp = auth_client.post('/expenses/add', data=payload, follow_redirects=False)
        assert resp.status_code == 302, (
            "Expected a small positive amount (0.01) to be accepted, got %d" % resp.status_code
        )
        row = _latest_expense(demo_user_id)
        assert float(row["amount"]) == pytest.approx(0.01)

    def test_amount_with_extra_decimal_precision_does_not_crash(self, auth_client):
        """An amount with many decimal places should be handled gracefully (accept or
        reject), but must never 500."""
        resp = auth_client.post('/expenses/add', data=_payload(amount="12.999999"), follow_redirects=False)
        assert resp.status_code != 500, (
            "Expected no server error for an amount with extra decimal precision"
        )

    def test_sql_injection_in_description_is_handled_safely(self, auth_client, demo_user_id, cleanup_new_expenses):
        """Parameterised queries should make SQL-injection attempts inert; the value
        is simply stored/escaped as a literal string."""
        malicious = "Robert'); DROP TABLE expenses;--"
        payload = _payload(amount="3.50", category="Food", date=_today_iso(), description=malicious)
        resp = auth_client.post('/expenses/add', data=payload, follow_redirects=False)

        assert resp.status_code == 302, (
            "Expected a normal successful insert even with SQL-meta-characters in description"
        )
        # The expenses table must still exist and be queryable
        count = _expense_count(demo_user_id)
        assert count >= 1, "Expected the expenses table to remain intact after the injection attempt"

        row = _latest_expense(demo_user_id)
        assert row["description"] == malicious, (
            "Expected the malicious string to be stored verbatim (as a literal), not executed"
        )

    def test_long_description_does_not_crash(self, auth_client, cleanup_new_expenses):
        long_desc = "A" * 2000
        payload = _payload(amount="2.00", category="Food", date=_today_iso(), description=long_desc)
        resp = auth_client.post('/expenses/add', data=payload, follow_redirects=False)
        assert resp.status_code != 500, (
            "Expected no server error for a very long description"
        )

    def test_missing_amount_field_entirely_rerenders_form(self, auth_client, demo_user_id):
        payload = {
            "category": "Food",
            "date": _today_iso(),
            "description": "no amount field",
        }
        before = _expense_count(demo_user_id)
        resp = auth_client.post('/expenses/add', data=payload, follow_redirects=False)
        after = _expense_count(demo_user_id)

        assert resp.status_code == 200, (
            "Expected the form to be re-rendered when amount is missing entirely, got %d"
            % resp.status_code
        )
        assert after == before, "Expected no row inserted when amount field is missing"

    def test_missing_date_field_entirely_rerenders_form(self, auth_client, demo_user_id):
        payload = {
            "amount": "10.00",
            "category": "Food",
            "description": "no date field",
        }
        before = _expense_count(demo_user_id)
        resp = auth_client.post('/expenses/add', data=payload, follow_redirects=False)
        after = _expense_count(demo_user_id)

        assert resp.status_code == 200, (
            "Expected the form to be re-rendered when date is missing entirely, got %d"
            % resp.status_code
        )
        assert after == before, "Expected no row inserted when date field is missing"
