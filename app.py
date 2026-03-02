import os
from dotenv import load_dotenv
from flask import Flask, request, jsonify, session, redirect, render_template
import sqlite3
from google import genai
import json
import re
import logging
from time import time
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps

load_dotenv()

app = Flask(__name__)

# ─────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────

app.secret_key = "pioneer_super_secret_key_do_not_change_2024"
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SECURE'] = False   # Set True if using HTTPS
app.config['PERMANENT_SESSION_LIFETIME'] = 86400  # Session lasts 24 hours

# ✅ API key loaded ONLY from .env — never hardcoded
gemini_api_key = os.environ.get("GEMINI_API_KEY")

if not gemini_api_key:
    logger_temp = logging.getLogger(__name__)
    print("WARNING: GEMINI_API_KEY not set in .env. Using rule-based classification only.")
    client = None
else:
    client = genai.Client(api_key=gemini_api_key)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────
# DATABASE
# ─────────────────────────────────────────────

def get_db():
    conn = sqlite3.connect("queries.db")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id       INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        email    TEXT UNIQUE NOT NULL,
        password TEXT NOT NULL,
        role     TEXT NOT NULL DEFAULT 'student'
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS queries (
        id         INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id    INTEGER NOT NULL,
        query_text TEXT NOT NULL,
        category   TEXT,
        priority   TEXT,
        status     TEXT DEFAULT 'Pending',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
    )
    """)

    hashed_password = generate_password_hash("admin123")
    cursor.execute("""
    INSERT OR IGNORE INTO users (username, email, password, role)
    VALUES ('admin', 'admin@university.com', ?, 'admin')
    """, (hashed_password,))

    conn.commit()
    conn.close()


init_db()


# ─────────────────────────────────────────────
# DECORATORS
# ─────────────────────────────────────────────

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user_id" not in session:
            return jsonify({"message": "Unauthorized. Please log in."}), 401
        return f(*args, **kwargs)
    return decorated


def admin_required(f):
    @wraps(f)
    @login_required
    def decorated(*args, **kwargs):
        if session.get("role") != "admin":
            return jsonify({"message": "Admin access required."}), 403
        return f(*args, **kwargs)
    return decorated


# ─────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────

def validate_fields(data, required_fields):
    for field in required_fields:
        if not data.get(field) or str(data.get(field)).strip() == "":
            return False, f"'{field}' is required and cannot be empty."
    return True, None


def validate_email(email):
    pattern = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"
    return re.match(pattern, email)


request_log = {}

def rate_limit(key, limit=5, window=60):
    now = time()
    request_log.setdefault(key, [])
    request_log[key] = [t for t in request_log[key] if now - t < window]
    if len(request_log[key]) >= limit:
        return False
    request_log[key].append(now)
    return True


def sanitize_for_prompt(text):
    injection_patterns = [
        "ignore previous", "ignore above", "disregard",
        "system:", "assistant:", "user:"
    ]
    text_lower = text.lower()
    for pattern in injection_patterns:
        if pattern in text_lower:
            return None
    return text[:1000]


# ─────────────────────────────────────────────
# CLASSIFICATION
# ─────────────────────────────────────────────

def classify_query_rule_based(text):
    text_lower = text.lower()

    category_keywords = {
        "Finance":   ["fee", "fees", "payment", "refund", "scholarship", "fine", "challan", "dues", "tuition"],
        "Academics": ["exam", "grade", "marks", "result", "attendance", "assignment", "lecture", "course", "syllabus", "backlog", "revaluation"],
        "Technical": ["portal", "login", "password", "website", "app", "system", "error", "bug", "access", "wifi", "internet", "email"],
        "Hostel":    ["hostel", "room", "mess", "warden", "accommodation", "dormitory", "laundry", "maintenance"],
        "Admin":     ["certificate", "document", "noc", "bonafide", "transcript", "migration", "id card", "admission", "form", "affidavit"],
        "Library":   ["library", "book", "issue", "return", "fine", "journal", "reading room"],
    }

    category = "General"
    for cat, keywords in category_keywords.items():
        if any(kw in text_lower for kw in keywords):
            category = cat
            break

    high_kw = ["urgent", "deadline", "tomorrow", "asap", "immediately", "emergency", "critical", "today", "last date"]
    low_kw  = ["whenever", "no rush", "sometime", "general inquiry", "just wondering", "curious"]

    if any(kw in text_lower for kw in high_kw):
        priority = "High"
    elif any(kw in text_lower for kw in low_kw):
        priority = "Low"
    else:
        priority = "Medium"

    return category, priority


def classify_query(text):
    if client is None:
        return classify_query_rule_based(text)

    safe_text = sanitize_for_prompt(text)
    if safe_text is None:
        logger.warning("Suspicious prompt injection detected. Falling back to rule-based classifier.")
        return classify_query_rule_based(text)

    try:
        prompt = f"""You are a university support ticket classifier.

