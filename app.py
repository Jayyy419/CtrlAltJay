import os
import time
import hmac
import uuid
from datetime import datetime
from decimal import Decimal
from functools import wraps
from pathlib import Path

import boto3
from boto3.dynamodb.conditions import Attr

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
UPLOAD_DIR = BASE_DIR / "static" / "uploads"
ALLOWED_IMAGE_EXT = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg", ".ico"}

AWS_REGION = os.getenv("AWS_REGION", "ap-southeast-1")
dynamodb = boto3.resource("dynamodb", region_name=AWS_REGION)
table_items = dynamodb.Table("ctrlaltjay-portfolio-items")
table_resume = dynamodb.Table("ctrlaltjay-resume-items")
table_skills = dynamodb.Table("ctrlaltjay-skills")

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "change-this-secret")
app.config["MAIL_SERVER"] = os.getenv("MAIL_SERVER", "default_server")
app.config["MAIL_PORT"] = int(os.getenv("MAIL_PORT", 587))
app.config["MAIL_USERNAME"] = os.getenv("MAIL_USERNAME", "default_username")
app.config["MAIL_PASSWORD"] = os.getenv("MAIL_PASSWORD", "default_password")
app.config["MAIL_USE_TLS"] = os.getenv("MAIL_USE_TLS", "true").lower() in ["true", "1", "t"]
app.config["MAIL_USE_SSL"] = os.getenv("MAIL_USE_SSL", "false").lower() in ["true", "1", "t"]
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024  # 16 MB upload limit

mail = Mail(app)

DEFAULT_ADMIN_PASSCODE_HASH = generate_password_hash("controlalternatejay")
MAX_ADMIN_ATTEMPTS = 5
ADMIN_LOCK_SECONDS = 600

PORTFOLIO_ITEM_FIELDS = [
    "section", "category", "subsection", "title", "byline", "tag",
    "summary", "description", "date_label", "date_value", "deliverables",
    "challenges", "future_improvements", "extra_notes", "image_path",
    "external_link",
]


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

    safe_name = secure_filename(upload.filename)
    if not safe_name:
        return ""
    ext = os.path.splitext(safe_name)[1].lower()
    if ext not in ALLOWED_IMAGE_EXT:
        return ""

    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    stamped_name = f"{int(datetime.utcnow().timestamp())}_{safe_name}"
    destination = UPLOAD_DIR / stamped_name
    upload.save(destination)
    return f"../static/uploads/{stamped_name}"


def dynamo_to_dict(item):
    """Convert DynamoDB item (with Decimals) to JSON-safe dict."""
    result = {}
    for k, v in item.items():
        if isinstance(v, Decimal):
            result[k] = int(v) if v == int(v) else float(v)
        else:
            result[k] = v
    return result


@app.before_request
def ensure_upload_dir():
    if not getattr(app, "_dirs_ready", False):
        UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
        app._dirs_ready = True


@app.after_request
def set_security_headers(response):
    response.headers["Content-Type"] = response.headers.get(
        "Content-Type", "text/html; charset=utf-8"
    )
    response.headers["Strict-Transport-Security"] = (
        "max-age=63072000; includeSubDomains; preload"
    )
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline' 'unsafe-eval' https://cdn.tailwindcss.com https://unpkg.com; "
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
        "font-src 'self' https://fonts.gstatic.com; "
        "img-src 'self' data: blob:; "
        "connect-src 'self'; "
        "frame-ancestors 'none'; "
        "base-uri 'self'; "
        "form-action 'self'"
    )
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = (
        "camera=(), microphone=(), geolocation=(), payment=()"
    )
    response.headers["Cross-Origin-Opener-Policy"] = "same-origin"
    response.headers["Cross-Origin-Embedder-Policy"] = "unsafe-none"
    response.headers["Cross-Origin-Resource-Policy"] = "same-origin"
    response.headers["X-Permitted-Cross-Domain-Policies"] = "none"
    return response


