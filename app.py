import os
import re
import secrets
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
from werkzeug.middleware.proxy_fix import ProxyFix
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename

import json

try:
    from PIL import Image as PILImage
    HAS_PILLOW = True
except ImportError:
    HAS_PILLOW = False

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent
UPLOAD_DIR = BASE_DIR / "static" / "uploads"
ALLOWED_IMAGE_EXT = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".ico"}
# .svg intentionally excluded: an uploaded SVG can embed <script>, which executes
# if the file is ever opened via direct navigation (not just <img src>) — the
# current CSP allows 'unsafe-inline' script-src, so it wouldn't block this.

AWS_REGION = os.getenv("AWS_REGION", "ap-southeast-1")
dynamodb = boto3.resource("dynamodb", region_name=AWS_REGION)
table_items = dynamodb.Table("ctrlaltjay-portfolio-items")
table_resume = dynamodb.Table("ctrlaltjay-resume-items")
table_skills = dynamodb.Table("ctrlaltjay-skills")

app = Flask(__name__)

_secret_key = os.getenv("SECRET_KEY", "").strip()
if not _secret_key or _secret_key == "change-this-secret":
    raise RuntimeError(
        "SECRET_KEY is not set (or is still the placeholder from .env.example). "
        "Flask signs session cookies — including the admin login flag — with this "
        "key, so an unset/default value lets anyone forge an authenticated admin "
        "session. Set a long random SECRET_KEY environment variable before starting "
        "the app."
    )
app.secret_key = _secret_key

# Trust the single reverse proxy (nginx, per .platform config) for client IP/proto
# so request.remote_addr reflects the real visitor instead of 127.0.0.1.
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

def _resolve_secret(env_var, secret_id_env_var, default=""):
    """Read a config value from AWS Secrets Manager if <secret_id_env_var> is
    set (naming a secret name or ARN), otherwise fall back to the plain
    <env_var> environment variable. Never raises — a Secrets Manager fetch
    failure degrades to the env var/default rather than crashing the app,
    matching how mail errors are already handled elsewhere (best-effort,
    not security-critical like SECRET_KEY/admin passcode)."""
    secret_id = os.getenv(secret_id_env_var, "").strip()
    if secret_id:
        try:
            sm = boto3.client("secretsmanager", region_name=AWS_REGION)
            return sm.get_secret_value(SecretId=secret_id)["SecretString"]
        except Exception as e:
            print(f"WARNING: could not fetch secret {secret_id!r} ({secret_id_env_var}): {e}", flush=True)
    return os.getenv(env_var, default)


app.config["MAIL_SERVER"] = os.getenv("MAIL_SERVER", "default_server")
app.config["MAIL_PORT"] = int(os.getenv("MAIL_PORT", 587))
app.config["MAIL_USERNAME"] = os.getenv("MAIL_USERNAME", "default_username")
app.config["MAIL_PASSWORD"] = _resolve_secret("MAIL_PASSWORD", "MAIL_PASSWORD_SECRET_ID", "default_password")
app.config["MAIL_USE_TLS"] = os.getenv("MAIL_USE_TLS", "true").lower() in ["true", "1", "t"]
app.config["MAIL_USE_SSL"] = os.getenv("MAIL_USE_SSL", "false").lower() in ["true", "1", "t"]
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024  # 16 MB upload limit

# Session cookie hardening — explicit rather than relying on framework/browser defaults.
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["SESSION_COOKIE_SECURE"] = os.getenv("FLASK_DEBUG", "").lower() not in ("1", "true", "t")

mail = Mail(app)

if not any(
    os.getenv(name, "").strip()
    for name in ("ADMIN_PASSCODE_HASH", "ADMIN_PASSCODE", "ADMIN_PASSWORD")
):
    print(
        "WARNING: No admin passcode is configured (ADMIN_PASSCODE_HASH, "
        "ADMIN_PASSCODE, or ADMIN_PASSWORD) — admin login is disabled until "
        "one is set.",
        flush=True,
    )

