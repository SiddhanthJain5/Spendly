import os
import re
import sqlite3
import calendar
from datetime import date, datetime, timedelta
from flask import Flask, render_template, request, redirect, url_for, session, abort, flash
from werkzeug.security import generate_password_hash, check_password_hash
from database.db import init_db, seed_db, create_user, create_expense, get_user_by_email, get_user_by_id, get_expense_by_id, update_expense, delete_expense as remove_expense, get_expense_summary, get_expenses_by_category, get_recent_expenses

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-change-in-production")

with app.app_context():
    init_db()
    seed_db()


# ------------------------------------------------------------------ #
# Routes                                                              #
# ------------------------------------------------------------------ #

@app.route("/")
def landing():
    return render_template("landing.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "GET":
        return render_template("register.html")

    name     = request.form.get("name", "").strip()
    email    = request.form.get("email", "").strip()
    password = request.form.get("password", "")
    confirm  = request.form.get("confirm_password", "")

    if not name or not email:
        return render_template("register.html", error="Name and email are required.", name=name, email=email)
    if len(password) < 8:
        return render_template("register.html", error="Password must be at least 8 characters.", name=name, email=email)
    if password != confirm:
        return render_template("register.html", error="Passwords do not match.", name=name, email=email)

    password_hash = generate_password_hash(password)
    try:
        create_user(name, email, password_hash)
    except sqlite3.IntegrityError:
        return render_template("register.html", error="An account with that email already exists.", name=name, email=email)

    flash("Account created successfully! Sign in to continue.", "success")
    return redirect(url_for("login"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "GET":
        return render_template("login.html")

    email    = request.form.get("email", "").strip()
    password = request.form.get("password", "")

    user = get_user_by_email(email)
    if not user or not check_password_hash(user["password_hash"], password):
        return render_template("login.html", error="Invalid email or password.")

    session["user_id"]   = user["id"]
    session["user_name"] = user["name"]
    return redirect(url_for("profile"))


# ------------------------------------------------------------------ #
# Dev convenience — remove before production                          #
# ------------------------------------------------------------------ #

@app.route("/dev/autologin")
def dev_autologin():
    if not app.debug:
        abort(404)
    user = get_user_by_email("demo@spendly.com")
    if user:
        session["user_id"]   = user["id"]
        session["user_name"] = user["name"]
    return redirect(url_for("profile"))


# ------------------------------------------------------------------ #
# Placeholder routes — students will implement these                  #
# ------------------------------------------------------------------ #

@app.route("/terms")
def terms():
    return render_template("terms.html")


@app.route("/privacy")
def privacy():
    return render_template("privacy.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("landing"))


CATEGORIES = ["Food", "Transport", "Bills", "Health", "Entertainment", "Shopping", "Other"]


def _parse_date(s):
    if not s or not re.match(r'^\d{4}-\d{2}-\d{2}$', s):
        return None
    try:
        datetime.strptime(s, "%Y-%m-%d")
        return s
    except ValueError:
        return None


def _fmt_date(iso):
    return datetime.strptime(iso, "%Y-%m-%d").strftime("%d %b %Y")


def _build_preset_dates():
    today = date.today()
    # this month
    first_this = today.replace(day=1)
    last_this  = today.replace(day=calendar.monthrange(today.year, today.month)[1])
    # last month
    last_last  = first_this - timedelta(days=1)
    first_last = last_last.replace(day=1)
    # last 3 months: from the 1st of the month 3 months ago up to today
    # go back month by month
    m, y = today.month, today.year
    for _ in range(2):
        m -= 1
        if m == 0:
            m, y = 12, y - 1
    first_3m = date(y, m, 1)
    return {
        "this_month":    (first_this.isoformat(),  last_this.isoformat()),
        "last_month":    (first_last.isoformat(),  last_last.isoformat()),
        "last_3_months": (first_3m.isoformat(),    today.isoformat()),
    }


@app.route("/profile")
def profile():
    if not session.get("user_id"):
        return redirect(url_for("login"))

    user = get_user_by_id(session["user_id"])
    if user is None:
        session.clear()
        return redirect(url_for("login"))

    date_from = _parse_date(request.args.get("from", ""))
    date_to   = _parse_date(request.args.get("to",   ""))

    preset_dates = _build_preset_dates()

    if date_from is None and date_to is None:
        active_preset = "all_time"
    elif (date_from, date_to) == preset_dates["this_month"]:
        active_preset = "this_month"
    elif (date_from, date_to) == preset_dates["last_month"]:
        active_preset = "last_month"
    elif (date_from, date_to) == preset_dates["last_3_months"]:
        active_preset = "last_3_months"
    else:
        active_preset = "custom"

    if date_from and date_to:
        filter_label = f"{_fmt_date(date_from)} – {_fmt_date(date_to)}"
    elif date_from:
        filter_label = f"From {_fmt_date(date_from)}"
    elif date_to:
        filter_label = f"Until {_fmt_date(date_to)}"
    else:
        filter_label = "All time"

    summary         = get_expense_summary(session["user_id"], date_from, date_to)
    categories      = get_expenses_by_category(session["user_id"], date_from, date_to)
    recent_expenses = get_recent_expenses(session["user_id"], date_from=date_from, date_to=date_to)
    member_since    = datetime.strptime(user["created_at"][:7], "%Y-%m").strftime("%B %Y")

    return render_template(
        "profile.html",
        user=user, summary=summary, categories=categories,
        recent_expenses=recent_expenses, member_since=member_since,
        date_from=date_from, date_to=date_to,
        active_preset=active_preset, filter_label=filter_label,
        preset_dates=preset_dates,
    )


@app.route("/analytics")
def analytics():
    if not session.get("user_id"):
        return redirect(url_for("login"))
    return render_template("analytics.html")


@app.route("/expenses/add", methods=["GET", "POST"])
def add_expense():
    if not session.get("user_id"):
        return redirect(url_for("login"))

    today = date.today().isoformat()

    def render_form(error=None, amount="", category="", expense_date="", description=""):
        return render_template("add_expense.html", categories=CATEGORIES, today=today,
                               error=error, amount=amount, category=category,
                               date=expense_date, description=description)

    if request.method == "GET":
        return render_form()

    amount_raw   = request.form.get("amount", "").strip()
    category     = request.form.get("category", "").strip()
    expense_date = request.form.get("date", "").strip()
    description  = request.form.get("description", "").strip()

    try:
        amount = float(amount_raw)
        if amount <= 0:
            raise ValueError
    except ValueError:
        return render_form(error="Enter a valid amount greater than zero.",
                           amount=amount_raw, category=category, expense_date=expense_date, description=description)

    if category not in CATEGORIES:
        return render_form(error="Select a valid category.",
                           amount=amount_raw, category=category, expense_date=expense_date, description=description)

    parsed_date = _parse_date(expense_date)
    if not parsed_date or date.fromisoformat(parsed_date) > date.today():
        return render_form(error="Enter a valid date that is not in the future.",
                           amount=amount_raw, category=category, expense_date=expense_date, description=description)

    create_expense(session["user_id"], amount, category, parsed_date, description or None)
    flash("Expense added successfully.", "success")
    return redirect(url_for("profile"))


@app.route("/expenses/<int:id>/edit", methods=["GET", "POST"])
def edit_expense(id):
    if not session.get("user_id"):
        return redirect(url_for("login"))

    expense = get_expense_by_id(id, session["user_id"])
    if expense is None:
        abort(404)

    today = date.today().isoformat()

    def render_form(error=None, amount=None, category=None, expense_date=None, description=None):
        return render_template(
            "edit_expense.html", categories=CATEGORIES, today=today, expense=expense,
            error=error,
            amount=amount if amount is not None else expense["amount"],
            category=category if category is not None else expense["category"],
            date=expense_date if expense_date is not None else expense["date"],
            description=description if description is not None else (expense["description"] or ""),
        )

    if request.method == "GET":
        return render_form()

    amount_raw   = request.form.get("amount", "").strip()
    category     = request.form.get("category", "").strip()
    expense_date = request.form.get("date", "").strip()
    description  = request.form.get("description", "").strip()

    try:
        amount = float(amount_raw)
        if amount <= 0:
            raise ValueError
    except ValueError:
        return render_form(error="Enter a valid amount greater than zero.",
                           amount=amount_raw, category=category, expense_date=expense_date, description=description)

    if category not in CATEGORIES:
        return render_form(error="Select a valid category.",
                           amount=amount_raw, category=category, expense_date=expense_date, description=description)

    parsed_date = _parse_date(expense_date)
    if not parsed_date or date.fromisoformat(parsed_date) > date.today():
        return render_form(error="Enter a valid date that is not in the future.",
                           amount=amount_raw, category=category, expense_date=expense_date, description=description)

    update_expense(id, session["user_id"], amount, category, parsed_date, description or None)
    flash("Expense updated successfully.", "success")
    return redirect(url_for("profile"))


@app.route("/expenses/<int:id>/delete", methods=["POST"])
def delete_expense(id):
    if not session.get("user_id"):
        return redirect(url_for("login"))

    expense = get_expense_by_id(id, session["user_id"])
    if expense is None:
        abort(404)

    remove_expense(id, session["user_id"])
    flash("Expense deleted.", "success")
    return redirect(url_for("profile"))




if __name__ == "__main__":
    app.run(debug=True, port=5001)
