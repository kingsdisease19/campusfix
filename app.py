# ============================================================
#  CampusFix - app.py  (updated with Jobs marketplace)
#  Save this file in:  campusfix/app.py
#  Run with:          python app.py
# ============================================================

from flask import Flask, render_template, request, redirect, url_for, session, flash
from werkzeug.security import generate_password_hash, check_password_hash
import psycopg
from psycopg.rows import dict_row

# ── App setup ────────────────────────────────────────────────
app = Flask(__name__)
app.secret_key = "campusfix_secret_2026"
# In a real app, load this from environment variables
# Updated connection details based on your request
DB_HOST = "localhost"
DB_NAME = "campusfix"
DB_USER = "postgres"

# ── Database helpers ─────────────────────────────────────────

def get_db():
    """Open and return a database connection."""
    # We use psycopg (v3) instead of psycopg2 because psycopg2 fails to 
    # compile on your Windows machine, but the API and connection are identical!
    conn = psycopg.connect(
        host=DB_HOST,
        dbname=DB_NAME,
        user=DB_USER,
        row_factory=dict_row
    )
    return conn


def init_db():
    """Create all tables on first run if they don't already exist."""
    conn = get_db()
    cur = conn.cursor()

    # Users table
    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id         SERIAL PRIMARY KEY,
            name       VARCHAR(100) NOT NULL,
            email      VARCHAR(100) NOT NULL UNIQUE,
            password   TEXT    NOT NULL,
            university VARCHAR(150) NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Jobs table (NEW)
    # user_id links each job back to the student who posted it
    cur.execute("""
        CREATE TABLE IF NOT EXISTS jobs (
            id          SERIAL PRIMARY KEY,
            title       VARCHAR(200) NOT NULL,
            description TEXT    NOT NULL,
            category    VARCHAR(100) NOT NULL,
            budget      VARCHAR(50) NOT NULL,
            university  VARCHAR(150) NOT NULL,
            user_id     INTEGER NOT NULL,
            created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)

    conn.commit()
    cur.close()
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
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        """SELECT jobs.*, users.name AS poster_name, users.university AS poster_university
           FROM jobs
           JOIN users ON jobs.user_id = users.id
           ORDER BY jobs.created_at DESC LIMIT 3"""
    )
    latest_jobs = cur.fetchall()
    cur.close()
    conn.close()
    return render_template("index.html", jobs=latest_jobs)


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name       = request.form["name"].strip()
        email      = request.form["email"].strip().lower()
        password   = request.form["password"]
        university = request.form["university"].strip()

        if not name or not email or not password or not university:
            flash("Please fill in all fields.", "danger")
            return redirect(url_for("register"))

        if len(password) < 6:
            flash("Password must be at least 6 characters.", "danger")
            return redirect(url_for("register"))

        hashed_pw = generate_password_hash(password)

        try:
            conn = get_db()
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO users (name, email, password, university) VALUES (%s, %s, %s, %s)",
                (name, email, hashed_pw, university)
            )
            conn.commit()
            cur.close()
            conn.close()
            flash("Account created! Please log in.", "success")
            return redirect(url_for("login"))
        except psycopg.IntegrityError:
            flash("That email is already registered. Try logging in.", "warning")
            return redirect(url_for("register"))

    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email    = request.form["email"].strip().lower()
        password = request.form["password"]

        conn = get_db()
        cur = conn.cursor()
        cur.execute(
            "SELECT * FROM users WHERE email = %s", (email,)
        )
        user = cur.fetchone()
        cur.close()
        conn.close()

        if user and check_password_hash(user["password"], password):
            session["user_id"]   = user["id"]
            session["user_name"] = user["name"]
            session["user_university"] = user["university"]
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


@app.route("/dashboard")
def dashboard():
    """Show the user's dashboard with their posted jobs."""
    if login_required():
        flash("Please log in to view your dashboard.", "warning")
        return redirect(url_for("login"))
        
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        "SELECT * FROM jobs WHERE user_id = %s ORDER BY created_at DESC", 
        (session["user_id"],)
    )
    user_jobs = cur.fetchall()
    cur.close()
    conn.close()
    
    return render_template(
        "dashboard.html", 
        name=session.get("user_name"),
        university=session.get("user_university"),
        jobs=user_jobs
    )


