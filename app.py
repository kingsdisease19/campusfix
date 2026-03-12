# ============================================================
#  CampusFix - app.py  (updated with Jobs marketplace)
#  Save this file in:  campusfix/app.py
#  Run with:          python app.py
# ============================================================

from flask import Flask, render_template, request, redirect, url_for, session, flash
from werkzeug.security import generate_password_hash, check_password_hash
import sqlite3

# ── App setup ────────────────────────────────────────────────
app = Flask(__name__)
app.secret_key = "campusfix_secret_2026"
DATABASE = "campusfix.db"


# ── Database helpers ─────────────────────────────────────────

def get_db():
    """Open and return a database connection."""
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row   # access columns by name e.g. job["title"]
    return conn


def init_db():
    """Create all tables on first run if they don't already exist."""
    conn = get_db()

    # Users table (unchanged from before)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id       INTEGER PRIMARY KEY AUTOINCREMENT,
            name     TEXT    NOT NULL,
            email    TEXT    NOT NULL UNIQUE,
            password TEXT    NOT NULL
        )
    """)

    # Jobs table (NEW)
    # user_id links each job back to the student who posted it
    conn.execute("""
        CREATE TABLE IF NOT EXISTS jobs (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            title       TEXT    NOT NULL,
            description TEXT    NOT NULL,
            category    TEXT    NOT NULL,
            budget      REAL    NOT NULL,
            user_id     INTEGER NOT NULL,
            created_at  DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)

    conn.commit()
    conn.close()


# ── Login guard ───────────────────────────────────────────────
def login_required():
    """Returns True if the user is NOT logged in."""
    return "user_id" not in session


# ═══════════════════════════════════════════════════════════════
#  AUTH ROUTES
# ═══════════════════════════════════════════════════════════════

@app.route("/")
def index():
    name = session.get("user_name")
    conn = get_db()
    latest_jobs = conn.execute(
        """SELECT jobs.*, users.name AS poster_name
           FROM jobs
           JOIN users ON jobs.user_id = users.id
           ORDER BY jobs.created_at DESC LIMIT 3"""
    ).fetchall()
    conn.close()
    return render_template("index.html", name=name, jobs=latest_jobs)


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name     = request.form["name"].strip()
        email    = request.form["email"].strip().lower()
        password = request.form["password"]

        if not name or not email or not password:
            flash("Please fill in all fields.", "danger")
            return redirect(url_for("register"))

        if len(password) < 6:
            flash("Password must be at least 6 characters.", "danger")
            return redirect(url_for("register"))

        hashed_pw = generate_password_hash(password)

        try:
            conn = get_db()
            conn.execute(
                "INSERT INTO users (name, email, password) VALUES (?, ?, ?)",
                (name, email, hashed_pw)
            )
            conn.commit()
            conn.close()
            flash("Account created! Please log in.", "success")
            return redirect(url_for("login"))
        except sqlite3.IntegrityError:
            flash("That email is already registered. Try logging in.", "warning")
            return redirect(url_for("register"))

    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email    = request.form["email"].strip().lower()
        password = request.form["password"]

        conn = get_db()
        user = conn.execute(
            "SELECT * FROM users WHERE email = ?", (email,)
        ).fetchone()
        conn.close()

        if user and check_password_hash(user["password"], password):
            session["user_id"]   = user["id"]
            session["user_name"] = user["name"]
            flash(f"Welcome back, {user['name']}!", "success")
            return redirect(url_for("index"))
        else:
            flash("Incorrect email or password.", "danger")
            return redirect(url_for("login"))

    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    flash("You have been logged out.", "info")
    return redirect(url_for("login"))


# ═══════════════════════════════════════════════════════════════
#  JOBS ROUTES
# ═══════════════════════════════════════════════════════════════

# ---------- Post a Job ----------
@app.route("/post-job", methods=["GET", "POST"])
def post_job():
    # Redirect to login if not logged in
    if login_required():
        flash("Please log in to post a job.", "warning")
        return redirect(url_for("login"))

    if request.method == "POST":
        title       = request.form["title"].strip()
        description = request.form["description"].strip()
        category    = request.form["category"]
        budget      = request.form["budget"].strip()

        # Validate all fields are filled
        if not title or not description or not category or not budget:
            flash("Please fill in all fields.", "danger")
            return redirect(url_for("post_job"))

        # Make sure budget is a valid positive number
        try:
            budget = float(budget)
            if budget <= 0:
                raise ValueError
        except ValueError:
            flash("Budget must be a positive number e.g. 50", "danger")
            return redirect(url_for("post_job"))

        # Save job to the database, linking it to the logged-in user
        conn = get_db()
        conn.execute(
            """INSERT INTO jobs (title, description, category, budget, user_id)
               VALUES (?, ?, ?, ?, ?)""",
            (title, description, category, budget, session["user_id"])
        )
        conn.commit()
        conn.close()

        flash("Your job has been posted successfully!", "success")
        return redirect(url_for("jobs"))

    return render_template("post_job.html", name=session.get("user_name"))


# ---------- Browse All Jobs ----------
@app.route("/jobs")
def jobs():
    # Optional: filter by category from URL e.g. /jobs?category=Networking
    category_filter = request.args.get("category", "")

    conn = get_db()

    if category_filter:
        all_jobs = conn.execute(
            """SELECT jobs.*, users.name AS poster_name
               FROM jobs
               JOIN users ON jobs.user_id = users.id
               WHERE jobs.category = ?
               ORDER BY jobs.created_at DESC""",
            (category_filter,)
        ).fetchall()
    else:
        # JOIN lets us display the poster's name on each card
        all_jobs = conn.execute(
            """SELECT jobs.*, users.name AS poster_name
               FROM jobs
               JOIN users ON jobs.user_id = users.id
               ORDER BY jobs.created_at DESC"""
        ).fetchall()

    conn.close()

    return render_template(
        "jobs.html",
        jobs=all_jobs,
        name=session.get("user_name"),
        selected_category=category_filter
    )


# ---------- Job Details ----------
@app.route("/job/<int:job_id>")
def job_details(job_id):
    conn = get_db()

    # Fetch the single job by its ID, plus the poster's name via JOIN
    job = conn.execute(
        """SELECT jobs.*, users.name AS poster_name
           FROM jobs
           JOIN users ON jobs.user_id = users.id
           WHERE jobs.id = ?""",
        (job_id,)
    ).fetchone()

    conn.close()

    if not job:
        flash("Job not found.", "danger")
        return redirect(url_for("jobs"))

    return render_template(
        "job_details.html",
        job=job,
        name=session.get("user_name")
    )


# ── Start ────────────────────────────────────────────────────
if __name__ == "__main__":
    init_db()   # Creates users table AND jobs table automatically
    print("CampusFix is running at http://127.0.0.1:5000")
    app.run(debug=True)