"""Casebook: the owner-only interview and application prep area.

Everything here sits behind the owner session. Signed-out requests get an
empty 404, so the routes look the same as ones that don't exist.
"""
import os
import re
import uuid
from datetime import datetime, timezone
from decimal import Decimal

from flask import Blueprint, abort, jsonify, request

OCCASIONS = {
    "interview": "Internship or job interview",
    "volunteering": "Overseas volunteering or community trip",
    "scholarship": "Scholarship or exchange application",
    "pitch": "Competition or hackathon pitch",
    "leadership": "CCA or leadership interview",
    "networking": "Networking chat",
}
FORMATS = {
    "online_assessment": "Online assessment",
    "video": "Video interview",
    "panel": "Panel",
    "case": "Case interview",
    "technical": "Technical round",
    "group": "Group activity",
    "unknown": "Not known yet",
}
STAR_FIELDS = ("situation", "task", "action", "result")
TEXT_LIMITS = {"organisation": 120, "role": 160, "notes": 4000, "posting_url": 500, "title": 160}
STORY_FIELD_LIMIT = 2000
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

bp = Blueprint("casebook", __name__)


def _now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _clean(value, limit):
    return str(value or "").strip()[:limit]


def _plain(item):
    out = {}
    for k, v in item.items():
        if isinstance(v, Decimal):
            out[k] = int(v) if v == v.to_integral_value() else float(v)
        else:
            out[k] = v
    return out


def _casebook_fields(payload, partial=False):
    fields, errors = {}, []
    if "occasion" in payload or not partial:
        occasion = payload.get("occasion")
        if occasion not in OCCASIONS:
            errors.append("occasion")
        else:
            fields["occasion"] = occasion
    if "organisation" in payload or not partial:
        org = _clean(payload.get("organisation"), TEXT_LIMITS["organisation"])
        if not org:
            errors.append("organisation")
        fields["organisation"] = org
    for key in ("role", "notes"):
        if key in payload or not partial:
            fields[key] = _clean(payload.get(key), TEXT_LIMITS[key])
    if "date" in payload or not partial:
        date = _clean(payload.get("date"), 10)
        if date and not DATE_RE.match(date):
            errors.append("date")
        fields["date"] = date
    if "format" in payload or not partial:
        fmt = payload.get("format") or "unknown"
        if fmt not in FORMATS:
            errors.append("format")
        fields["format"] = fmt
    if "posting_url" in payload or not partial:
        url = _clean(payload.get("posting_url"), TEXT_LIMITS["posting_url"])
        if url and not url.startswith(("https://", "http://")):
            errors.append("posting_url")
        fields["posting_url"] = url
    return fields, errors


def _story_fields(payload):
    fields = {"title": _clean(payload.get("title"), TEXT_LIMITS["title"])}
    for key in STAR_FIELDS:
        fields[key] = _clean(payload.get(key), STORY_FIELD_LIMIT)
    for key in ("item_ids", "skills"):
        values = payload.get(key) or []
        if not isinstance(values, list):
            values = []
        fields[key] = [_clean(v, 160) for v in values if _clean(v, 160)][:30]
    errors = [] if fields["title"] else ["title"]
    return fields, errors


