import sqlite3
from flask import Flask, render_template, request, redirect, url_for, session
from werkzeug.security import generate_password_hash, check_password_hash
from database.db import init_db, seed_db, create_user, get_user_by_email, get_user_by_id, get_expense_summary, get_expenses_by_category, get_recent_expenses

app = Flask(__name__)
app.secret_key = "dev-secret-change-in-production"

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


@app.route("/profile")
def profile():
    if not session.get("user_id"):
        return redirect(url_for("login"))
    from datetime import datetime
    user            = get_user_by_id(session["user_id"])
    summary         = get_expense_summary(session["user_id"])
    categories      = get_expenses_by_category(session["user_id"])
    recent_expenses = get_recent_expenses(session["user_id"])
    member_since    = datetime.strptime(user["created_at"][:7], "%Y-%m").strftime("%B %Y")
    return render_template("profile.html", user=user, summary=summary,
                           categories=categories, recent_expenses=recent_expenses,
                           member_since=member_since)


@app.route("/expenses/add")
def add_expense():
    return "Add expense — coming in Step 7"


@app.route("/expenses/<int:id>/edit")
def edit_expense(id):
    return "Edit expense — coming in Step 8"


@app.route("/expenses/<int:id>/delete")
def delete_expense(id):
    return "Delete expense — coming in Step 9"




if __name__ == "__main__":
    app.run(debug=True, port=5001)
