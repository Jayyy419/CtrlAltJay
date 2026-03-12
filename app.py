import os
import sqlite3
import time
import hmac
from datetime import datetime
from functools import wraps
from pathlib import Path

from dotenv import load_dotenv
from flask import (
    Flask,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from flask_mail import Mail, Message
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "portfolio.db"
UPLOAD_DIR = BASE_DIR / "static" / "uploads"

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "change-this-secret")
app.config["MAIL_SERVER"] = os.getenv("MAIL_SERVER", "default_server")
app.config["MAIL_PORT"] = int(os.getenv("MAIL_PORT", 587))
app.config["MAIL_USERNAME"] = os.getenv("MAIL_USERNAME", "default_username")
app.config["MAIL_PASSWORD"] = os.getenv("MAIL_PASSWORD", "default_password")
app.config["MAIL_USE_TLS"] = os.getenv("MAIL_USE_TLS", "true").lower() in ["true", "1", "t"]
app.config["MAIL_USE_SSL"] = os.getenv("MAIL_USE_SSL", "false").lower() in ["true", "1", "t"]

mail = Mail(app)

DEFAULT_ADMIN_PASSCODE_HASH = generate_password_hash("controlalternatejay")
MAX_ADMIN_ATTEMPTS = 5
ADMIN_LOCK_SECONDS = 600


def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def now_iso():
    return datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")


def login_required(view_func):
    @wraps(view_func)
    def wrapped(*args, **kwargs):
        if not session.get("is_admin"):
            return redirect(url_for("index"))
        return view_func(*args, **kwargs)

    return wrapped


def verify_admin_passcode(submitted_passcode):
    configured_hash = os.getenv("ADMIN_PASSCODE_HASH", "").strip()
    configured_plain = os.getenv("ADMIN_PASSCODE", "").strip()

    if configured_hash:
        return check_password_hash(configured_hash, submitted_passcode)

    if configured_plain:
        return hmac.compare_digest(configured_plain, submitted_passcode)

    return check_password_hash(DEFAULT_ADMIN_PASSCODE_HASH, submitted_passcode)


def unauthorized_admin_response():
    if not session.get("is_admin"):
        return jsonify({"error": "Unauthorized"}), 403
    return None


def save_uploaded_image(upload):
    if not upload or not upload.filename:
        return ""

    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    safe_name = secure_filename(upload.filename)
    stamped_name = f"{int(datetime.utcnow().timestamp())}_{safe_name}"
    destination = UPLOAD_DIR / stamped_name
    upload.save(destination)
    return f"../static/uploads/{stamped_name}"