def register_casebook(app, is_owner, dynamodb):
    casebooks = dynamodb.Table(os.getenv("CASEBOOKS_TABLE", "ctrlaltjay-casebooks"))
    stories = dynamodb.Table(os.getenv("STORIES_TABLE", "ctrlaltjay-stories"))

    @bp.before_request
    def owner_only():
        # Deny by default: nothing below runs for anyone but the owner.
        if not is_owner():
            abort(404)

    @bp.after_request
    def private_headers(response):
        response.headers["Cache-Control"] = "no-store, private"
        response.headers["X-Robots-Tag"] = "noindex, nofollow, noarchive"
        return response

    def _rows(case_id):
        resp = casebooks.query(
            KeyConditionExpression="pk = :pk",
            ExpressionAttributeValues={":pk": f"CASE#{case_id}"},
        )
        rows = resp.get("Items", [])
        while resp.get("LastEvaluatedKey"):
            resp = casebooks.query(
                KeyConditionExpression="pk = :pk",
                ExpressionAttributeValues={":pk": f"CASE#{case_id}"},
                ExclusiveStartKey=resp["LastEvaluatedKey"],
            )
            rows += resp.get("Items", [])
        return rows

    def _meta(case_id):
        item = casebooks.get_item(Key={"pk": f"CASE#{case_id}", "sk": "META"}).get("Item")
        if not item:
            abort(404)
        return item

    @bp.route("/api/owner/casebook/options", methods=["GET"])
    def options():
        return jsonify({"occasions": OCCASIONS, "formats": FORMATS})

    @bp.route("/api/owner/casebooks", methods=["GET", "POST"])
    def casebook_collection():
        if request.method == "GET":
            resp = casebooks.scan(
                FilterExpression="sk = :meta", ExpressionAttributeValues={":meta": "META"}
            )
            items = resp.get("Items", [])
            while resp.get("LastEvaluatedKey"):
                resp = casebooks.scan(
                    FilterExpression="sk = :meta",
                    ExpressionAttributeValues={":meta": "META"},
                    ExclusiveStartKey=resp["LastEvaluatedKey"],
                )
                items += resp.get("Items", [])
            items = sorted((_plain(i) for i in items), key=lambda i: i.get("created_at", ""), reverse=True)
            return jsonify(items)

        payload = request.get_json(silent=True) or {}
        fields, errors = _casebook_fields(payload)
        if errors:
            return jsonify({"error": "Check these fields.", "fields": errors}), 400
        case_id = uuid.uuid4().hex[:12]
        now = _now()
        item = {
            "pk": f"CASE#{case_id}",
            "sk": "META",
            "id": case_id,
            **fields,
            # Pasted posting text is only ever handed to a research run, never
            # stored: the casebook keeps a summary and the link instead.
            "posting_provided": bool(str(payload.get("posting_text") or "").strip()),
            "research_status": "not_started",
            "cost_usd": Decimal("0"),
            "researched_at": "",
            "created_at": now,
            "updated_at": now,
        }
        casebooks.put_item(Item=item, ConditionExpression="attribute_not_exists(pk)")
        return jsonify(_plain(item)), 201

    @bp.route("/api/owner/casebooks/<case_id>", methods=["GET", "PATCH", "DELETE"])
    def casebook_item(case_id):
        if not re.fullmatch(r"[0-9a-f]{12}", case_id):
            abort(404)
        meta = _meta(case_id)

        if request.method == "GET":
            rows = [_plain(r) for r in _rows(case_id)]
            grouped = {"sources": [], "questions": [], "evidence": []}
            for row in rows:
                kind = row["sk"].split("#", 1)[0]
                if kind == "SRC":
                    grouped["sources"].append(row)
                elif kind == "Q":
                    grouped["questions"].append(row)
                elif kind == "EV":
                    grouped["evidence"].append(row)
            return jsonify({"casebook": _plain(meta), **grouped})

        if request.method == "DELETE":
            with casebooks.batch_writer() as batch:
                for row in _rows(case_id):
                    batch.delete_item(Key={"pk": row["pk"], "sk": row["sk"]})
            return jsonify({"ok": True})

        payload = request.get_json(silent=True) or {}
        fields, errors = _casebook_fields(payload, partial=True)
        if errors:
            return jsonify({"error": "Check these fields.", "fields": errors}), 400
        if not fields:
            return jsonify(_plain(meta))
        fields["updated_at"] = _now()
        names = {f"#{k}": k for k in fields}
        values = {f":{k}": v for k, v in fields.items()}
        updated = casebooks.update_item(
            Key={"pk": meta["pk"], "sk": "META"},
            UpdateExpression="SET " + ", ".join(f"#{k} = :{k}" for k in fields),
            ExpressionAttributeNames=names,
            ExpressionAttributeValues=values,
            ReturnValues="ALL_NEW",
        )["Attributes"]
        return jsonify(_plain(updated))

    @bp.route("/api/owner/stories", methods=["GET", "POST"])
    def story_collection():
        if request.method == "GET":
            resp = stories.scan()
            items = resp.get("Items", [])
            while resp.get("LastEvaluatedKey"):
                resp = stories.scan(ExclusiveStartKey=resp["LastEvaluatedKey"])
                items += resp.get("Items", [])
            return jsonify(sorted((_plain(i) for i in items), key=lambda i: i.get("updated_at", ""), reverse=True))

        fields, errors = _story_fields(request.get_json(silent=True) or {})
        if errors:
            return jsonify({"error": "A story needs a title.", "fields": errors}), 400
        now = _now()
        item = {"id": uuid.uuid4().hex[:12], **fields, "created_at": now, "updated_at": now}
        stories.put_item(Item=item, ConditionExpression="attribute_not_exists(id)")
        return jsonify(item), 201

    @bp.route("/api/owner/stories/<story_id>", methods=["PUT", "DELETE"])
    def story_item(story_id):
        if not re.fullmatch(r"[0-9a-f]{12}", story_id):
            abort(404)
        existing = stories.get_item(Key={"id": story_id}).get("Item")
        if not existing:
            abort(404)
        if request.method == "DELETE":
            stories.delete_item(Key={"id": story_id})
            return jsonify({"ok": True})
        fields, errors = _story_fields(request.get_json(silent=True) or {})
        if errors:
            return jsonify({"error": "A story needs a title.", "fields": errors}), 400
        item = {**existing, **fields, "updated_at": _now()}
        stories.put_item(Item=item)
        return jsonify(_plain(item))

    app.register_blueprint(bp)
