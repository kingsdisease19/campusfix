# ============================================================
#  CampusFix - app.py (Final Expanded Version)
# ============================================================

import os
import uuid
import datetime
from flask import Flask, render_template, request, redirect, url_for, session, flash, abort
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import psycopg
from psycopg.rows import dict_row

# ── App setup ────────────────────────────────────────────────
app = Flask(__name__)
app.secret_key = "campusfix_secret_2026_premium"
app.permanent_session_lifetime = datetime.timedelta(minutes=30)
app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024  # 10 MB max
UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), "static", "uploads")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "webp"}

def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS

# DB Config
DB_HOST = "localhost"
DB_NAME = "campusfix"
DB_USER = "postgres"
# Add password here if your postgres has one: password="your_password"

# ── Database Connection ───────────────────────────────────────
def get_db():
    conn = psycopg.connect(
        host=DB_HOST,
        dbname=DB_NAME,
        user=DB_USER,
        row_factory=dict_row
    )
    return conn

# ── Initial Schema ───────────────────────────────────────────
def init_db():
    conn = get_db()
    cur = conn.cursor()

    # Users
    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            name VARCHAR(100) NOT NULL,
            email VARCHAR(100) NOT NULL UNIQUE,
            password TEXT NOT NULL,
            university VARCHAR(150) NOT NULL,
            phone VARCHAR(20),
            bio TEXT,
            profile_pic TEXT,
            is_verified BOOLEAN DEFAULT FALSE,
            is_banned BOOLEAN DEFAULT FALSE,
            role VARCHAR(20) DEFAULT 'user',
            last_login TIMESTAMP,
            reset_token TEXT,
            reset_token_expiry TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Jobs
    cur.execute("""
        CREATE TABLE IF NOT EXISTS jobs (
            id SERIAL PRIMARY KEY,
            title VARCHAR(200) NOT NULL,
            description TEXT NOT NULL,
            category VARCHAR(100) NOT NULL,
            budget VARCHAR(50) NOT NULL,
            university VARCHAR(150) NOT NULL,
            image_filename VARCHAR(300),
            user_id INTEGER NOT NULL REFERENCES users(id),
            status VARCHAR(20) DEFAULT 'open',
            views INTEGER DEFAULT 0,
            is_featured BOOLEAN DEFAULT FALSE,
            deadline DATE,
            location VARCHAR(200),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Offers
    cur.execute("""
        CREATE TABLE IF NOT EXISTS offers (
            id SERIAL PRIMARY KEY,
            job_id INTEGER NOT NULL REFERENCES jobs(id),
            helper_id INTEGER NOT NULL REFERENCES users(id),
            message TEXT NOT NULL,
            status VARCHAR(20) DEFAULT 'pending',
            is_accepted BOOLEAN DEFAULT FALSE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(job_id, helper_id)
        )
    """)

    # Messages
    cur.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id SERIAL PRIMARY KEY,
            sender_id INTEGER NOT NULL REFERENCES users(id),
            receiver_id INTEGER NOT NULL REFERENCES users(id),
            job_id INTEGER REFERENCES jobs(id),
            body TEXT NOT NULL,
            is_read BOOLEAN DEFAULT FALSE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Notifications
    cur.execute("""
        CREATE TABLE IF NOT EXISTS notifications (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id),
            message TEXT NOT NULL,
            is_read BOOLEAN DEFAULT FALSE,
            link TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Reports
    cur.execute("""
        CREATE TABLE IF NOT EXISTS reports (
            id SERIAL PRIMARY KEY,
            reporter_id INTEGER NOT NULL REFERENCES users(id),
            reported_user_id INTEGER REFERENCES users(id),
            job_id INTEGER REFERENCES jobs(id),
            reason TEXT NOT NULL,
            status VARCHAR(20) DEFAULT 'pending',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Ratings
    cur.execute("""
        CREATE TABLE IF NOT EXISTS ratings (
            id SERIAL PRIMARY KEY,
            rater_id INTEGER NOT NULL REFERENCES users(id),
            rated_user_id INTEGER NOT NULL REFERENCES users(id),
            job_id INTEGER NOT NULL REFERENCES jobs(id),
            score INTEGER CHECK (score >= 1 AND score <= 5),
            comment TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(rater_id, job_id)
        )
    """)

    # Login Attempts
    cur.execute("""
        CREATE TABLE IF NOT EXISTS login_attempts (
            id SERIAL PRIMARY KEY,
            email VARCHAR(100) NOT NULL,
            ip_address VARCHAR(45) NOT NULL,
            success BOOLEAN NOT NULL,
            attempted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Migration: Add columns if missing (simplified for the prompt)
    # This block ensures smooth updates without full drops
    columns_to_add = [
        ("users", "role", "VARCHAR(20) DEFAULT 'user'"),
        ("users", "is_banned", "BOOLEAN DEFAULT FALSE"),
        ("jobs", "is_featured", "BOOLEAN DEFAULT FALSE"),
        ("jobs", "views", "INTEGER DEFAULT 0"),
        ("jobs", "status", "VARCHAR(20) DEFAULT 'open'")
    ]
    for table, col, defn in columns_to_add:
        try:
            cur.execute(f"ALTER TABLE {table} ADD COLUMN {col} {defn}")
        except:
            conn.rollback()
    
    conn.commit()
    cur.close()
    conn.close()

# ── Helper Functions ──────────────────────────────────────────

def notify(user_id, message, link=None):
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO notifications (user_id, message, link) VALUES (%s, %s, %s)",
        (user_id, message, link)
    )
    conn.commit()
    cur.close()
    conn.close()

def login_required():
    return "user_id" not in session

def admin_required():
    if login_required(): return True
    return session.get("role") != "admin"

@app.context_processor
def inject_globals():
    if "user_id" not in session:
        return {"unread_messages": 0, "unread_notifications": 0}
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM messages WHERE receiver_id = %s AND is_read = FALSE", (session["user_id"],))
    m_count = cur.fetchone()["count"]
    cur.execute("SELECT COUNT(*) FROM notifications WHERE user_id = %s AND is_read = FALSE", (session["user_id"],))
    n_count = cur.fetchone()["count"]
    cur.close(); conn.close()
    return {"unread_messages": m_count, "unread_notifications": n_count}

# ── Auth Routes ───────────────────────────────────────────────

@app.route("/")
def index():
    conn = get_db()
    cur = conn.cursor()
    # Stats
    cur.execute("SELECT COUNT(*) FROM users")
    u_count = cur.fetchone()["count"]
    cur.execute("SELECT COUNT(*) FROM jobs")
    j_count = cur.fetchone()["count"]
    # Coverage (distinct unis)
    cur.execute("SELECT COUNT(DISTINCT university) FROM users")
    uni_count = cur.fetchone()["count"]

    # Featured Jobs
    cur.execute("""
        SELECT jobs.*, users.name as poster_name 
        FROM jobs JOIN users ON jobs.user_id = users.id 
        WHERE is_featured = TRUE AND status = 'open' 
        ORDER BY created_at DESC LIMIT 3
    """)
    featured = cur.fetchall()

    # Latest Jobs
    cur.execute("""
        SELECT jobs.*, users.name as poster_name 
        FROM jobs JOIN users ON jobs.user_id = users.id 
        WHERE is_featured = FALSE AND status = 'open' 
        ORDER BY created_at DESC LIMIT 6
    """)
    latest = cur.fetchall()

    cur.close(); conn.close()
    return render_template("index.html", featured=featured, latest=latest, 
                           stats={"users": u_count, "jobs": j_count, "unis": uni_count})

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name = request.form["name"].strip()
        email = request.form["email"].strip().lower()
        password = request.form["password"]
        university = request.form["university"]
        phone = request.form.get("phone")

        if not name or not email or len(password) < 6:
            flash("Validation failed. Check name, email and password (min 6 chars).", "danger")
            return redirect(url_for("register"))

        hashed = generate_password_hash(password)
        try:
            conn = get_db()
            cur = conn.cursor()
            # First user becomes admin automatically
            cur.execute("SELECT COUNT(*) FROM users")
            role = 'admin' if cur.fetchone()["count"] == 0 else 'user'
            
            cur.execute(
                "INSERT INTO users (name, email, password, university, phone, role) VALUES (%s, %s, %s, %s, %s, %s)",
                (name, email, hashed, university, phone, role)
            )
            conn.commit()
            flash("Registration successful! Please login.", "success")
            return redirect(url_for("login"))
        except:
            flash("Email already exists.", "warning")
            return redirect(url_for("register"))
    return render_template("register.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form["email"].strip().lower()
        password = request.form["password"]
        ip = request.remote_addr

        conn = get_db()
        cur = conn.cursor()

        # Check for lockout (5 fails in 15 mins)
        cur.execute("""
            SELECT COUNT(*) FROM login_attempts 
            WHERE email = %s AND success = FALSE 
            AND attempted_at > NOW() - INTERVAL '15 minutes'
        """, (email,))
        fails = cur.fetchone()["count"]

        if fails >= 5:
            flash("Too many failed attempts. Try again in 15 minutes.", "danger")
            cur.close(); conn.close()
            return render_template("login.html", locked=True)

        cur.execute("SELECT * FROM users WHERE email = %s", (email,))
        user = cur.fetchone()

        if user and check_password_hash(user["password"], password):
            if user["is_banned"]:
                flash("Your account has been banned.", "danger")
                cur.close(); conn.close()
                return redirect(url_for("login"))

            # Log success
            cur.execute("INSERT INTO login_attempts (email, ip_address, success) VALUES (%s, %s, TRUE)", (email, ip))
            cur.execute("UPDATE users SET last_login = NOW() WHERE id = %s", (user["id"],))
            conn.commit()

            session.permanent = True
            session["user_id"] = user["id"]
            session["user_name"] = user["name"]
            session["user_university"] = user["university"]
            session["role"] = user["role"]

            flash(f"Welcome back, {user['name']}!", "success")
            cur.close(); conn.close()
            return redirect(url_for("dashboard"))
        else:
            # Log failure
            cur.execute("INSERT INTO login_attempts (email, ip_address, success) VALUES (%s, %s, FALSE)", (email, ip))
            conn.commit()
            flash(f"Invalid credentials. {4-fails} attempts remaining.", "warning")
            cur.close(); conn.close()
            return redirect(url_for("login"))

    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    flash("Logged out successfully.", "info")
    return redirect(url_for("login"))

# ── Job Routes ───────────────────────────────────────────────

@app.route("/jobs")
def jobs_list():
    cat = request.args.get("category", "")
    uni = request.args.get("university", "")
    min_b = request.args.get("min_budget", "")
    max_b = request.args.get("max_budget", "")

    conn = get_db()
    cur = conn.cursor()

    query = """
        SELECT jobs.*, users.name as poster_name,
        (SELECT COUNT(*) FROM offers WHERE job_id = jobs.id) as offer_count
        FROM jobs JOIN users ON jobs.user_id = users.id 
        WHERE status = 'open'
    """
    params = []
    if cat: 
        query += " AND category = %s"; params.append(cat)
    if uni: 
        query += " AND jobs.university = %s"; params.append(uni)
    if min_b: 
        query += " AND CAST(budget AS NUMERIC) >= %s"; params.append(min_b)
    if max_b: 
        query += " AND CAST(budget AS NUMERIC) <= %s"; params.append(max_b)

    # Featured first, then newest
    query += " ORDER BY is_featured DESC, created_at DESC"
    cur.execute(query, tuple(params))
    jobs = cur.fetchall()

    cur.execute("SELECT DISTINCT university FROM users")
    unis = [r["university"] for r in cur.fetchall()]

    cur.close(); conn.close()
    return render_template("jobs.html", jobs=jobs, universities=unis, count=len(jobs),
                           filters={"cat": cat, "uni": uni, "min": min_b, "max": max_b})

@app.route("/job/<int:job_id>")
def job_details(job_id):
    conn = get_db()
    cur = conn.cursor()
    
    cur.execute("UPDATE jobs SET views = views + 1 WHERE id = %s", (job_id,))
    conn.commit()

    cur.execute("""
        SELECT jobs.*, users.name as poster_name, users.id as poster_id,
        (SELECT AVG(score) FROM ratings WHERE rated_user_id = users.id) as avg_rating
        FROM jobs JOIN users ON jobs.user_id = users.id WHERE jobs.id = %s
    """, (job_id,))
    job = cur.fetchone()

    if not job: abort(404)

    cur.execute("""
        SELECT offers.*, users.name as helper_name, users.university as helper_uni 
        FROM offers JOIN users ON offers.helper_id = users.id 
        WHERE job_id = %s ORDER BY created_at DESC
    """, (job_id,))
    offers = cur.fetchall()

    cur.close(); conn.close()
    return render_template("job_details.html", job=job, offers=offers)

# ── Offer & Action Routes ─────────────────────────────────────

@app.route("/job/<int:job_id>/offer", methods=["POST"])
def submit_offer(job_id):
    if login_required(): return redirect(url_for("login"))
    msg = request.form["message"].strip()
    
    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute("INSERT INTO offers (job_id, helper_id, message) VALUES (%s, %s, %s)", 
                    (job_id, session["user_id"], msg))
        
        # Notify poster
        cur.execute("SELECT user_id, title FROM jobs WHERE id = %s", (job_id,))
        job_info = cur.fetchone()
        notify(job_info["user_id"], f"New offer for your job: {job_info['title']}", url_for('job_details', job_id=job_id))
        
        conn.commit()
        flash("Offer submitted!", "success")
    except:
        flash("You already made an offer.", "warning")
    
    cur.close(); conn.close()
    return redirect(url_for("job_details", job_id=job_id))

@app.route("/offer/<int:offer_id>/accept", methods=["POST"])
def accept_offer(offer_id):
    if login_required(): return redirect(url_for("login"))
    
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM offers WHERE id = %s", (offer_id,))
    offer = cur.fetchone()
    
    cur.execute("SELECT user_id, title FROM jobs WHERE id = %s", (offer["job_id"],))
    job = cur.fetchone()
    
    if job["user_id"] != session["user_id"]: abort(403)
    
    cur.execute("UPDATE offers SET is_accepted = TRUE, status = 'accepted' WHERE id = %s", (offer_id,))
    cur.execute("UPDATE jobs SET status = 'in_progress' WHERE id = %s", (offer["job_id"],))
    conn.commit()
    
    notify(offer["helper_id"], f"Your offer for '{job['title']}' was ACCEPTED!", url_for('job_details', job_id=offer['job_id']))
    
    cur.close(); conn.close()
    flash("Offer accepted! Get in touch with the student.", "success")
    return redirect(url_for("job_details", job_id=offer["job_id"]))

# ── Messaging ────────────────────────────────────────────────

@app.route("/messages")
def messages():
    if login_required(): return redirect(url_for("login"))
    uid = session["user_id"]
    conn = get_db()
    cur = conn.cursor()
    # List conversations
    cur.execute("""
        SELECT DISTINCT ON (other_id)
        u.id as other_id, u.name as other_name, m.body as last_msg, m.created_at, m.is_read
        FROM (
            SELECT CASE WHEN sender_id = %s THEN receiver_id ELSE sender_id END as other_id,
            body, created_at, is_read, receiver_id FROM messages
            WHERE sender_id = %s OR receiver_id = %s
        ) m JOIN users u ON u.id = m.other_id
        ORDER BY other_id, m.created_at DESC
    """, (uid, uid, uid))
    convs = cur.fetchall()
    cur.close(); conn.close()
    return render_template("messages.html", convs=convs)

@app.route("/messages/<int:other_user_id>")
def conversation(other_user_id):
    if login_required(): return redirect(url_for("login"))
    uid = session["user_id"]
    conn = get_db()
    cur = conn.cursor()
    
    cur.execute("UPDATE messages SET is_read = TRUE WHERE sender_id = %s AND receiver_id = %s", (other_user_id, uid))
    conn.commit()

    cur.execute("SELECT name FROM users WHERE id = %s", (other_user_id,))
    other_name = cur.fetchone()["name"]

    cur.execute("""
        SELECT * FROM messages 
        WHERE (sender_id = %s AND receiver_id = %s) OR (sender_id = %s AND receiver_id = %s)
        ORDER BY created_at ASC
    """, (uid, other_user_id, other_user_id, uid))
    thread = cur.fetchall()
    
    cur.close(); conn.close()
    return render_template("conversation.html", thread=thread, other_id=other_user_id, other_name=other_name)

@app.route("/message/send", methods=["POST"])
def send_msg():
    if login_required(): return redirect(url_for("login"))
    rid = request.form["receiver_id"]
    body = request.form["body"].strip()
    jid = request.form.get("job_id")
    
    conn = get_db()
    cur = conn.cursor()
    cur.execute("INSERT INTO messages (sender_id, receiver_id, job_id, body) VALUES (%s, %s, %s, %s)",
                (session["user_id"], rid, jid, body))
    conn.commit()
    notify(rid, "You received a new message!", url_for('conversation', other_user_id=session['user_id']))
    cur.close(); conn.close()
    return redirect(request.referrer)

# ── User & Admin ──────────────────────────────────────────────

@app.route("/user/<int:user_id>")
def profile(user_id):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        SELECT users.*, 
        (SELECT AVG(score) FROM ratings WHERE rated_user_id = users.id) as avg_rating,
        (SELECT COUNT(*) FROM jobs WHERE user_id = users.id) as post_count,
        (SELECT COUNT(*) FROM offers WHERE helper_id = users.id) as offer_count
        FROM users WHERE id = %s
    """, (user_id,))
    user = cur.fetchone()
    if not user: abort(404)
    
    cur.execute("SELECT * FROM jobs WHERE user_id = %s ORDER BY created_at DESC", (user_id,))
    user_jobs = cur.fetchall()
    
    cur.close(); conn.close()
    return render_template("profile.html", profile=user, jobs=user_jobs)

@app.route("/dashboard")
def dashboard():
    if login_required(): return redirect(url_for("login"))
    uid = session["user_id"]
    conn = get_db()
    cur = conn.cursor()
    
    cur.execute("SELECT * FROM jobs WHERE user_id = %s", (uid,))
    my_jobs = cur.fetchall()
    cur.execute("SELECT jobs.*, offers.status as o_status FROM offers JOIN jobs ON offers.job_id = jobs.id WHERE helper_id = %s", (uid,))
    my_offers = cur.fetchall()
    cur.execute("SELECT * FROM notifications WHERE user_id = %s ORDER BY created_at DESC LIMIT 10", (uid,))
    notifs = cur.fetchall()
    
    cur.close(); conn.close()
    return render_template("dashboard.html", my_jobs=my_jobs, my_offers=my_offers, notifications=notifs)

@app.route("/admin")
def admin_panel():
    if admin_required(): abort(403)
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT (SELECT COUNT(*) FROM users) as u, (SELECT COUNT(*) FROM jobs) as j, (SELECT COUNT(*) FROM reports WHERE status = 'pending') as r")
    counts = cur.fetchone()
    cur.execute("SELECT reports.*, u.name as reporter FROM reports JOIN users u ON u.id = reports.reporter_id WHERE status = 'pending'")
    reports = cur.fetchall()
    cur.close(); conn.close()
    return render_template("admin.html", counts=counts, reports=reports)

@app.route("/post-job", methods=["GET", "POST"])
def post_job():
    if login_required(): return redirect(url_for("login"))
    if request.method == "POST":
        title = request.form["title"]
        desc = request.form["description"]
        cat = request.form["category"]
        budget = request.form["budget"]
        deadline = request.form.get("deadline")
        
        conn = get_db()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO jobs (title, description, category, budget, university, user_id, deadline) 
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """, (title, desc, cat, budget, session["user_university"], session["user_id"], deadline if deadline else None))
        conn.commit()
        cur.close(); conn.close()
        flash("Job posted!", "success")
        return redirect(url_for("dashboard"))
    return render_template("post_job.html")

@app.route("/settings", methods=["GET", "POST"])
def settings():
    if login_required(): return redirect(url_for("login"))
    uid = session["user_id"]
    conn = get_db()
    cur = conn.cursor()

    if request.method == "POST":
        name = request.form["name"].strip()
        phone = request.form.get("phone")
        bio = request.form.get("bio")
        uni = request.form["university"]

        cur.execute(
            "UPDATE users SET name = %s, phone = %s, bio = %s, university = %s WHERE id = %s",
            (name, phone, bio, uni, uid)
        )
        conn.commit()
        session["user_name"] = name
        session["user_university"] = uni
        flash("Settings updated!", "success")
        return redirect(url_for("settings"))

    cur.execute("SELECT * FROM users WHERE id = %s", (uid,))
    user = cur.fetchone()
    cur.close(); conn.close()
    return render_template("settings.html", user=user)

@app.route("/notifications")
def notifications():
    if login_required(): return redirect(url_for("login"))
    uid = session["user_id"]
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM notifications WHERE user_id = %s ORDER BY created_at DESC", (uid,))
    notifs = cur.fetchall()
    cur.close(); conn.close()
    return render_template("notifications.html", notifications=notifs)

@app.route("/notifications/read/<int:notif_id>", methods=["POST"])
def mark_notif_read(notif_id):
    if login_required(): return redirect(url_for("login"))
    conn = get_db()
    cur = conn.cursor()
    cur.execute("UPDATE notifications SET is_read = TRUE WHERE id = %s AND user_id = %s", (notif_id, session["user_id"]))
    conn.commit()
    cur.close(); conn.close()
    return redirect(url_for("notifications"))

@app.route("/rate/<int:target_user_id>", methods=["POST"])
def submit_rating(target_user_id):
    if login_required(): return redirect(url_for("login"))
    job_id = request.form["job_id"]
    score = request.form["score"]
    comment = request.form.get("comment", "")
    
    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute(
            "INSERT INTO ratings (rater_id, rated_user_id, job_id, score, comment) VALUES (%s, %s, %s, %s, %s)",
            (session["user_id"], target_user_id, job_id, score, comment)
        )
        conn.commit()
        flash("Rating submitted!", "success")
    except:
        flash("You already rated this user for this job.", "warning")
    
    cur.close(); conn.close()
    return redirect(request.referrer)

@app.route("/report", methods=["POST"])
def submit_report():
    if login_required(): return redirect(url_for("login"))
    reported_user_id = request.form.get("reported_user_id")
    job_id = request.form.get("job_id")
    reason = request.form["reason"]

    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO reports (reporter_id, reported_user_id, job_id, reason) VALUES (%s, %s, %s, %s)",
        (session["user_id"], reported_user_id or None, job_id or None, reason)
    )
    conn.commit()
    cur.close(); conn.close()
    flash("Report submitted. Thank you for keeping CampusFix safe.", "info")
    return redirect(request.referrer)

if __name__ == "__main__":
    init_db()
    app.run(debug=True)