MAX_ADMIN_ATTEMPTS = 5
ADMIN_LOCK_SECONDS = 600
MAX_CONTACT_ATTEMPTS = 5
CONTACT_RATE_WINDOW_SECONDS = 600
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

PORTFOLIO_ITEM_FIELDS = [
    "additional_images", "byline", "category", "challenges",
    "credential_url", "date_label", "date_value", "deliverables",
    "description", "external_link", "extra_notes", "future_improvements",
    "image_path", "section", "skills", "status", "subsection", "summary",
    "tag", "title",
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
    # ADMIN_PASSWORD is accepted as a legacy alias for ADMIN_PASSCODE — earlier
    # versions of the docs told deployers to set that name instead.
    configured_plain = (
        os.getenv("ADMIN_PASSCODE", "").strip()
        or os.getenv("ADMIN_PASSWORD", "").strip()
    )

    if configured_hash:
        return check_password_hash(configured_hash, submitted_passcode)

    if configured_plain:
        return hmac.compare_digest(configured_plain, submitted_passcode)

    # No admin passcode configured — fail closed instead of falling back to a
    # hardcoded default (which would be visible to anyone reading this source).
    return False


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

    # Optimise with Pillow when available (skip SVG/ICO)
    if HAS_PILLOW and ext in {".jpg", ".jpeg", ".png", ".webp"}:
        try:
            with PILImage.open(destination) as img:
                if img.mode in ("RGBA", "P") and ext in {".jpg", ".jpeg"}:
                    img = img.convert("RGB")
                max_w = 1200
                if img.width > max_w:
                    ratio = max_w / img.width
                    img = img.resize((max_w, int(img.height * ratio)), PILImage.LANCZOS)
                save_kw = {"optimize": True}
                if ext in {".jpg", ".jpeg"}:
                    img.save(destination, "JPEG", quality=85, **save_kw)
                elif ext == ".png":
                    img.save(destination, "PNG", **save_kw)
                elif ext == ".webp":
                    img.save(destination, "WEBP", quality=85)
        except Exception:
            pass  # keep original if optimisation fails

    return f"../static/uploads/{stamped_name}"


def save_additional_images(files):
    """Save multiple uploaded images, return comma-separated paths."""
    return ",".join(filter(None, (save_uploaded_image(f) for f in files)))


def scan_all(table):
    """Scan a DynamoDB table across pages — table.scan() alone caps out at
    1MB per call and silently truncates larger tables via LastEvaluatedKey."""
    items = []
    kwargs = {}
    while True:
        resp = table.scan(**kwargs)
        items.extend(resp.get("Items", []))
        last_key = resp.get("LastEvaluatedKey")
        if not last_key:
            break
        kwargs["ExclusiveStartKey"] = last_key
    return items


def dynamo_to_dict(item):
    """Convert DynamoDB item (with Decimals) to JSON-safe dict."""
    result = {}
    for k, v in item.items():
        if isinstance(v, Decimal):
            result[k] = int(v) if v == int(v) else float(v)
        else:
            result[k] = v
    return result


# ─── IP-based rate limiting (shared table, DynamoDB-backed so it works across
# multiple gunicorn workers/instances — unlike session-based counters, which
# an attacker can reset just by dropping cookies) ───────────────────────────

def _client_ip():
    return request.remote_addr or "unknown"


def _rate_limit_id(bucket, ip):
    return f"__ratelimit_{bucket}_{ip}"


def _rate_limit_locked_seconds(bucket, ip):
    """Seconds remaining in an active lockout for this bucket/ip, or 0 if none."""
    resp = table_items.get_item(Key={"id": _rate_limit_id(bucket, ip)})
    item = resp.get("Item")
    if not item:
        return 0
    remaining = int(item.get("lock_until", 0)) - int(time.time())
    return max(0, remaining)


def _record_rate_limit_failure(bucket, ip, max_attempts, lock_seconds):
    """Record a failed attempt. Returns (locked_out, remaining_attempts)."""
    key = _rate_limit_id(bucket, ip)
    resp = table_items.get_item(Key={"id": key})
    existing = resp.get("Item") or {}
    attempts = int(existing.get("attempts", 0)) + 1

    if attempts >= max_attempts:
        table_items.put_item(Item={
            "id": key,
            "attempts": Decimal(0),
            "lock_until": Decimal(int(time.time()) + lock_seconds),
            "updated_at": now_iso(),
        })
        return True, 0

    table_items.put_item(Item={
        "id": key,
        "attempts": Decimal(attempts),
        "lock_until": Decimal(0),
        "updated_at": now_iso(),
    })
    return False, max_attempts - attempts


def _clear_rate_limit(bucket, ip):
    table_items.delete_item(Key={"id": _rate_limit_id(bucket, ip)})


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
        "connect-src 'self' https://unpkg.com; "
        "manifest-src 'self'; "
        "worker-src 'self'; "
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
    # Cache static assets for CDN / browser caching
    if request.path.startswith("/static/"):
        response.headers["Cache-Control"] = "public, max-age=86400"
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


_public_data_cache = {"payload": None, "expires_at": 0.0}
PUBLIC_DATA_CACHE_SECONDS = 30


def invalidate_public_data_cache():
    _public_data_cache["payload"] = None
    _public_data_cache["expires_at"] = 0.0


@app.route("/api/public-data")
def api_public_data():
    now = time.time()
    cached = _public_data_cache["payload"]
    if cached is not None and _public_data_cache["expires_at"] > now:
        return jsonify(cached)

    all_items = [dynamo_to_dict(i) for i in scan_all(table_items) if not i.get("id", "").startswith("__") and not i.get("deleted_at")]

    projects = [i for i in all_items if i.get("section") == "project"]
    experiences = [i for i in all_items if i.get("section") == "experience"]

    resume_items = sorted(
        [dynamo_to_dict(i) for i in scan_all(table_resume)],
        key=lambda x: (x.get("lane", ""), x.get("sort_order", 0), x.get("id", "")),
    )

    skills = sorted(
        [dynamo_to_dict(i) for i in scan_all(table_skills)],
        key=lambda x: (x.get("sort_order", 0), x.get("id", "")),
    )

    payload = {
        "projects": projects,
        "experiences": experiences,
        "resume": resume_items,
        "skills": skills,
    }
    _public_data_cache["payload"] = payload
    _public_data_cache["expires_at"] = now + PUBLIC_DATA_CACHE_SECONDS
    return jsonify(payload)


@app.route("/api/admin/auth-status", methods=["GET"])
def admin_auth_status():
    return jsonify({"is_admin": bool(session.get("is_admin"))})


@app.route("/admin/auth", methods=["POST"])
def admin_auth():
    ip = _client_ip()
    remaining_lock = _rate_limit_locked_seconds("admin", ip)
    if remaining_lock > 0:
        return jsonify({"error": "Too many attempts. Please wait and try again.", "retry_in": remaining_lock}), 429

    payload = request.get_json(silent=True) or {}
    submitted_passcode = (
        payload.get("passcode")
        or request.form.get("passcode", "")
    ).strip()

    if not submitted_passcode:
        return jsonify({"error": "Passcode is required."}), 400

    if verify_admin_passcode(submitted_passcode):
        session["is_admin"] = True
        _clear_rate_limit("admin", ip)
        return jsonify({"message": "Authenticated.", "redirect_url": url_for("index")})

    locked_out, remaining_attempts = _record_rate_limit_failure(
        "admin", ip, MAX_ADMIN_ATTEMPTS, ADMIN_LOCK_SECONDS
    )
    if locked_out:
        return jsonify({"error": "Too many attempts. Please wait and try again."}), 429

    return jsonify({"error": "Invalid passcode.", "remaining_attempts": remaining_attempts}), 401


@app.route("/admin/logout", methods=["GET", "POST"])
def admin_logout():
    session.pop("is_admin", None)
    if request.method == "POST":
        resp = jsonify({"ok": True})
        resp.headers["Clear-Site-Data"] = '"cache", "storage"'
        return resp
    resp = redirect(url_for("index"))
    resp.headers["Clear-Site-Data"] = '"cache", "storage"'
    return resp


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
        all_items = [dynamo_to_dict(i) for i in scan_all(table_items) if not i.get("id", "").startswith("__") and not i.get("deleted_at")]

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
        "skills": request.form.get("skills", "").strip(),
        "status": request.form.get("status", "").strip(),
        "credential_url": request.form.get("credential_url", "").strip(),
    }

    # Additional images
    add_files = request.files.getlist("additional_images")
    new_adds = save_additional_images(add_files)
    existing_adds = request.form.get("existing_additional_images", "").strip()
    payload["additional_images"] = ",".join(filter(None, [existing_adds, new_adds]))

    required_ok = payload["section"] in {"project", "experience"} and payload["category"] and payload["title"]
    if not required_ok:
        return jsonify({"error": "section, category, and title are required."}), 400

    payload["id"] = str(uuid.uuid4())
    payload["created_at"] = now
    payload["updated_at"] = now
    table_items.put_item(Item=payload)
    invalidate_public_data_cache()

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
        table_items.update_item(
            Key={"id": item_id},
            UpdateExpression="SET deleted_at = :ts",
            ExpressionAttributeValues={":ts": now_iso()},
        )
        invalidate_public_data_cache()
        return jsonify({"message": "Item moved to Recently Deleted."})

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
        "skills": form.get("skills", existing.get("skills", "")).strip(),
        "status": form.get("status", existing.get("status", "")).strip(),
        "credential_url": form.get("credential_url", existing.get("credential_url", "")).strip(),
    }

    # Additional images
    add_files = request.files.getlist("additional_images")
    new_adds = save_additional_images(add_files)
    existing_adds = form.get("existing_additional_images", existing.get("additional_images", "")).strip()
    updated_payload["additional_images"] = ",".join(filter(None, [existing_adds, new_adds]))

    updated_payload["id"] = item_id
    updated_payload["created_at"] = existing.get("created_at", "")
    updated_payload["updated_at"] = updated_at
    table_items.put_item(Item=updated_payload)
    invalidate_public_data_cache()

    return jsonify({"message": "Item updated."})