def initialize_database():
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

    with get_db_connection() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS portfolio_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                section TEXT NOT NULL,
                category TEXT NOT NULL,
                subsection TEXT,
                title TEXT NOT NULL,
                byline TEXT,
                tag TEXT,
                summary TEXT,
                description TEXT,
                date_label TEXT,
                date_value TEXT,
                deliverables TEXT,
                challenges TEXT,
                future_improvements TEXT,
                extra_notes TEXT,
                image_path TEXT,
                external_link TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )

        # Add subsection column if it doesn't exist
        try:
            conn.execute("ALTER TABLE portfolio_items ADD COLUMN subsection TEXT")
        except:
            pass  # Column already exists

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS resume_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                lane TEXT NOT NULL,
                title TEXT NOT NULL,
                subtitle TEXT,
                period TEXT NOT NULL,
                description TEXT,
                sort_order INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS skills (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                level INTEGER NOT NULL,
                focus TEXT,
                sort_order INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )

        has_data = conn.execute("SELECT COUNT(*) AS count FROM portfolio_items").fetchone()["count"]

        if has_data == 0:
            seed_now = now_iso()
            seed_items = [
                (
                    "project",
                    "App Development",
                    "Jumpstart",
                    "Rone Peh",
                    "App Development - Platform",
                    "Student-first starter platform to help peers rapidly ship portfolio-quality projects.",
                    "A practical project accelerant for students. Jumpstart includes starter architecture, repeatable checklists, and coaching-style prompts to reduce setup friction.",
                    "Started",
                    "Jan 2026",
                    "Starter boilerplates and docs",
                    "Aligning templates to many skill levels",
                    "Add AI-driven project scaffolding",
                    "Actively building with peers.",
                    "../static/images/Projects/AppDev_AdaptEd.png",
                    "",
                    seed_now,
                    seed_now,
                ),
                (
                    "project",
                    "Machine Learning",
                    "Dream Machine",
                    "Rone Peh",
                    "Machine Learning - GenAI",
                    "Generate anime-style storyline pipelines with prompt-to-scene experiments.",
                    "Prototype to convert user prompts into narrative blocks, then map them into image/storyboard generation.",
                    "Status",
                    "Work in progress",
                    "Prompt pipeline and scene generation",
                    "Keeping style consistency across generated outputs",
                    "Build community gallery and sharing",
                    "Exploring model orchestration patterns.",
                    "../static/images/Projects/ML_DreamMachine.png",
                    "",
                    seed_now,
                    seed_now,
                ),
                (
                    "project",
                    "Web Development",
                    "CtrlAltJay Portfolio",
                    "Rone Peh",
                    "Web Development - Personal Branding",
                    "A living portfolio designed as a narrative resume with deep project and experience context.",
                    "A content-first portfolio with card previews and richer detail modals, intended for recruiters and collaborators.",
                    "Released",
                    "Mar 2026",
                    "Responsive portfolio with admin CMS",
                    "Balancing storytelling with clean information architecture",
                    "Add analytics and public changelog",
                    "Designed to evolve over time.",
                    "../static/images/Projects/WebDev_PortfolioV1.png",
                    "",
                    seed_now,
                    seed_now,
                ),
                (
                    "experience",
                    "Certifications",
                    "AWS Certified Cloud Practitioner",
                    "AWS Training and Certification",
                    "Certifications - AWS",
                    "Foundational cloud credential validating core AWS concepts and practical understanding.",
                    "Completed and applied fundamentals in projects involving cloud architecture and serverless tooling.",
                    "Certified Date",
                    "2024",
                    "Cloud fundamentals validation",
                    "Balancing exam prep with project timelines",
                    "Advance towards specialty tracks",
                    "",
                    "../static/images/Certifications/AWS/AWSTrainingAndCertification/ACP/AWSCertifiedCloudPractitioner_Certificate.jpg",
                    "",
                    seed_now,
                    seed_now,
                ),
                (
                    "experience",
                    "Events",
                    "Tech Week 2024",
                    "NYP AWS Cloud Club",
                    "Events - Dialogue",
                    "Supported event activities focused on cloud, innovation, and student networking.",
                    "Participated in planning and support operations to ensure smooth technical sessions.",
                    "Event Date",
                    "2024",
                    "Event support and attendee engagement",
                    "Coordinating logistics under short timelines",
                    "Lead a segment in future editions",
                    "",
                    "../static/images/Projects/AppDev_TriviaBotOnDiscord.png",
                    "",
                    seed_now,
                    seed_now,
                ),
                (
                    "experience",
                    "External Roles",
                    "Networks Engagement Manager",
                    "Advisory Singapore",
                    "External Roles - Youth Organization",
                    "Building links with professionals and stakeholders to expand youth career support.",
                    "Drives partnerships and event collaborations to strengthen access to mentorship and opportunities.",
                    "Joined",
                    "Aug 2024",
                    "Partnership initiatives and ecosystem engagement",
                    "Aligning stakeholder schedules and priorities",
                    "Scale long-term collaboration tracks",
                    "",
                    "",
                    "",
                    seed_now,
                    seed_now,
                ),
                (
                    "experience",
                    "Testimonials",
                    "Reliable under pressure",
                    "Peer Collaboration Feedback",
                    "Testimonials - Teamwork",
                    "Rone communicates clearly and keeps execution moving even in tight sprint windows.",
                    "Consistently dependable in planning and delivery phases, especially when requirements shift quickly.",
                    "Received",
                    "2025",
                    "Cross-functional coordination",
                    "Rapid requirement changes",
                    "Continue mentoring junior contributors",
                    "",
                    "../static/images/avatar-1.png",
                    "",
                    seed_now,
                    seed_now,
                ),
            ]

            conn.executemany(
                """
                INSERT INTO portfolio_items (
                    section, category, title, byline, tag, summary, description,
                    date_label, date_value, deliverables, challenges,
                    future_improvements, extra_notes, image_path, external_link,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                seed_items,
            )

            seed_resume = [
                (
                    "education",
                    "Nanyang Polytechnic",
                    "Diploma in Information Technology",
                    "Apr 2023 - May 2026",
                    "Core focus: software engineering, cloud, and AI applications.",
                    1,
                    seed_now,
                    seed_now,
                ),
                (
                    "education",
                    "Gachon University",
                    "Overseas Exchange Programme",
                    "Aug 2024 - Dec 2024",
                    "Completed advanced modules in ML, deep learning, web databases, and data programming.",
                    2,
                    seed_now,
                    seed_now,
                ),
                (
                    "work",
                    "JPMorganChase",
                    "SWE Intern - Commercial & Investment Bank",
                    "Apr 2025 - Mar 2026",
                    "Supported cloud migration and platform/tooling workstreams in enterprise environments.",
                    1,
                    seed_now,
                    seed_now,
                ),
            ]

            conn.executemany(
                """
                INSERT INTO resume_items (
                    lane, title, subtitle, period, description, sort_order, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                seed_resume,
            )

            seed_skills = [
                ("Python", 84, "Backend and automation", 1, seed_now, seed_now),
                ("Flask", 81, "Web app architecture", 2, seed_now, seed_now),
                ("JavaScript", 76, "Frontend interaction", 3, seed_now, seed_now),
                ("Cloud & DevOps", 72, "AWS fundamentals and deployment", 4, seed_now, seed_now),
                ("AI/ML", 74, "Practical model integration", 5, seed_now, seed_now),
            ]

            conn.executemany(
                """
                INSERT INTO skills (
                    name, level, focus, sort_order, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                seed_skills,
            )

        conn.commit()


def row_to_dict(row):
    return {key: row[key] for key in row.keys()}


@app.before_request
def bootstrap():
    if not getattr(app, "_db_initialized", False):
        initialize_database()
        app._db_initialized = True


@app.route("/")
def index():
    profile = {
        "name": "Rone Peh",
        "headline": "IT Student | Builder of practical AI and cloud solutions",
        "location": "Singapore",
        "email": "Rone_peh@hotmail.com",
        "phone": "+65 8808 1760",
        "credly": "https://www.credly.com/",
        "github": "https://github.com/Jayyy419",
        "linkedin": "https://www.linkedin.com/in/ronepeh",
        "bio": (
            "I am an IT student passionate about building meaningful products at the intersection of software, cloud, and AI. "
            "I enjoy transforming ideas into practical systems that people can use."
        ),
        "now_building": [
            {
                "title": "Jumpstart",
                "description": "A project-launch system to help students ship polished products faster.",
            },
            {
                "title": "Competition Track",
                "description": "Preparing for hackathons and innovation competitions with reusable technical playbooks.",
            },
            {
                "title": "AI Prototyping Sprint",
                "description": "Exploring rapid prototypes in GenAI, RAG, and product UX alignment.",
            },
        ],
    }
    return render_template("index.html", profile=profile)


@app.route("/api/public-data")
def api_public_data():
    with get_db_connection() as conn:
        projects = conn.execute(
            "SELECT * FROM portfolio_items WHERE section = 'project'"
        ).fetchall()
        experiences = conn.execute(
            "SELECT * FROM portfolio_items WHERE section = 'experience'"
        ).fetchall()
        resume_items = conn.execute(
            "SELECT * FROM resume_items ORDER BY lane ASC, sort_order ASC, id DESC"
        ).fetchall()
        skills = conn.execute(
            "SELECT * FROM skills ORDER BY sort_order ASC, id ASC"
        ).fetchall()

    return jsonify(
        {
            "projects": [row_to_dict(row) for row in projects],
            "experiences": [row_to_dict(row) for row in experiences],
            "resume": [row_to_dict(row) for row in resume_items],
            "skills": [row_to_dict(row) for row in skills],
        }
    )


@app.route("/admin/login/<secret_key>", methods=["GET", "POST"])
def admin_login(secret_key):
    # Legacy route retained for compatibility; auth now happens via popup on index.
    return redirect(url_for("index"))


@app.route("/api/admin/auth-status", methods=["GET"])
def admin_auth_status():
    return jsonify({"is_admin": bool(session.get("is_admin"))})


@app.route("/admin/auth", methods=["POST"])
def admin_auth():
    lock_until = int(session.get("admin_lock_until", 0) or 0)
    now_epoch = int(time.time())

    if lock_until > now_epoch:
        remaining = lock_until - now_epoch
        return jsonify({"error": "Too many attempts. Please wait and try again.", "retry_in": remaining}), 429

    payload = request.get_json(silent=True) or {}
    submitted_passcode = (
        payload.get("passcode")
        or request.form.get("passcode", "")
    ).strip()

    if not submitted_passcode:
        return jsonify({"error": "Passcode is required."}), 400

    if verify_admin_passcode(submitted_passcode):
        session["is_admin"] = True
        session.pop("admin_attempts", None)
        session.pop("admin_lock_until", None)
        return jsonify({"message": "Authenticated.", "redirect_url": url_for("admin_dashboard")})

    attempts = int(session.get("admin_attempts", 0) or 0) + 1
    session["admin_attempts"] = attempts

    if attempts >= MAX_ADMIN_ATTEMPTS:
        session["admin_lock_until"] = now_epoch + ADMIN_LOCK_SECONDS
        session["admin_attempts"] = 0
        return jsonify({"error": "Too many attempts. Please wait and try again."}), 429

    remaining = MAX_ADMIN_ATTEMPTS - attempts
    return jsonify({"error": "Invalid passcode.", "remaining_attempts": remaining}), 401


@app.route("/admin/logout", methods=["GET", "POST"])
def admin_logout():
    session.pop("is_admin", None)
    if request.method == "POST":
        return jsonify({"ok": True})
    return redirect(url_for("index"))


@app.route("/admin")
@login_required
def admin_dashboard():
    return render_template("admin.html")


@app.route("/api/admin/items", methods=["GET", "POST"])
def api_admin_items():
    unauthorized = unauthorized_admin_response()
    if unauthorized:
        return unauthorized
    
    if request.method == "GET":
        section = request.args.get("section", "").strip().lower()
        query = "SELECT * FROM portfolio_items"
        args = []
        if section in {"project", "experience"}:
            query += " WHERE section = ?"
            args.append(section)
        query += " ORDER BY updated_at DESC"

        with get_db_connection() as conn:
            rows = conn.execute(query, args).fetchall()

        return jsonify([row_to_dict(row) for row in rows])

    image_path = save_uploaded_image(request.files.get("image"))
    now = now_iso()
    payload = {
        "section": request.form.get("section", "").strip().lower(),
        "category": request.form.get("category", "").strip(),
        "subsection": request.form.get("subsection", "").strip(),
        "title": request.form.get("title", "").strip(),
        "byline": request.form.get("byline", "").strip(),
        "tag": request.form.get("tag", "").strip(),
        "summary": request.form.get("summary", "").strip(),
        "description": request.form.get("description", "").strip(),
        "date_label": request.form.get("date_label", "").strip(),
        "date_value": request.form.get("date_value", "").strip(),
        "deliverables": request.form.get("deliverables", "").strip(),
        "challenges": request.form.get("challenges", "").strip(),
        "future_improvements": request.form.get("future_improvements", "").strip(),
        "extra_notes": request.form.get("extra_notes", "").strip(),
        "image_path": image_path or request.form.get("image_path", "").strip(),
        "external_link": request.form.get("external_link", "").strip(),
    }

    required_ok = payload["section"] in {"project", "experience"} and payload["category"] and payload["title"]
    if not required_ok:
        return jsonify({"error": "section, category, and title are required."}), 400

    with get_db_connection() as conn:
        conn.execute(
            """
            INSERT INTO portfolio_items (
                section, category, subsection, title, byline, tag, summary, description,
                date_label, date_value, deliverables, challenges,
                future_improvements, extra_notes, image_path, external_link,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                payload["section"],
                payload["category"],
                payload["subsection"],
                payload["title"],
                payload["byline"],
                payload["tag"],
                payload["summary"],
                payload["description"],
                payload["date_label"],
                payload["date_value"],
                payload["deliverables"],
                payload["challenges"],
                payload["future_improvements"],
                payload["extra_notes"],
                payload["image_path"],
                payload["external_link"],
                now,
                now,
            ),
        )
        conn.commit()

    return jsonify({"message": "Item created."}), 201


@app.route("/api/admin/items/<int:item_id>", methods=["PUT", "DELETE"])
def api_admin_item(item_id):
    unauthorized = unauthorized_admin_response()
    if unauthorized:
        return unauthorized
    
    with get_db_connection() as conn:
        existing = conn.execute(
            "SELECT * FROM portfolio_items WHERE id = ?", (item_id,)
        ).fetchone()

        if not existing:
            return jsonify({"error": "Item not found."}), 404

        if request.method == "DELETE":
            conn.execute("DELETE FROM portfolio_items WHERE id = ?", (item_id,))
            conn.commit()
            return jsonify({"message": "Item deleted."})

        form = request.form
        image_path = save_uploaded_image(request.files.get("image"))
        updated_at = now_iso()
        updated_payload = {
            "section": form.get("section", existing["section"]).strip().lower(),
            "category": form.get("category", existing["category"]).strip(),
            "subsection": form.get("subsection", existing.get("subsection", "")).strip(),
            "title": form.get("title", existing["title"]).strip(),
            "byline": form.get("byline", existing.get("byline") or "").strip(),
            "tag": form.get("tag", existing.get("tag") or "").strip(),
            "summary": form.get("summary", existing.get("summary") or "").strip(),
            "description": form.get("description", existing.get("description") or "").strip(),
            "date_label": form.get("date_label", existing.get("date_label") or "").strip(),
            "date_value": form.get("date_value", existing.get("date_value") or "").strip(),
            "deliverables": form.get("deliverables", existing.get("deliverables") or "").strip(),
            "challenges": form.get("challenges", existing.get("challenges") or "").strip(),
            "future_improvements": form.get("future_improvements", existing.get("future_improvements") or "").strip(),
            "extra_notes": form.get("extra_notes", existing.get("extra_notes") or "").strip(),
            "image_path": image_path or form.get("image_path", existing.get("image_path") or "").strip(),
            "external_link": form.get("external_link", existing.get("external_link") or "").strip(),
        }

        conn.execute(
            """
            UPDATE portfolio_items
            SET section = ?, category = ?, subsection = ?, title = ?, byline = ?, tag = ?, summary = ?,
                description = ?, date_label = ?, date_value = ?, deliverables = ?, challenges = ?,
                future_improvements = ?, extra_notes = ?, image_path = ?, external_link = ?, updated_at = ?
            WHERE id = ?
            """,
            (
                updated_payload["section"],
                updated_payload["category"],
                updated_payload["subsection"],
                updated_payload["title"],
                updated_payload["byline"],
                updated_payload["tag"],
                updated_payload["summary"],
                updated_payload["description"],
                updated_payload["date_label"],
                updated_payload["date_value"],
                updated_payload["deliverables"],
                updated_payload["challenges"],
                updated_payload["future_improvements"],
                updated_payload["extra_notes"],
                updated_payload["image_path"],
                updated_payload["external_link"],
                updated_at,
                item_id,
            ),
        )
        conn.commit()

    return jsonify({"message": "Item updated."})


@app.route("/api/admin/resume", methods=["GET", "POST"])
def api_admin_resume():
    unauthorized = unauthorized_admin_response()
    if unauthorized:
        return unauthorized
    
    if request.method == "GET":
        with get_db_connection() as conn:
            rows = conn.execute(
                "SELECT * FROM resume_items ORDER BY lane ASC, sort_order ASC, id DESC"
            ).fetchall()
        return jsonify([row_to_dict(row) for row in rows])

    now = now_iso()
    lane = request.form.get("lane", "").strip().lower()
    title = request.form.get("title", "").strip()
    period = request.form.get("period", "").strip()
    subtitle = request.form.get("subtitle", "").strip()
    description = request.form.get("description", "").strip()
    sort_order = int(request.form.get("sort_order", "0") or 0)

    if lane not in {"education", "work"}:
        return jsonify({"error": "lane must be education or work."}), 400
    if not title or not period:
        return jsonify({"error": "title and period are required."}), 400

    with get_db_connection() as conn:
        conn.execute(
            """
            INSERT INTO resume_items (
                lane, title, subtitle, period, description, sort_order, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (lane, title, subtitle, period, description, sort_order, now, now),
        )
        conn.commit()
    return jsonify({"message": "Resume item created."}), 201


@app.route("/api/admin/resume/<int:item_id>", methods=["PUT", "DELETE"])
def api_admin_resume_item(item_id):
    unauthorized = unauthorized_admin_response()
    if unauthorized:
        return unauthorized
    
    with get_db_connection() as conn:
        existing = conn.execute(
            "SELECT * FROM resume_items WHERE id = ?", (item_id,)
        ).fetchone()
        if not existing:
            return jsonify({"error": "Resume item not found."}), 404

        if request.method == "DELETE":
            conn.execute("DELETE FROM resume_items WHERE id = ?", (item_id,))
            conn.commit()
            return jsonify({"message": "Resume item deleted."})

        lane = request.form.get("lane", existing["lane"]).strip().lower()
        if lane not in {"education", "work"}:
            return jsonify({"error": "lane must be education or work."}), 400

        conn.execute(
            """
            UPDATE resume_items
            SET lane = ?, title = ?, subtitle = ?, period = ?, description = ?, sort_order = ?, updated_at = ?
            WHERE id = ?
            """,
            (
                lane,
                request.form.get("title", existing["title"]).strip(),
                request.form.get("subtitle", existing["subtitle"] or "").strip(),
                request.form.get("period", existing["period"]).strip(),
                request.form.get("description", existing["description"] or "").strip(),
                int(request.form.get("sort_order", existing["sort_order"]) or 0),
                now_iso(),
                item_id,
            ),
        )
        conn.commit()

    return jsonify({"message": "Resume item updated."})


@app.route("/api/admin/skills", methods=["GET", "POST"])
def api_admin_skills():
    unauthorized = unauthorized_admin_response()
    if unauthorized:
        return unauthorized
    
    if request.method == "GET":
        with get_db_connection() as conn:
            rows = conn.execute("SELECT * FROM skills ORDER BY sort_order ASC, id ASC").fetchall()
        return jsonify([row_to_dict(row) for row in rows])

    now = now_iso()
    name = request.form.get("name", "").strip()
    level = int(request.form.get("level", "0") or 0)
    focus = request.form.get("focus", "").strip()
    sort_order = int(request.form.get("sort_order", "0") or 0)

    if not name or level < 0 or level > 100:
        return jsonify({"error": "name is required and level must be 0-100."}), 400

    with get_db_connection() as conn:
        conn.execute(
            """
            INSERT INTO skills (name, level, focus, sort_order, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (name, level, focus, sort_order, now, now),
        )
        conn.commit()
    return jsonify({"message": "Skill created."}), 201


@app.route("/api/admin/skills/<int:item_id>", methods=["PUT", "DELETE"])
def api_admin_skill_item(item_id):
    unauthorized = unauthorized_admin_response()
    if unauthorized:
        return unauthorized
    
    with get_db_connection() as conn:
        existing = conn.execute("SELECT * FROM skills WHERE id = ?", (item_id,)).fetchone()
        if not existing:
            return jsonify({"error": "Skill not found."}), 404

        if request.method == "DELETE":
            conn.execute("DELETE FROM skills WHERE id = ?", (item_id,))
            conn.commit()
            return jsonify({"message": "Skill deleted."})

        level = int(request.form.get("level", existing["level"]) or 0)
        if level < 0 or level > 100:
            return jsonify({"error": "level must be 0-100."}), 400

        conn.execute(
            """
            UPDATE skills
            SET name = ?, level = ?, focus = ?, sort_order = ?, updated_at = ?
            WHERE id = ?
            """,
            (
                request.form.get("name", existing["name"]).strip(),
                level,
                request.form.get("focus", existing["focus"] or "").strip(),
                int(request.form.get("sort_order", existing["sort_order"]) or 0),
                now_iso(),
                item_id,
            ),
        )
        conn.commit()

    return jsonify({"message": "Skill updated."})


@app.route("/send_message", methods=["POST"])
def send_message():
    # Collect form data
    fullname = request.form.get("fullname", "").strip()
    email = request.form.get("email", "").strip()
    company = request.form.get("company", "").strip()
    subject = request.form.get("subject", "").strip()
    message_body = request.form.get("message", "").strip()
    newsletter_opt_in = request.form.get("newsletter-opt-in") == "yes"

    # Validate required fields
    if not fullname:
        flash("Please provide your full name.", "error")
        return redirect(url_for("index"))
    
    if not email:
        flash("Please provide a valid email address.", "error")
        return redirect(url_for("index"))
    
    if not subject:
        flash("Please provide a subject for your message.", "error")
        return redirect(url_for("index"))
    
    if not message_body or len(message_body) < 10:
        flash("Your message should be at least 10 characters long.", "error")
        return redirect(url_for("index"))

    # Build the email
    email_body = f"""New Contact Form Submission
==========================================

From: {fullname}
Email: {email}
Company: {company if company else 'Not provided'}
Newsletter Opt-in: {'Yes' if newsletter_opt_in else 'No'}

Subject: {subject}

Message:
{message_body}
"""

    try:
        msg = Message(
            subject=f"Portfolio Contact: {subject}",
            sender=app.config["MAIL_USERNAME"],
            recipients=["Rone_peh@hotmail.com"],
            body=email_body,
            reply_to=email,
        )
        mail.send(msg)
        flash("Message sent successfully. I'll get back to you soon!", "success")
    except Exception as e:
        print(f"Mail error: {e}")
        flash("Message could not be sent right now. Please try again later or email directly.", "error")

    return redirect(url_for("index"))


if __name__ == "__main__":
    app.run(debug=True)