@app.route("/settings", methods=["GET", "POST"])
def settings():
    """Allow the user to update their profile settings."""
    if login_required():
        flash("Please log in to view your settings.", "warning")
        return redirect(url_for("login"))
        
    conn = get_db()
    cur = conn.cursor()
    
    if request.method == "POST":
        name = request.form.get("name").strip()
        university = request.form.get("university").strip()
        
        if not name or not university:
            flash("Name and University are required.", "danger")
        else:
            cur.execute(
                "UPDATE users SET name = %s, university = %s WHERE id = %s",
                (name, university, session["user_id"])
            )
            
            # If the user updated their university, update their existing jobs too
            cur.execute(
                "UPDATE jobs SET university = %s WHERE user_id = %s",
                (university, session["user_id"])
            )
            
            conn.commit()
            
            session["user_name"] = name
            session["user_university"] = university
            flash("Your settings have been updated successfully.", "success")
            
    # Fetch current user info to pre-fill the form
    cur.execute("SELECT * FROM users WHERE id = %s", (session["user_id"],))
    user = cur.fetchone()
    
    cur.close()
    conn.close()
    
    return render_template(
        "settings.html",
        user=user,
        name=session.get("user_name")
    )


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
        cur = conn.cursor()
        cur.execute(
            """INSERT INTO jobs (title, description, category, budget, university, user_id)
               VALUES (%s, %s, %s, %s, %s, %s)""",
            (title, description, category, budget, session["user_university"], session["user_id"])
        )
        conn.commit()
        cur.close()
        conn.close()

        flash("Your job has been posted successfully!", "success")
        return redirect(url_for("jobs"))

    return render_template("post_job.html", name=session.get("user_name"))


# ---------- Browse All Jobs ----------
@app.route("/jobs")
def jobs():
    # Optional: filter by category or university from URL
    category_filter = request.args.get("category", "")
    university_filter = request.args.get("university", "")

    conn = get_db()
    cur = conn.cursor()

    # Get distinct universities for the dropdown filter
    cur.execute("SELECT DISTINCT university FROM users WHERE university IS NOT NULL AND university != '' ORDER BY university")
    universities_rows = cur.fetchall()
    universities = [row["university"] for row in universities_rows]

    query = """SELECT jobs.*, users.name AS poster_name, users.university AS poster_university
               FROM jobs
               JOIN users ON jobs.user_id = users.id
               WHERE 1=1"""
    params = []

    if category_filter:
        query += " AND jobs.category = %s"
        params.append(category_filter)
        
    if university_filter:
        query += " AND users.university = %s"
        params.append(university_filter)

    query += " ORDER BY jobs.created_at DESC"
    cur.execute(query, tuple(params))
    all_jobs = cur.fetchall()

    cur.close()
    conn.close()

    return render_template(
        "jobs.html",
        jobs=all_jobs,
        name=session.get("user_name"),
        selected_category=category_filter,
        selected_university=university_filter,
        universities=universities
    )


# ---------- Job Details ----------
@app.route("/job/<int:job_id>")
def job_details(job_id):
    conn = get_db()
    cur = conn.cursor()

    # Fetch the single job by its ID, plus the poster's name and university via JOIN
    cur.execute(
        """SELECT jobs.*, users.name AS poster_name, users.university AS poster_university
           FROM jobs
           JOIN users ON jobs.user_id = users.id
           WHERE jobs.id = %s""",
        (job_id,)
    )
    job = cur.fetchone()

    cur.close()
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