@app.route("/api/admin/items/<item_id>/clear-image", methods=["PATCH"])
def api_admin_item_clear_image(item_id):
    unauthorized = unauthorized_admin_response()
    if unauthorized:
        return unauthorized

    response = table_items.get_item(Key={"id": item_id})
    existing = response.get("Item")
    if not existing:
        return jsonify({"error": "Item not found."}), 404

    table_items.update_item(
        Key={"id": item_id},
        UpdateExpression="SET image_path = :empty, updated_at = :ts",
        ExpressionAttributeValues={":empty": "", ":ts": now_iso()},
    )
    invalidate_public_data_cache()
    return jsonify({"message": "Image cleared."})


@app.route("/api/admin/deleted-items", methods=["GET"])
def api_admin_deleted_items():
    unauthorized = unauthorized_admin_response()
    if unauthorized:
        return unauthorized
    deleted = [
        dynamo_to_dict(i)
        for i in scan_all(table_items)
        if not i.get("id", "").startswith("__") and i.get("deleted_at")
    ]
    deleted.sort(key=lambda x: x.get("deleted_at", ""), reverse=True)
    return jsonify(deleted)


@app.route("/api/admin/items/<item_id>/restore", methods=["POST"])
def api_admin_item_restore(item_id):
    unauthorized = unauthorized_admin_response()
    if unauthorized:
        return unauthorized
    response = table_items.get_item(Key={"id": item_id})
    existing = response.get("Item")
    if not existing or not existing.get("deleted_at"):
        return jsonify({"error": "Item not found in deleted items."}), 404
    table_items.update_item(
        Key={"id": item_id},
        UpdateExpression="REMOVE deleted_at",
    )
    invalidate_public_data_cache()
    return jsonify({"message": "Item restored."})


