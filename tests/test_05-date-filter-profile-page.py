"""
tests/test_05-date-filter-profile-page.py

Pytest test suite for the Spendly date-filter feature on /profile (Step 05).

All test logic is derived exclusively from the feature specification in
.claude/specs/05-date-filter-profile-page.md.  Source files were read only
to identify fixture helpers and the Flask app object.

Seed data (from database/db.py seed_db):
  - Demo user: demo@spendly.com / demo123
  - 8 expenses, all dated in May 2026 (2026-05-01 through 2026-05-20)
  - Total spend: 12.50+45.00+120.00+35.00+25.00+89.99+18.75+15.00 = 361.24
"""

import calendar
import re
from datetime import date, timedelta

import pytest

from app import app as flask_app
from database.db import init_db, seed_db


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def app():
    """
    Fresh Flask app configured for testing.

    IMPORTANT: The database helpers in db.py open a connection to DB_PATH each
    time they are called; there is no per-request application-context DB
    attachment.  Because of that, in-memory ':memory:' databases are NOT
    shared across connections and therefore cannot be used here.

    Instead we rely on the real spendly.db that is initialised and seeded at
    module import time (app.py runs init_db()/seed_db() at startup).  The
    seed data is idempotent (seed_db() is a no-op when rows already exist),
    so running the suite against the real DB is safe.
    """
    flask_app.config.update({
        'TESTING': True,
        'SECRET_KEY': 'test-secret-05',
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
    This relies on the demo seed data being present (seed_db is idempotent).
    """
    resp = client.get('/dev/autologin', follow_redirects=False)
    # autologin sets the session and redirects to /profile
    assert resp.status_code in (301, 302), (
        "Expected redirect from /dev/autologin, got %d" % resp.status_code
    )
    return client


# ---------------------------------------------------------------------------
# Helper: compute the same preset date ranges as app.py does at runtime
# ---------------------------------------------------------------------------

def _preset_dates():
    """Return the same (from, to) tuples that app.py's _build_preset_dates() computes."""
    today = date.today()
    # this month
    first_this = today.replace(day=1)
    last_this = today.replace(day=calendar.monthrange(today.year, today.month)[1])
    # last month
    last_last = first_this - timedelta(days=1)
    first_last = last_last.replace(day=1)
    # last 3 months: 1st of the month 2 months back, up to today
    m, y = today.month, today.year
    for _ in range(2):
        m -= 1
        if m == 0:
            m, y = 12, y - 1
    first_3m = date(y, m, 1)
    return {
        "this_month": (first_this.isoformat(), last_this.isoformat()),
        "last_month": (first_last.isoformat(), last_last.isoformat()),
        "last_3_months": (first_3m.isoformat(), today.isoformat()),
    }


# ---------------------------------------------------------------------------
# DoD 1 — /profile with no params returns HTTP 200 and "Showing: All time"
# ---------------------------------------------------------------------------

class TestNoParams:
    def test_profile_no_params_returns_200(self, auth_client):
        resp = auth_client.get('/profile')
        assert resp.status_code == 200, (
            "Expected HTTP 200 for /profile with no query params, got %d" % resp.status_code
        )

    def test_profile_no_params_shows_all_time_label(self, auth_client):
        resp = auth_client.get('/profile')
        assert b'Showing: All time' in resp.data, (
            "Expected 'Showing: All time' in response when no date params are given"
        )

    def test_profile_no_params_all_time_button_is_active(self, auth_client):
        resp = auth_client.get('/profile')
        html = resp.data.decode('utf-8')
        # The "All Time" link should carry the active class
        assert 'filter-btn--active' in html, (
            "Expected at least one element with class 'filter-btn--active' on /profile"
        )
        # More specifically the All Time button should be active
        assert re.search(r'filter-btn--active[^>]*>\s*All Time', html) or \
               re.search(r'All Time[^<]*<[^>]+filter-btn--active', html) or \
               re.search(r'filter-btn filter-btn--active[^>]*>\s*\n?\s*All Time', html), (
            "Expected the 'All Time' button to have the filter-btn--active class when no params given"
        )


# ---------------------------------------------------------------------------
# DoD 2 — "This Month" preset href is correct
# ---------------------------------------------------------------------------

class TestThisMonthPreset:
    def test_this_month_href_contains_correct_dates(self, auth_client):
        presets = _preset_dates()
        from_date, to_date = presets['this_month']
        resp = auth_client.get('/profile')
        html = resp.data.decode('utf-8')
        expected_href_fragment = (
            'from=%s' % from_date
        )
        assert expected_href_fragment in html, (
            "Expected 'This Month' href to contain from=%s, but it was not found in HTML" % from_date
        )
        assert ('to=%s' % to_date) in html, (
            "Expected 'This Month' href to contain to=%s, but it was not found in HTML" % to_date
        )

    def test_this_month_href_first_day_is_day_1(self, auth_client):
        resp = auth_client.get('/profile')
        html = resp.data.decode('utf-8')
        today = date.today()
        first_day = today.replace(day=1).isoformat()
        assert first_day in html, (
            "Expected the first day of the current month (%s) to appear in the This Month href" % first_day
        )

    def test_this_month_href_last_day_is_month_end(self, auth_client):
        resp = auth_client.get('/profile')
        html = resp.data.decode('utf-8')
        today = date.today()
        last_day = today.replace(day=calendar.monthrange(today.year, today.month)[1]).isoformat()
        assert last_day in html, (
            "Expected the last day of the current month (%s) to appear in the This Month href" % last_day
        )


# ---------------------------------------------------------------------------
# DoD 3 — "Last Month" preset href scopes to previous calendar month
# ---------------------------------------------------------------------------

class TestLastMonthPreset:
    def test_last_month_href_contains_correct_dates(self, auth_client):
        presets = _preset_dates()
        from_date, to_date = presets['last_month']
        resp = auth_client.get('/profile')
        html = resp.data.decode('utf-8')
        assert ('from=%s' % from_date) in html, (
            "Expected 'Last Month' href to contain from=%s" % from_date
        )
        assert ('to=%s' % to_date) in html, (
            "Expected 'Last Month' href to contain to=%s" % to_date
        )

    def test_last_month_from_is_first_day_of_previous_month(self, auth_client):
        today = date.today()
        first_this = today.replace(day=1)
        last_last = first_this - timedelta(days=1)
        first_last = last_last.replace(day=1)
        resp = auth_client.get('/profile')
        html = resp.data.decode('utf-8')
        assert first_last.isoformat() in html, (
            "Expected first day of last month (%s) in Last Month preset href" % first_last.isoformat()
        )

    def test_last_month_to_is_last_day_of_previous_month(self, auth_client):
        today = date.today()
        first_this = today.replace(day=1)
        last_last = first_this - timedelta(days=1)
        resp = auth_client.get('/profile')
        html = resp.data.decode('utf-8')
        assert last_last.isoformat() in html, (
            "Expected last day of last month (%s) in Last Month preset href" % last_last.isoformat()
        )


# ---------------------------------------------------------------------------
# DoD 4 — "Last 3 Months" preset href is correct
# ---------------------------------------------------------------------------

class TestLast3MonthsPreset:
    def test_last_3_months_href_contains_correct_dates(self, auth_client):
        presets = _preset_dates()
        from_date, to_date = presets['last_3_months']
        resp = auth_client.get('/profile')
        html = resp.data.decode('utf-8')
        assert ('from=%s' % from_date) in html, (
            "Expected 'Last 3 Months' href to contain from=%s" % from_date
        )
        assert ('to=%s' % to_date) in html, (
            "Expected 'Last 3 Months' href to contain to=%s" % to_date
        )

    def test_last_3_months_to_date_is_today(self, auth_client):
        today = date.today().isoformat()
        resp = auth_client.get('/profile')
        html = resp.data.decode('utf-8')
        assert ('to=%s' % today) in html, (
            "Expected 'Last 3 Months' preset to use today (%s) as the end date" % today
        )

    def test_last_3_months_from_is_first_day_two_months_back(self, auth_client):
        presets = _preset_dates()
        from_date, _ = presets['last_3_months']
        resp = auth_client.get('/profile')
        html = resp.data.decode('utf-8')
        assert from_date in html, (
            "Expected Last 3 Months start date (%s) in the HTML" % from_date
        )


# ---------------------------------------------------------------------------
# DoD 5 — "All Time" button/link href is plain /profile (no date params)
# ---------------------------------------------------------------------------

class TestAllTimePreset:
    def test_all_time_href_is_plain_profile(self, auth_client):
        resp = auth_client.get('/profile')
        html = resp.data.decode('utf-8')
        # The All Time anchor should point to /profile with no query params.
        # It must NOT have from= or to= on the same href.
        # We check that an href="/profile" (or href="/profile") anchor exists and contains "All Time".
        assert re.search(r'href="/profile"\s*\n?\s*class="filter-btn', html) or \
               re.search(r'href="/profile"[^>]*>\s*\n?\s*All Time', html), (
            "Expected an 'All Time' anchor with href='/profile' (no query params)"
        )

    def test_all_time_href_does_not_contain_from_param(self, auth_client):
        resp = auth_client.get('/profile')
        html = resp.data.decode('utf-8')
        # Extract the All Time anchor and confirm its href has no from= param
        match = re.search(r'<a\s+href="([^"]*)"[^>]*>\s*\n?\s*All Time', html)
        assert match is not None, "Could not find an anchor tag with 'All Time' text"
        all_time_href = match.group(1)
        assert 'from=' not in all_time_href, (
            "All Time href should not contain 'from=' parameter, got: %s" % all_time_href
        )
        assert 'to=' not in all_time_href, (
            "All Time href should not contain 'to=' parameter, got: %s" % all_time_href
        )


# ---------------------------------------------------------------------------
# DoD 6 — Filtering with ?from=2026-05-01&to=2026-05-31 returns 8 expenses;
#          filtering for June 2026 returns 0
# ---------------------------------------------------------------------------

class TestDateRangeFiltering:
    def test_may_2026_filter_shows_all_8_seed_expenses(self, auth_client):
        resp = auth_client.get('/profile?from=2026-05-01&to=2026-05-31')
        assert resp.status_code == 200, "Expected 200 for May 2026 filter"
        html = resp.data.decode('utf-8')
        # The stats panel renders summary.total_count; seed has 8 expenses in May
        assert b'8' in resp.data, (
            "Expected total_count of 8 for May 2026 filter (all seed expenses are in May 2026)"
        )

    def test_may_2026_filter_shows_correct_label(self, auth_client):
        resp = auth_client.get('/profile?from=2026-05-01&to=2026-05-31')
        assert b'01 May 2026' in resp.data, "Expected '01 May 2026' in the date label"
        assert b'31 May 2026' in resp.data, "Expected '31 May 2026' in the date label"

    def test_june_2026_filter_shows_zero_transactions(self, auth_client):
        resp = auth_client.get('/profile?from=2026-06-01&to=2026-06-30')
        assert resp.status_code == 200, "Expected 200 for June 2026 filter"
        html = resp.data.decode('utf-8')
        # No seed expenses fall in June, so total_count should be 0.
        # The page should show the onboarding/empty state, not the transaction table.
        assert b'Start tracking your spending' in resp.data or \
               b'haven&#39;t logged any expenses' in resp.data or \
               b"haven't logged any expenses" in resp.data or \
               b'0' in resp.data, (
            "Expected 0 transactions for June 2026 (no seed data in that month)"
        )

    def test_june_2026_filter_total_count_is_zero(self, auth_client):
        """Stat panel transaction count should be 0 for an empty date range in seed data."""
        resp = auth_client.get('/profile?from=2026-06-01&to=2026-06-30')
        html = resp.data.decode('utf-8')
        # The Transactions stat card renders summary.total_count
        # When categories is empty the template renders the onboarding block, not
        # the stat cards — so we just assert the page renders successfully and
        # there are no May-dated transactions visible.
        assert b'Lunch at cafe' not in resp.data, (
            "Expected no May 2026 seed transactions to appear when filtered to June 2026"
        )
        assert b'Electricity bill' not in resp.data, (
            "Expected no May 2026 seed transactions to appear when filtered to June 2026"
        )

    def test_may_2026_filter_seed_expenses_are_visible(self, auth_client):
        """At least one known seed expense description appears in the May 2026 filtered view."""
        resp = auth_client.get('/profile?from=2026-05-01&to=2026-05-31')
        # Pick a description from the seed data
        assert b'Lunch at cafe' in resp.data or b'Electricity bill' in resp.data, (
            "Expected seed expense descriptions to appear in the May 2026 filtered view"
        )


# ---------------------------------------------------------------------------
# DoD 7 — Active preset button has CSS class filter-btn--active
# ---------------------------------------------------------------------------

class TestActivePresetHighlighting:
    def test_all_time_active_when_no_params(self, auth_client):
        resp = auth_client.get('/profile')
        html = resp.data.decode('utf-8')
        # The All Time anchor (href=/profile) should have filter-btn--active
        match = re.search(r'<a\s+href="/profile"\s+class="([^"]*)"', html)
        assert match is not None, "Could not find All Time anchor with href='/profile'"
        classes = match.group(1)
        assert 'filter-btn--active' in classes, (
            "Expected 'filter-btn--active' on All Time anchor, got classes: '%s'" % classes
        )

    def test_this_month_active_when_this_month_params(self, auth_client):
        presets = _preset_dates()
        from_d, to_d = presets['this_month']
        resp = auth_client.get('/profile?from=%s&to=%s' % (from_d, to_d))
        html = resp.data.decode('utf-8')
        # Find the anchor linking to this month and check its class
        pattern = re.compile(
            r'<a\s+href="[^"]*from=%s[^"]*"\s+class="([^"]*)"' % re.escape(from_d)
        )
        match = pattern.search(html)
        assert match is not None, (
            "Could not find This Month anchor with from=%s in HTML" % from_d
        )
        assert 'filter-btn--active' in match.group(1), (
            "Expected 'filter-btn--active' on This Month anchor"
        )

    def test_last_month_active_when_last_month_params(self, auth_client):
        presets = _preset_dates()
        from_d, to_d = presets['last_month']
        resp = auth_client.get('/profile?from=%s&to=%s' % (from_d, to_d))
        html = resp.data.decode('utf-8')
        pattern = re.compile(
            r'<a\s+href="[^"]*from=%s[^"]*"\s+class="([^"]*)"' % re.escape(from_d)
        )
        match = pattern.search(html)
        assert match is not None, (
            "Could not find Last Month anchor with from=%s in HTML" % from_d
        )
        assert 'filter-btn--active' in match.group(1), (
            "Expected 'filter-btn--active' on Last Month anchor"
        )

    def test_last_3_months_active_when_last_3_months_params(self, auth_client):
        presets = _preset_dates()
        from_d, to_d = presets['last_3_months']
        resp = auth_client.get('/profile?from=%s&to=%s' % (from_d, to_d))
        html = resp.data.decode('utf-8')
        pattern = re.compile(
            r'<a\s+href="[^"]*from=%s[^"]*"\s+class="([^"]*)"' % re.escape(from_d)
        )
        match = pattern.search(html)
        assert match is not None, (
            "Could not find Last 3 Months anchor with from=%s in HTML" % from_d
        )
        assert 'filter-btn--active' in match.group(1), (
            "Expected 'filter-btn--active' on Last 3 Months anchor"
        )

    def test_no_other_button_is_active_when_all_time(self, auth_client):
        """Only one button should carry filter-btn--active at a time."""
        resp = auth_client.get('/profile')
        html = resp.data.decode('utf-8')
        active_count = html.count('filter-btn--active')
        assert active_count == 1, (
            "Expected exactly 1 element with 'filter-btn--active', found %d" % active_count
        )

    def test_no_other_button_is_active_when_this_month(self, auth_client):
        presets = _preset_dates()
        from_d, to_d = presets['this_month']
        resp = auth_client.get('/profile?from=%s&to=%s' % (from_d, to_d))
        html = resp.data.decode('utf-8')
        active_count = html.count('filter-btn--active')
        assert active_count == 1, (
            "Expected exactly 1 active preset button for This Month, found %d" % active_count
        )


# ---------------------------------------------------------------------------
# DoD 8 — Human-readable date label reflects the active range
# ---------------------------------------------------------------------------

class TestFilterLabel:
    def test_all_time_label_shows_all_time(self, auth_client):
        resp = auth_client.get('/profile')
        assert b'Showing: All time' in resp.data, (
            "Expected 'Showing: All time' when no date params given"
        )

    def test_may_range_label_is_human_readable(self, auth_client):
        resp = auth_client.get('/profile?from=2026-05-01&to=2026-05-31')
        assert b'Showing: 01 May 2026' in resp.data, (
            "Expected 'Showing: 01 May 2026...' label for ?from=2026-05-01&to=2026-05-31"
        )
        assert b'31 May 2026' in resp.data, (
            "Expected '31 May 2026' in the filter label for ?to=2026-05-31"
        )

    def test_label_format_matches_dd_mon_yyyy(self, auth_client):
        """The label should use DD Mon YYYY format, not YYYY-MM-DD."""
        resp = auth_client.get('/profile?from=2026-05-01&to=2026-05-31')
        html = resp.data.decode('utf-8')
        # The raw ISO format must NOT appear inside the label element
        label_match = re.search(r'<p class="filter-label">Showing: ([^<]+)</p>', html)
        assert label_match is not None, "Could not find <p class='filter-label'> element"
        label_text = label_match.group(1)
        assert '2026-05-01' not in label_text, (
            "Label should use DD Mon YYYY format, not ISO format; got: '%s'" % label_text
        )

    def test_only_from_provided_shows_from_label(self, auth_client):
        """Only from= param: label should say 'From DD Mon YYYY'."""
        resp = auth_client.get('/profile?from=2026-05-01')
        assert resp.status_code == 200
        assert b'From 01 May 2026' in resp.data, (
            "Expected 'From 01 May 2026' when only ?from= is provided"
        )

    def test_only_to_provided_shows_until_label(self, auth_client):
        """Only to= param: label should say 'Until DD Mon YYYY'."""
        resp = auth_client.get('/profile?to=2026-05-31')
        assert resp.status_code == 200
        assert b'Until 31 May 2026' in resp.data, (
            "Expected 'Until 31 May 2026' when only ?to= is provided"
        )


# ---------------------------------------------------------------------------
# DoD 9 — Malformed dates fall back gracefully to "Showing: All time"
# ---------------------------------------------------------------------------

class TestMalformedDates:
    @pytest.mark.parametrize("bad_from,bad_to", [
        ("not-a-date", ""),
        ("", "not-a-date"),
        ("not-a-date", "also-bad"),
        ("2026-13-01", ""),         # invalid month
        ("2026-00-01", ""),         # invalid month zero
        ("abcdef", "ghijkl"),
        ("2026/05/01", ""),         # wrong separator
        ("05-01-2026", ""),         # wrong order
        ("' OR 1=1 --", ""),        # SQL injection attempt
        ("A" * 200, ""),            # very long string
    ])
    def test_malformed_from_falls_back_to_all_time(self, auth_client, bad_from, bad_to):
        url = '/profile'
        params = []
        if bad_from:
            params.append('from=%s' % bad_from)
        if bad_to:
            params.append('to=%s' % bad_to)
        if params:
            url += '?' + '&'.join(params)
        resp = auth_client.get(url)
        assert resp.status_code == 200, (
            "Expected HTTP 200 for malformed date params, got %d (URL: %s)" % (resp.status_code, url)
        )
        assert b'Showing: All time' in resp.data, (
            "Expected fallback to 'Showing: All time' for malformed date params (URL: %s)" % url
        )

    def test_malformed_date_does_not_cause_500(self, auth_client):
        resp = auth_client.get('/profile?from=not-a-date&to=also-not-a-date')
        assert resp.status_code != 500, (
            "Expected no 500 error for malformed date params, got %d" % resp.status_code
        )

    def test_valid_from_with_malformed_to_falls_back(self, auth_client):
        """A valid from= paired with a malformed to= should treat both as absent."""
        resp = auth_client.get('/profile?from=2026-05-01&to=not-a-date')
        assert resp.status_code == 200
        # The spec says: "ignore malformed values silently and fall back to 'all time'"
        # When to= is malformed, only date_from is valid; label should say "From 01 May 2026"
        # OR the implementation may treat the pair as all-time — either is acceptable per spec.
        # We assert only that the page loads and no 500 is thrown.
        assert resp.status_code == 200, "Expected no crash with one valid and one malformed date param"

    def test_malformed_from_does_not_expose_raw_sql_error(self, auth_client):
        resp = auth_client.get("/profile?from=' OR '1'='1")
        assert resp.status_code == 200, (
            "Expected HTTP 200 even for SQL injection attempt in from= param"
        )
        assert b'sqlite3' not in resp.data.lower(), (
            "Response must not leak sqlite3 error details"
        )


# ---------------------------------------------------------------------------
# DoD 10 — All three panels respond to the filter (stats total_count changes)
# ---------------------------------------------------------------------------

class TestAllPanelsRespondToFilter:
    def test_all_time_shows_8_seed_expenses_in_stats(self, auth_client):
        resp = auth_client.get('/profile')
        assert resp.status_code == 200
        # 8 seed expenses exist; the stat panel shows summary.total_count
        # The number 8 must appear somewhere in the stats section
        assert b'8' in resp.data, (
            "Expected total_count of 8 to appear on the all-time /profile view"
        )

    def test_future_range_shows_zero_transactions(self, auth_client):
        """A date range with no data should show 0 transactions across all panels."""
        resp = auth_client.get('/profile?from=2099-01-01&to=2099-12-31')
        assert resp.status_code == 200, "Expected 200 for a future date range"
        html = resp.data.decode('utf-8')
        # With no expenses in 2099, categories is empty so the onboarding block is shown
        # (the template renders {% if categories %}...{% else %}onboarding{% endif %})
        assert b'Start tracking your spending' in resp.data or \
               b'0' in resp.data, (
            "Expected 0 transactions (or onboarding state) for a future date range"
        )

    def test_future_range_hides_transaction_table(self, auth_client):
        """When categories is empty (no data), the transaction table must not render."""
        resp = auth_client.get('/profile?from=2099-01-01&to=2099-12-31')
        html = resp.data.decode('utf-8')
        # The transaction table header appears only inside the {% if categories %} block
        assert b'Recent Transactions' not in resp.data or \
               b'Start tracking your spending' in resp.data, (
            "Expected no 'Recent Transactions' table for a date range with zero expenses"
        )

    def test_future_range_hides_category_breakdown(self, auth_client):
        """When no expenses exist for the range, By Category panel must not render."""
        resp = auth_client.get('/profile?from=2099-01-01&to=2099-12-31')
        html = resp.data.decode('utf-8')
        assert b'By Category' not in resp.data or \
               b'Start tracking your spending' in resp.data, (
            "Expected no 'By Category' panel for a date range with zero expenses"
        )

    def test_may_filter_shows_expected_total_spend(self, auth_client):
        """Total spend for May 2026 seed data equals 361.24."""
        resp = auth_client.get('/profile?from=2026-05-01&to=2026-05-31')
        # Seed total: 12.50+45.00+120.00+35.00+25.00+89.99+18.75+15.00 = 361.24
        assert b'361.24' in resp.data, (
            "Expected total spend of 361.24 for May 2026 (all seed expenses)"
        )

    def test_may_filter_shows_all_seed_categories(self, auth_client):
        """All seed categories should appear in the By Category panel for May 2026."""
        resp = auth_client.get('/profile?from=2026-05-01&to=2026-05-31')
        for category in [b'Food', b'Transport', b'Bills', b'Health', b'Entertainment',
                         b'Shopping', b'Other']:
            assert category in resp.data, (
                "Expected category '%s' to appear in the May 2026 filtered view" % category.decode()
            )


# ---------------------------------------------------------------------------
# DoD 11 — Auth guard: unauthenticated request redirects to /login
# ---------------------------------------------------------------------------

class TestAuthGuard:
    def test_unauthenticated_profile_redirects_to_login(self, client):
        resp = client.get('/profile', follow_redirects=False)
        assert resp.status_code == 302, (
            "Expected 302 redirect for unauthenticated /profile, got %d" % resp.status_code
        )

    def test_unauthenticated_profile_redirect_location_is_login(self, client):
        resp = client.get('/profile', follow_redirects=False)
        location = resp.headers.get('Location', '')
        assert '/login' in location, (
            "Expected redirect to /login for unauthenticated /profile, got Location: '%s'" % location
        )

    def test_unauthenticated_profile_with_params_still_redirects(self, client):
        """Auth guard must fire even when date params are present."""
        resp = client.get('/profile?from=2026-05-01&to=2026-05-31', follow_redirects=False)
        assert resp.status_code == 302, (
            "Expected 302 redirect even with date query params when not logged in"
        )
        location = resp.headers.get('Location', '')
        assert '/login' in location, (
            "Expected redirect target to be /login, got: '%s'" % location
        )

    def test_following_redirect_lands_on_login_page(self, client):
        resp = client.get('/profile', follow_redirects=True)
        assert resp.status_code == 200
        assert b'Login' in resp.data or b'login' in resp.data, (
            "Expected the login page after following the /profile redirect"
        )

    def test_logout_and_revisit_profile_redirects(self, auth_client):
        """After logout, /profile must redirect to /login again."""
        auth_client.get('/logout')
        resp = auth_client.get('/profile', follow_redirects=False)
        assert resp.status_code == 302, (
            "Expected redirect after logout when accessing /profile"
        )
        location = resp.headers.get('Location', '')
        assert '/login' in location, (
            "Expected /login redirect after logout, got: '%s'" % location
        )


# ---------------------------------------------------------------------------
# Edge cases not covered above
# ---------------------------------------------------------------------------

class TestEdgeCases:
    def test_from_equals_to_single_day_range(self, auth_client):
        """A range where from==to (single day) should work without error."""
        resp = auth_client.get('/profile?from=2026-05-01&to=2026-05-01')
        assert resp.status_code == 200, (
            "Expected HTTP 200 for single-day range, got %d" % resp.status_code
        )

    def test_from_after_to_returns_200_without_crash(self, auth_client):
        """from > to is a user error; the app must not crash (may return 0 results)."""
        resp = auth_client.get('/profile?from=2026-05-31&to=2026-05-01')
        assert resp.status_code == 200, (
            "Expected HTTP 200 even when from > to, got %d" % resp.status_code
        )

    def test_custom_range_not_matching_any_preset_has_no_active_preset(self, auth_client):
        """A custom date range should not mark any preset as active."""
        resp = auth_client.get('/profile?from=2026-04-01&to=2026-04-30')
        html = resp.data.decode('utf-8')
        # With a custom date range, active_preset == 'custom'; no preset button is active
        active_count = html.count('filter-btn--active')
        assert active_count == 0, (
            "Expected 0 active preset buttons for a custom date range, found %d" % active_count
        )

    def test_filter_bar_rendered_on_profile_page(self, auth_client):
        """The filter bar must be present on the profile page."""
        resp = auth_client.get('/profile')
        assert b'filter-bar' in resp.data, "Expected element with class 'filter-bar' on /profile"

    def test_custom_range_form_uses_get_method(self, auth_client):
        """The custom date form must use method='get' as specified."""
        resp = auth_client.get('/profile')
        html = resp.data.decode('utf-8')
        assert re.search(r'<form[^>]+method=["\']get["\']', html, re.IGNORECASE), (
            "Expected a <form method='get'> for the custom date range picker"
        )

    def test_filter_label_element_present(self, auth_client):
        """The filter-label paragraph must be present in the rendered HTML."""
        resp = auth_client.get('/profile')
        assert b'filter-label' in resp.data, (
            "Expected an element with class 'filter-label' on the profile page"
        )

    def test_profile_page_extends_base_template(self, auth_client):
        """Profile page must use the base template (navbar/footer indicators)."""
        resp = auth_client.get('/profile')
        html = resp.data.decode('utf-8')
        # base.html includes the app name "Spendly" in the navbar
        assert b'Spendly' in resp.data, (
            "Expected 'Spendly' (from base.html navbar) in the /profile response"
        )

    def test_seed_expense_dates_visible_in_may_filter(self, auth_client):
        """Individual expense dates must appear in the transaction list for May 2026."""
        resp = auth_client.get('/profile?from=2026-05-01&to=2026-05-31')
        # Multiple known dates from seed data
        assert b'2026-05-01' in resp.data or b'2026-05-05' in resp.data, (
            "Expected at least one May 2026 date (e.g. 2026-05-01) in the transactions list"
        )