@app.route("/")
def index():
    profile = {
        "name": "Rone Peh",
        "headline": "Information Technology student @ NYP | SWE Intern @ J.P. Morgan Chase",
        "location": "Singapore",
        "email": "Rone_peh@hotmail.com",
        "phone": "+65 8808 1760",
        "credly": "https://www.credly.com/users/ronepeh",
        "github": "https://github.com/Jayyy419",
        "linkedin": "https://www.linkedin.com/in/ronepeh",
        "bio": (
            "I'm an Information Technology student who enjoys turning ideas into systems that actually work "
            "in real environments \u2014 not just for assignments, but for teams, organisations, and users. "
            "I've had hands-on exposure to software development, web technologies, and process automation "
            "through internships and student-led initiatives, where I've worked on building internal tools, "
            "improving workflows, and collaborating across technical and non-technical stakeholders. "
            "I'm especially interested in how technology can streamline operations and scale impact "
            "without overengineering. Alongside my technical work, I've taken on leadership responsibilities "
            "in a growing organisation, helping to shape processes, manage projects end-to-end, and build "
            "things from the ground up. I'm driven by curiosity, ownership, and continuous improvement."
        ),
        "now_building": [
            {
                "title": "Cloud Migration @ JPMC",
                "description": "Working on server workloads migration from on-premise to public cloud within Currencies & Emerging Markets.",
            },
            {
                "title": "ASEAN Youth Advocates",
                "description": "Leading operations and finance to strengthen organisational sustainability and programme delivery.",
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
    items_resp = table_items.scan()
    all_items = [dynamo_to_dict(i) for i in items_resp.get("Items", [])]

    projects = [i for i in all_items if i.get("section") == "project"]
    experiences = [i for i in all_items if i.get("section") == "experience"]

    resume_resp = table_resume.scan()
    resume_items = sorted(
        [dynamo_to_dict(i) for i in resume_resp.get("Items", [])],
        key=lambda x: (x.get("lane", ""), x.get("sort_order", 0), x.get("id", "")),
    )

    skills_resp = table_skills.scan()
    skills = sorted(
        [dynamo_to_dict(i) for i in skills_resp.get("Items", [])],
        key=lambda x: (x.get("sort_order", 0), x.get("id", "")),
    )

    return jsonify(
        {
            "projects": projects,
            "experiences": experiences,
            "resume": resume_items,
            "skills": skills,
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
        return jsonify({"message": "Authenticated.", "redirect_url": url_for("index")})

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
def admin_dashboard():
    if session.get("is_admin"):
        return redirect(url_for("index"))
    return redirect(url_for("index") + "?admin=login")


@app.route("/api/admin/items", methods=["GET", "POST"])
def api_admin_items():
    unauthorized = unauthorized_admin_response()
    if unauthorized:
        return unauthorized
    
    if request.method == "GET":
        section = request.args.get("section", "").strip().lower()
        response = table_items.scan()
        all_items = [dynamo_to_dict(i) for i in response.get("Items", [])]

        if section in {"project", "experience"}:
            all_items = [i for i in all_items if i.get("section") == section]

        all_items.sort(key=lambda x: x.get("updated_at", ""), reverse=True)
        return jsonify(all_items)

    image_path = save_uploaded_image(request.files.get("image"))
    now = now_iso()
    section = request.form.get("section", "").strip().lower()
    category = request.form.get("category", "").strip()
    payload = {
        "section": section,
        "category": category,
        "subsection": category if section == "experience" else "",
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

    payload["id"] = str(uuid.uuid4())
    payload["created_at"] = now
    payload["updated_at"] = now
    table_items.put_item(Item=payload)

    return jsonify({"message": "Item created."}), 201


@app.route("/api/admin/items/<item_id>", methods=["PUT", "DELETE"])
def api_admin_item(item_id):
    unauthorized = unauthorized_admin_response()
    if unauthorized:
        return unauthorized
    
    response = table_items.get_item(Key={"id": item_id})
    existing = response.get("Item")

    if not existing:
        return jsonify({"error": "Item not found."}), 404

    if request.method == "DELETE":
        table_items.delete_item(Key={"id": item_id})
        return jsonify({"message": "Item deleted."})

    form = request.form
    image_path = save_uploaded_image(request.files.get("image"))
    updated_at = now_iso()
    section = form.get("section", existing.get("section", "")).strip().lower()
    category = form.get("category", existing.get("category", "")).strip()
    updated_payload = {
        "section": section,
        "category": category,
        "subsection": category if section == "experience" else existing.get("subsection", ""),
        "title": form.get("title", existing.get("title", "")).strip(),
        "byline": form.get("byline", existing.get("byline", "")).strip(),
        "tag": form.get("tag", existing.get("tag", "")).strip(),
        "summary": form.get("summary", existing.get("summary", "")).strip(),
        "description": form.get("description", existing.get("description", "")).strip(),
        "date_label": form.get("date_label", existing.get("date_label", "")).strip(),
        "date_value": form.get("date_value", existing.get("date_value", "")).strip(),
        "deliverables": form.get("deliverables", existing.get("deliverables", "")).strip(),
        "challenges": form.get("challenges", existing.get("challenges", "")).strip(),
        "future_improvements": form.get("future_improvements", existing.get("future_improvements", "")).strip(),
        "extra_notes": form.get("extra_notes", existing.get("extra_notes", "")).strip(),
        "image_path": image_path or form.get("image_path", existing.get("image_path", "")).strip(),
        "external_link": form.get("external_link", existing.get("external_link", "")).strip(),
    }

    updated_payload["id"] = item_id
    updated_payload["created_at"] = existing.get("created_at", "")
    updated_payload["updated_at"] = updated_at
    table_items.put_item(Item=updated_payload)

    return jsonify({"message": "Item updated."})


@app.route("/api/admin/resume", methods=["GET", "POST"])
def api_admin_resume():
    unauthorized = unauthorized_admin_response()
    if unauthorized:
        return unauthorized
    
    if request.method == "GET":
        response = table_resume.scan()
        items = sorted(
            [dynamo_to_dict(i) for i in response.get("Items", [])],
            key=lambda x: (x.get("lane", ""), x.get("sort_order", 0), x.get("id", "")),
        )
        return jsonify(items)

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

    table_resume.put_item(Item={
        "id": str(uuid.uuid4()),
        "lane": lane,
        "title": title,
        "subtitle": subtitle,
        "period": period,
        "description": description,
        "sort_order": Decimal(str(sort_order)),
        "created_at": now,
        "updated_at": now,
    })
    return jsonify({"message": "Resume item created."}), 201


@app.route("/api/admin/resume/<item_id>", methods=["PUT", "DELETE"])
def api_admin_resume_item(item_id):
    unauthorized = unauthorized_admin_response()
    if unauthorized:
        return unauthorized
    
    response = table_resume.get_item(Key={"id": item_id})
    existing = response.get("Item")
    if not existing:
        return jsonify({"error": "Resume item not found."}), 404

    if request.method == "DELETE":
        table_resume.delete_item(Key={"id": item_id})
        return jsonify({"message": "Resume item deleted."})

    lane = request.form.get("lane", existing.get("lane", "")).strip().lower()
    if lane not in {"education", "work"}:
        return jsonify({"error": "lane must be education or work."}), 400

    table_resume.put_item(Item={
        "id": item_id,
        "lane": lane,
        "title": request.form.get("title", existing.get("title", "")).strip(),
        "subtitle": request.form.get("subtitle", existing.get("subtitle", "")).strip(),
        "period": request.form.get("period", existing.get("period", "")).strip(),
        "description": request.form.get("description", existing.get("description", "")).strip(),
        "sort_order": Decimal(str(int(request.form.get("sort_order", existing.get("sort_order", 0)) or 0))),
        "created_at": existing.get("created_at", ""),
        "updated_at": now_iso(),
    })

    return jsonify({"message": "Resume item updated."})


@app.route("/api/admin/skills", methods=["GET", "POST"])
def api_admin_skills():
    unauthorized = unauthorized_admin_response()
    if unauthorized:
        return unauthorized
    
    if request.method == "GET":
        response = table_skills.scan()
        items = sorted(
            [dynamo_to_dict(i) for i in response.get("Items", [])],
            key=lambda x: (x.get("sort_order", 0), x.get("id", "")),
        )
        return jsonify(items)

    now = now_iso()
    name = request.form.get("name", "").strip()
    level = int(request.form.get("level", "0") or 0)
    focus = request.form.get("focus", "").strip()
    sort_order = int(request.form.get("sort_order", "0") or 0)

    if not name or level < 0 or level > 100:
        return jsonify({"error": "name is required and level must be 0-100."}), 400

    table_skills.put_item(Item={
        "id": str(uuid.uuid4()),
        "name": name,
        "level": Decimal(str(level)),
        "focus": focus,
        "sort_order": Decimal(str(sort_order)),
        "created_at": now,
        "updated_at": now,
    })
    return jsonify({"message": "Skill created."}), 201


@app.route("/api/admin/skills/<item_id>", methods=["PUT", "DELETE"])
def api_admin_skill_item(item_id):
    unauthorized = unauthorized_admin_response()
    if unauthorized:
        return unauthorized
    
    response = table_skills.get_item(Key={"id": item_id})
    existing = response.get("Item")
    if not existing:
        return jsonify({"error": "Skill not found."}), 404

    if request.method == "DELETE":
        table_skills.delete_item(Key={"id": item_id})
        return jsonify({"message": "Skill deleted."})

    level = int(request.form.get("level", existing.get("level", 0)) or 0)
    if level < 0 or level > 100:
        return jsonify({"error": "level must be 0-100."}), 400

    table_skills.put_item(Item={
        "id": item_id,
        "name": request.form.get("name", existing.get("name", "")).strip(),
        "level": Decimal(str(level)),
        "focus": request.form.get("focus", existing.get("focus", "")).strip(),
        "sort_order": Decimal(str(int(request.form.get("sort_order", existing.get("sort_order", 0)) or 0))),
        "created_at": existing.get("created_at", ""),
        "updated_at": now_iso(),
    })

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