Return ONLY valid JSON in this exact format with no extra text:
{{"category": "", "priority": ""}}

Allowed categories: Finance, Academics, Technical, Hostel, Admin, Library, General
Allowed priorities: Low, Medium, High

Rules:
- High priority: urgent deadlines, emergencies, system outages
- Low priority: general inquiries, no time pressure
- Medium priority: everything else

Query: {safe_text}"""

        response = client.models.generate_content(model="gemini-2.0-flash", contents=prompt)
        cleaned  = response.text.replace("```json", "").replace("```", "").strip()
        data     = json.loads(cleaned)

        if not isinstance(data, dict):
            raise ValueError("Invalid AI response structure")

        valid_categories = ["Finance", "Academics", "Technical", "Hostel", "Admin", "Library", "General"]
        valid_priorities  = ["Low", "Medium", "High"]

        category = data.get("category", "General")
        priority = data.get("priority", "Medium")

        if category not in valid_categories:
            category = "General"
        if priority not in valid_priorities:
            priority = "Medium"

        return category, priority

    except Exception as e:
        logger.error(f"AI classification failed ({e}). Falling back to rule-based classifier.")
        return classify_query_rule_based(text)


# ─────────────────────────────────────────────
# PAGE ROUTES
# ─────────────────────────────────────────────

@app.route("/")
def home():
    return render_template("role1.html")

@app.route("/student")
def student_page():
    return render_template("student.html")

@app.route("/health")
def health():
    return jsonify({"status": "ok", "ai_enabled": client is not None})


# ─────────────────────────────────────────────
# ADMIN PAGE ROUTES
# ─────────────────────────────────────────────

@app.route("/admin-login-page")
def admin_login_page():
    return render_template("admin_login.html")


@app.route("/admin-login", methods=["POST"])
def admin_login():
    data = request.json or request.form
    username = data.get("username")
    password = data.get("password")

    if not username or not password:
        return jsonify({"message": "Missing credentials"}), 400

    conn = get_db()
    user = conn.execute(
        "SELECT id, role, password FROM users WHERE username=?",
        (username,)
    ).fetchone()
    conn.close()

    if user and check_password_hash(user["password"], password) and user["role"] == "admin":
        session.permanent = True
        session["user_id"] = user["id"]
        session["role"] = "admin"
        return jsonify({"message": "Login successful"})

    return jsonify({"message": "Invalid login"}), 401


@app.route("/admin-page")
def admin_page():
    if session.get("role") != "admin":
        return redirect("/admin-login-page")
    return render_template("admin.html")


# ─────────────────────────────────────────────
# AUTH ROUTES (student + general)
# ─────────────────────────────────────────────

@app.route("/register", methods=["POST"])
def register():
    data = request.json or {}

    is_valid, error = validate_fields(data, ["username", "email", "password"])
    if not is_valid:
        return jsonify({"message": error}), 400

    username = data["username"].strip()
    email    = data["email"].strip().lower()
    password = data["password"].strip()

    if len(username) < 3:
        return jsonify({"message": "Username must be at least 3 characters."}), 400
    if not validate_email(email):
        return jsonify({"message": "Invalid email address."}), 400
    if len(password) < 6:
        return jsonify({"message": "Password must be at least 6 characters."}), 400

    hashed = generate_password_hash(password)

    try:
        conn = get_db()
        conn.execute(
            "INSERT INTO users (username, email, password, role) VALUES (?, ?, ?, 'student')",
            (username, email, hashed)
        )
        conn.commit()
        conn.close()
        return jsonify({"message": "Registration successful."}), 201

    except sqlite3.IntegrityError:
        return jsonify({"message": "Username or email already exists."}), 409


@app.route("/login", methods=["POST"])
def login():
    data = request.json or {}

    is_valid, error = validate_fields(data, ["username", "password"])
    if not is_valid:
        return jsonify({"message": error}), 400

    identifier = data["username"].strip()
    password   = data["password"].strip()

    conn = get_db()
    user = conn.execute(
        "SELECT id, role, password FROM users WHERE username=? OR email=?",
        (identifier, identifier)
    ).fetchone()
    conn.close()

    if user and check_password_hash(user["password"], password):
        session.permanent = True
        session["user_id"] = user["id"]
        session["role"]    = user["role"]
        return jsonify({"message": "Login successful.", "role": user["role"]})
    else:
        return jsonify({"message": "Invalid credentials."}), 401


@app.route("/logout")
def logout():
    """GET logout — used by admin redirect flow."""
    session.pop("user_id", None)
    session.pop("role", None)
    return redirect("/admin-login-page")


@app.route("/api/logout", methods=["POST"])
def api_logout():
    """POST logout — used by student JS fetch."""
    session.clear()
    return jsonify({"message": "Logged out successfully."})


# ─────────────────────────────────────────────
# SESSION CHECK ENDPOINT
# ─────────────────────────────────────────────

@app.route("/api/me", methods=["GET"])
@login_required
def get_me():
    """Returns current logged-in user info. Used by frontend to restore session on refresh."""
    conn = get_db()
    user = conn.execute(
        "SELECT id, username, email, role FROM users WHERE id=?",
        (session["user_id"],)
    ).fetchone()
    conn.close()
    if not user:
        return jsonify({"message": "User not found."}), 404
    return jsonify({
        "id":       user["id"],
        "username": user["username"],
        "email":    user["email"],
        "role":     user["role"]
    })


# ─────────────────────────────────────────────
# STUDENT ROUTES
# ─────────────────────────────────────────────

@app.route("/submit", methods=["POST"])
@login_required
def submit_query():
    data = request.json or {}

    is_valid, error = validate_fields(data, ["query"])
    if not is_valid:
        return jsonify({"message": error}), 400

    query_text = data["query"].strip()

    if len(query_text) < 10:
        return jsonify({"message": "Query is too short. Please describe your issue in more detail."}), 400
    if len(query_text) > 2000:
        return jsonify({"message": "Query is too long. Please limit to 2000 characters."}), 400

    if not rate_limit(f"user_{session['user_id']}", limit=5, window=60):
        return jsonify({"message": "Too many submissions. Please try again later."}), 429

    category, priority = classify_query(query_text)

    conn = get_db()
    conn.execute(
        "INSERT INTO queries (user_id, query_text, category, priority, status) VALUES (?, ?, ?, ?, 'Pending')",
        (session["user_id"], query_text, category, priority)
    )
    conn.commit()
    conn.close()

    return jsonify({
        "message":  "Query submitted successfully.",
        "category": category,
        "priority": priority
    }), 201


@app.route("/student/queries", methods=["GET"])
@login_required
def get_student_queries():
    page     = request.args.get("page", 1, type=int)
    per_page = min(request.args.get("per_page", 10, type=int), 50)
    offset   = (page - 1) * per_page

    conn  = get_db()
    total = conn.execute(
        "SELECT COUNT(*) FROM queries WHERE user_id=?", (session["user_id"],)
    ).fetchone()[0]
    rows  = conn.execute("""
        SELECT id, query_text, category, priority, status, created_at
        FROM queries WHERE user_id=?
        ORDER BY id DESC LIMIT ? OFFSET ?
    """, (session["user_id"], per_page, offset)).fetchall()
    conn.close()

    return jsonify({
        "total":    total,
        "page":     page,
        "per_page": per_page,
        "queries":  [dict(row) for row in rows]
    })


# ─────────────────────────────────────────────
# ADMIN API ROUTES
# ─────────────────────────────────────────────

@app.route("/admin/dashboard", methods=["GET"])
@admin_required
def admin_dashboard():
    conn = get_db()

    stats = {
        "total_students": conn.execute("SELECT COUNT(*) FROM users WHERE role='student'").fetchone()[0],
        "total_queries":  conn.execute("SELECT COUNT(*) FROM queries").fetchone()[0],
        "pending":        conn.execute("SELECT COUNT(*) FROM queries WHERE status='Pending'").fetchone()[0],
        "in_progress":    conn.execute("SELECT COUNT(*) FROM queries WHERE status='In Progress'").fetchone()[0],
        "resolved":       conn.execute("SELECT COUNT(*) FROM queries WHERE status='Resolved'").fetchone()[0],
    }

    category_rows = conn.execute(
        "SELECT category, COUNT(*) as count FROM queries GROUP BY category"
    ).fetchall()
    stats["by_category"] = {row["category"]: row["count"] for row in category_rows}

    priority_rows = conn.execute(
        "SELECT priority, COUNT(*) as count FROM queries GROUP BY priority"
    ).fetchall()
    stats["by_priority"] = {row["priority"]: row["count"] for row in priority_rows}

    conn.close()
    return jsonify(stats)


@app.route("/admin/queries", methods=["GET"])
@admin_required
def admin_all_queries():
    status   = request.args.get("status")
    category = request.args.get("category")
    priority = request.args.get("priority")
    page     = request.args.get("page", 1, type=int)
    per_page = min(request.args.get("per_page", 20, type=int), 100)
    offset   = (page - 1) * per_page

    base_query = """
        SELECT q.id, u.username, u.email, q.query_text,
               q.category, q.priority, q.status, q.created_at
        FROM queries q
        JOIN users u ON q.user_id = u.id
        WHERE 1=1
    """
    params = []

    if status:
        base_query += " AND q.status=?"
        params.append(status)
    if category:
        base_query += " AND q.category=?"
        params.append(category)
    if priority:
        base_query += " AND q.priority=?"
        params.append(priority)

    conn  = get_db()
    total = conn.execute(
        f"SELECT COUNT(*) FROM ({base_query}) AS subquery", params
    ).fetchone()[0]
    rows  = conn.execute(
        base_query + " ORDER BY q.id DESC LIMIT ? OFFSET ?",
        params + [per_page, offset]
    ).fetchall()
    conn.close()

    return jsonify({
        "total":    total,
        "page":     page,
        "per_page": per_page,
        "queries":  [dict(row) for row in rows]
    })


@app.route("/admin/students", methods=["GET"])
@admin_required
def admin_students():
    conn = get_db()
    rows = conn.execute("""
        SELECT u.id, u.username, u.email, COUNT(q.id) as total_queries
        FROM users u
        LEFT JOIN queries q ON u.id = q.user_id
        WHERE u.role='student'
        GROUP BY u.id
        ORDER BY total_queries DESC
    """).fetchall()
    conn.close()
    return jsonify([dict(row) for row in rows])


@app.route("/admin/student/<int:student_id>", methods=["GET"])
@admin_required
def admin_student_detail(student_id):
    conn    = get_db()
    student = conn.execute(
        "SELECT id, username, email FROM users WHERE id=? AND role='student'",
        (student_id,)
    ).fetchone()

    if not student:
        conn.close()
        return jsonify({"message": "Student not found."}), 404

    rows = conn.execute("""
        SELECT id, query_text, category, priority, status, created_at
        FROM queries WHERE user_id=? ORDER BY id DESC
    """, (student_id,)).fetchall()
    conn.close()

    return jsonify({
        "student": dict(student),
        "queries": [dict(row) for row in rows]
    })


@app.route("/admin/update-status", methods=["PUT"])
@admin_required
def update_status():
    data = request.json or {}

    is_valid, error = validate_fields(data, ["query_id", "status"])
    if not is_valid:
        return jsonify({"message": error}), 400

    query_id   = data["query_id"]
    new_status = data["status"]

    allowed = ["Pending", "In Progress", "Resolved"]
    if new_status not in allowed:
        return jsonify({"message": f"Invalid status. Allowed values: {allowed}"}), 400

    conn     = get_db()
    existing = conn.execute("SELECT id FROM queries WHERE id=?", (query_id,)).fetchone()
    if not existing:
        conn.close()
        return jsonify({"message": "Query not found."}), 404

    conn.execute("UPDATE queries SET status=? WHERE id=?", (new_status, query_id))
    conn.commit()
    conn.close()

    return jsonify({"message": "Status updated successfully."})


@app.route("/admin/delete-query/<int:query_id>", methods=["DELETE"])
@admin_required
def delete_query(query_id):
    conn     = get_db()
    existing = conn.execute("SELECT id FROM queries WHERE id=?", (query_id,)).fetchone()
    if not existing:
        conn.close()
        return jsonify({"message": "Query not found."}), 404

    conn.execute("DELETE FROM queries WHERE id=?", (query_id,))
    conn.commit()
    conn.close()
    return jsonify({"message": "Query deleted successfully."})


# ─────────────────────────────────────────────  ← ONLY CHANGE IS HERE
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port, debug=False)