@app.route("/api/admin/items/<item_id>/permanent", methods=["DELETE"])
def api_admin_item_permanent(item_id):
    unauthorized = unauthorized_admin_response()
    if unauthorized:
        return unauthorized
    response = table_items.get_item(Key={"id": item_id})
    existing = response.get("Item")
    if not existing:
        return jsonify({"error": "Item not found."}), 404
    table_items.delete_item(Key={"id": item_id})
    return jsonify({"message": "Item permanently deleted."})


@app.route("/api/admin/resume", methods=["GET", "POST"])
def api_admin_resume():
    unauthorized = unauthorized_admin_response()
    if unauthorized:
        return unauthorized
    
    if request.method == "GET":
        items = sorted(
            [dynamo_to_dict(i) for i in scan_all(table_resume)],
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
    invalidate_public_data_cache()
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
        invalidate_public_data_cache()
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

    invalidate_public_data_cache()
    return jsonify({"message": "Resume item updated."})


@app.route("/api/admin/skills", methods=["GET", "POST"])
def api_admin_skills():
    unauthorized = unauthorized_admin_response()
    if unauthorized:
        return unauthorized
    
    if request.method == "GET":
        items = sorted(
            [dynamo_to_dict(i) for i in scan_all(table_skills)],
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
    invalidate_public_data_cache()
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
        invalidate_public_data_cache()
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

    invalidate_public_data_cache()
    return jsonify({"message": "Skill updated."})


@app.route("/send_message", methods=["POST"])
def send_message():
    ip = _client_ip()
    remaining_lock = _rate_limit_locked_seconds("contact", ip)
    if remaining_lock > 0:
        error_msg = "Too many messages sent recently. Please wait a bit before trying again."
        if request.headers.get("X-Requested-With") == "XMLHttpRequest":
            return jsonify({"error": error_msg, "retry_in": remaining_lock}), 429
        flash(error_msg, "error")
        return redirect(url_for("index"))
    _record_rate_limit_failure("contact", ip, MAX_CONTACT_ATTEMPTS, CONTACT_RATE_WINDOW_SECONDS)

    # Collect form data
    fullname = request.form.get("fullname", "").strip()
    email = request.form.get("email", "").strip()
    company = request.form.get("company", "").strip()
    subject = request.form.get("subject", "").strip()
    message_body = request.form.get("message", "").strip()
    reason = request.form.get("reason", "").strip()

    # Honeypot — silently reject bot submissions
    if request.form.get("website", "").strip():
        if request.headers.get("X-Requested-With") == "XMLHttpRequest":
            return jsonify({"message": "Message sent successfully. I'll get back to you soon!"})
        flash("Message sent successfully. I'll get back to you soon!", "success")
        return redirect(url_for("index"))

    # Validate required fields
    if not fullname:
        if request.headers.get("X-Requested-With") == "XMLHttpRequest":
            return jsonify({"error": "Please provide your full name."}), 400
        flash("Please provide your full name.", "error")
        return redirect(url_for("index"))

    if not email or not EMAIL_RE.match(email):
        if request.headers.get("X-Requested-With") == "XMLHttpRequest":
            return jsonify({"error": "Please provide a valid email address."}), 400
        flash("Please provide a valid email address.", "error")
        return redirect(url_for("index"))

    if not subject:
        if request.headers.get("X-Requested-With") == "XMLHttpRequest":
            return jsonify({"error": "Please provide a subject for your message."}), 400
        flash("Please provide a subject for your message.", "error")
        return redirect(url_for("index"))
    
    if not message_body or len(message_body) < 10:
        if request.headers.get("X-Requested-With") == "XMLHttpRequest":
            return jsonify({"error": "Your message should be at least 10 characters long."}), 400
        flash("Your message should be at least 10 characters long.", "error")
        return redirect(url_for("index"))

    # Build the email
    email_body = f"""New Contact Form Submission
==========================================

From: {fullname}
Email: {email}
Company: {company if company else 'Not provided'}
Reason: {reason if reason else 'Not specified'}

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
        if request.headers.get("X-Requested-With") == "XMLHttpRequest":
            return jsonify({"message": "Message sent successfully. I'll get back to you soon!"})
        flash("Message sent successfully. I'll get back to you soon!", "success")
    except Exception as e:
        print(f"Mail error: {e}")
        if request.headers.get("X-Requested-With") == "XMLHttpRequest":
            return jsonify({"error": "Message could not be sent right now. Please try again later or email directly."}), 500
        flash("Message could not be sent right now. Please try again later or email directly.", "error")

    return redirect(url_for("index"))


# ─── Resume Key (gated print) ───────────────────────────────────────────────

SETTINGS_ID = "__settings"


def _get_or_create_resume_key():
    """Return the current resume key, creating one if it doesn't exist."""
    resp = table_items.get_item(Key={"id": SETTINGS_ID})
    item = resp.get("Item")
    if item and item.get("resume_key"):
        return item["resume_key"]
    new_key = secrets.token_urlsafe(32)
    table_items.put_item(Item={
        "id": SETTINGS_ID,
        "resume_key": new_key,
        "created_at": now_iso(),
        "updated_at": now_iso(),
    })
    return new_key


@app.route("/api/resume-key/verify", methods=["POST"])
def resume_key_verify():
    payload = request.get_json(silent=True) or {}
    submitted = (payload.get("key") or "").strip()
    if not submitted:
        return jsonify({"error": "Key is required."}), 400
    actual = _get_or_create_resume_key()
    if hmac.compare_digest(submitted, actual):
        return jsonify({"ok": True})
    return jsonify({"error": "Invalid key."}), 403


@app.route("/api/admin/resume-key", methods=["GET"])
def admin_resume_key_get():
    unauthorized = unauthorized_admin_response()
    if unauthorized:
        return unauthorized
    key = _get_or_create_resume_key()
    return jsonify({"resume_key": key})


@app.route("/api/admin/resume-key/rotate", methods=["POST"])
def admin_resume_key_rotate():
    unauthorized = unauthorized_admin_response()
    if unauthorized:
        return unauthorized
    new_key = secrets.token_urlsafe(32)
    resp = table_items.get_item(Key={"id": SETTINGS_ID})
    existing = resp.get("Item") or {}
    table_items.put_item(Item={
        "id": SETTINGS_ID,
        "resume_key": new_key,
        "created_at": existing.get("created_at", now_iso()),
        "updated_at": now_iso(),
    })
    return jsonify({"resume_key": new_key, "message": "Key rotated."})


if __name__ == "__main__":
    debug_mode = os.getenv("FLASK_DEBUG", "").lower() in ("1", "true", "t")
    app.run(debug=debug_mode)


# ─── SEO: Sitemap & Robots ──────────────────────────────────────────────────

@app.route("/sitemap.xml")
def sitemap():
    all_items = [
        dynamo_to_dict(i)
        for i in scan_all(table_items)
        if not i.get("id", "").startswith("__")
    ]
    base_url = "https://ctrlaltjay.dev"
    now = datetime.utcnow().strftime("%Y-%m-%d")

    urls = [
        {"loc": f"{base_url}/", "lastmod": now, "priority": "1.0"},
        {"loc": f"{base_url}/#about", "lastmod": now, "priority": "0.8"},
        {"loc": f"{base_url}/#projects", "lastmod": now, "priority": "0.9"},
        {"loc": f"{base_url}/#experiences", "lastmod": now, "priority": "0.9"},
        {"loc": f"{base_url}/#resume", "lastmod": now, "priority": "0.7"},
        {"loc": f"{base_url}/#contact", "lastmod": now, "priority": "0.6"},
    ]

    for item in all_items:
        lastmod = (item.get("updated_at") or now)[:10]
        urls.append({
            "loc": f"{base_url}/#item/{item['id']}",
            "lastmod": lastmod,
            "priority": "0.6",
        })

    xml_entries = "\n".join(
        f"  <url>\n"
        f"    <loc>{u['loc']}</loc>\n"
        f"    <lastmod>{u['lastmod']}</lastmod>\n"
        f"    <priority>{u['priority']}</priority>\n"
        f"  </url>"
        for u in urls
    )

    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        f"{xml_entries}\n"
        "</urlset>"
    )

    response = app.response_class(xml, mimetype="application/xml")
    return response


@app.route("/robots.txt")
def robots():
    txt = (
        "User-agent: *\n"
        "Allow: /\n"
        "Sitemap: https://ctrlaltjay.dev/sitemap.xml\n"
    )
    return app.response_class(txt, mimetype="text/plain")


# ─── Error Pages ─────────────────────────────────────────────────────────────

@app.errorhandler(404)
def page_not_found(e):
    return render_template("404.html"), 404


@app.errorhandler(500)
def internal_error(e):
    return render_template(
        "404.html", error_code=500,
        error_message="Something went wrong on our end.",
    ), 500


# ─── Visitor Hit Counter ─────────────────────────────────────────────────────

@app.route("/api/hit-count", methods=["GET", "POST"])
def hit_count():
    if request.method == "POST":
        try:
            table_items.update_item(
                Key={"id": SETTINGS_ID},
                UpdateExpression="SET hit_count = if_not_exists(hit_count, :zero) + :inc",
                ExpressionAttributeValues={":inc": Decimal("1"), ":zero": Decimal("0")},
            )
        except Exception:
            pass
        return jsonify({"ok": True})
    resp = table_items.get_item(Key={"id": SETTINGS_ID})
    item = resp.get("Item", {})
    count = int(item.get("hit_count", 0))
    return jsonify({"count": count})


# ─── Auto-Backup to S3 ──────────────────────────────────────────────────────

@app.route("/api/admin/backup", methods=["POST"])
def admin_backup():
    unauthorized = unauthorized_admin_response()
    if unauthorized:
        return unauthorized
    bucket = os.getenv("BACKUP_S3_BUCKET", "").strip()
    if not bucket:
        return jsonify({"error": "BACKUP_S3_BUCKET is not configured."}), 500
    try:
        s3 = boto3.client("s3", region_name=AWS_REGION)
        timestamp = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
        tables = {
            "portfolio-items": table_items,
            "resume-items": table_resume,
            "skills": table_skills,
        }
        for name, tbl in tables.items():
            items_list = [dynamo_to_dict(i) for i in scan_all(tbl)]
            s3.put_object(
                Bucket=bucket,
                Key=f"backups/{timestamp}/{name}.json",
                Body=json.dumps(items_list, indent=2, default=str),
                ContentType="application/json",
            )
        return jsonify({"message": f"Backup saved to s3://{bucket}/backups/{timestamp}/"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ─── Admin JSON Import ──────────────────────────────────────────────────────

ALLOWED_IMPORT_FIELDS = set(PORTFOLIO_ITEM_FIELDS)


@app.route("/api/admin/import", methods=["POST"])
def admin_import():
    unauthorized = unauthorized_admin_response()
    if unauthorized:
        return unauthorized
    try:
        payload = request.get_json(silent=True)
        if not payload:
            return jsonify({"error": "No JSON data provided."}), 400

        # Accept flat list, or { projects: [], experiences: [] } shape
        if isinstance(payload, list):
            items = payload
        else:
            items = []
            if isinstance(payload.get("projects"), list):
                items.extend(payload["projects"])
            if isinstance(payload.get("experiences"), list):
                items.extend(payload["experiences"])

        created = 0
        for item in items:
            if not isinstance(item, dict):
                continue
            title = (item.get("title") or "").strip()
            section = (item.get("section") or "").strip().lower()
            if not title or section not in {"project", "experience"}:
                continue

            clean = {}
            for k, v in item.items():
                if k in ALLOWED_IMPORT_FIELDS and isinstance(v, str):
                    clean[k] = v.strip()
            clean["title"] = title
            clean["section"] = section
            clean["id"] = str(uuid.uuid4())
            clean["created_at"] = now_iso()
            clean["updated_at"] = now_iso()
            table_items.put_item(Item=clean)
            created += 1

        if created:
            invalidate_public_data_cache()
        return jsonify({"message": f"Imported {created} item(s)."})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ─── PWA: Service Worker & Manifest ─────────────────────────────────────────

@app.route("/sw.js")
def service_worker():
    response = app.send_static_file("sw.js")
    response.headers["Service-Worker-Allowed"] = "/"
    response.headers["Content-Type"] = "application/javascript"
    response.headers["Cache-Control"] = "no-cache"
    return response


@app.route("/manifest.json")
def manifest():
    return app.send_static_file("manifest.json")
