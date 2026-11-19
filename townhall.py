"""Town hall: the owner-only area behind Commit City and Source Map.

Everything here sits behind the owner session. Signed-out requests get an
empty 404, the same as a route that doesn't exist. Nothing in this module is
read by public pages; they only read what Town hall publishes to the public
table.
"""
import json
import os
import re
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import boto3
from boto3.dynamodb.conditions import Key

from flask import Blueprint, Response, abort, jsonify, render_template, request

from commit_city import language_color

UI_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "townhall_ui")
UI_FILES = {"app.js": "text/javascript; charset=utf-8", "app.css": "text/css; charset=utf-8"}
# A refresh that hasn't finished in this long has died; the collector's own
# limit is 15 minutes.
STALE_RUN = timedelta(minutes=20)

NAME_LIMIT = 60
DESCRIPTION_LIMIT = 280
# Private repos publish a size class, never a byte count.
SIZE_CLASSES = (50_000, 250_000, 1_000_000)

bp = Blueprint("townhall", __name__)


def _clean(value, limit):
    return re.sub(r"\s+", " ", str(value or "")).strip()[:limit]


def size_class(total_bytes):
    for i, limit in enumerate(SIZE_CLASSES):
        if total_bytes < limit:
            return i + 1
    return len(SIZE_CLASSES) + 1


def _to_ts(iso):
    try:
        return int(datetime.strptime(iso, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc).timestamp())
    except (TypeError, ValueError):
        return 0


def public_building(meta, stats, project_urls):
    """Exactly what one approved repo puts on the public site.

    Private repos get the owner's name and description, weekly commit
    counts, language shares, last push date and a size class. Nothing that
    names a file, branch, commit or the real repo is ever included.
    """
    stats = stats or {}
    languages = stats.get("languages") or {}
    total = sum(languages.values()) or 0
    shares = sorted(([k, round(v / total, 3)] for k, v in languages.items()), key=lambda x: -x[1]) if total else []
    main = shares[0][0] if shares else ""
    weeks = [[int(w), int(c)] for w, c in (stats.get("weeks") or [])]
    private = bool(meta.get("private"))
    building = {
        "slug": f"b{meta['github_id']}",
        "name": meta.get("public_name") or ("" if private else meta.get("full_name", "").split("/")[-1]),
        "description": meta.get("description") or ("" if private else meta.get("gh_description", "")),
        "languages": shares[:6],
        "main_language": main,
        "color": language_color(main),
        "weeks": weeks,
        "first_week": weeks[0][0] if weeks else 0,
        "commits": sum(c for _, c in weeks),
        "weeks_active": len(weeks),
        "last_push": _to_ts(meta.get("pushed_at")),
        "project_url": project_urls.get(meta.get("project_item_id") or "", ""),
        "tour_url": "",
    }
    if private:
        building["size_class"] = size_class(total)
        building["archived"] = False
    else:
        building["bytes"] = total
        building["archived"] = bool(meta.get("archived"))
        building["github_url"] = meta.get("html_url", "")
    return building


def _plain(value):
    if isinstance(value, Decimal):
        return int(value) if value == value.to_integral_value() else float(value)
    if isinstance(value, dict):
        return {k: _plain(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_plain(v) for v in value]
    return value


def _main_language(languages):
    if not languages:
        return ""
    return max(languages.items(), key=lambda kv: kv[1])[0]


def register_townhall(app, is_owner, dynamodb, static_version=lambda path: ""):
    town = dynamodb.Table(os.getenv("TOWN_TABLE", "ctrlaltjay-town"))
    collector_fn = os.getenv("TOWN_COLLECTOR_FUNCTION", "ctrlaltjay-town-collector")
    lambda_client = boto3.client("lambda")

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

    def _run_state():
        run = _plain(town.get_item(Key={"pk": "RUN", "sk": "LATEST"}).get("Item") or {})
        run.pop("pk", None)
        run.pop("sk", None)
        if run.get("status") == "running" and run.get("started_at"):
            began = datetime.strptime(run["started_at"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
            if datetime.now(timezone.utc) - began > STALE_RUN:
                run["status"] = "failed"
                run["error"] = "stopped without finishing"
        return run

    def _latest_stats(pk):
        items = town.query(KeyConditionExpression=Key("pk").eq(pk) & Key("sk").begins_with("STATS#"),
                           ScanIndexForward=False, Limit=1).get("Items", [])
        return _plain(items[0]) if items else None

    @bp.route("/owner/townhall", methods=["GET"])
    def townhall_page():
        return render_template("townhall.html")

    @bp.route("/owner/townhall/<name>", methods=["GET"])
    def townhall_asset(name):
        # Served from here rather than /static so nothing about Town hall is
        # public, not even its scripts.
        if name not in UI_FILES:
            abort(404)
        with open(os.path.join(UI_DIR, name), encoding="utf-8") as fh:
            return Response(fh.read(), mimetype=UI_FILES[name].split(";")[0], content_type=UI_FILES[name])

    @bp.route("/api/owner/townhall/repos", methods=["GET"])
    def townhall_repos():
        rows = []
        resp = town.scan(FilterExpression="sk = :m", ExpressionAttributeValues={":m": "META"})
        items = resp.get("Items", [])
        while resp.get("LastEvaluatedKey"):
            resp = town.scan(FilterExpression="sk = :m", ExpressionAttributeValues={":m": "META"},
                             ExclusiveStartKey=resp["LastEvaluatedKey"])
            items += resp.get("Items", [])
        for meta in (_plain(i) for i in items if i["pk"].startswith("REPO#")):
            stats = _latest_stats(meta["pk"])
            rows.append({
                "id": meta["github_id"],
                "full_name": meta.get("full_name", ""),
                "private": bool(meta.get("private")),
                "mode": meta.get("mode", "hidden"),
                "public_name": meta.get("public_name", ""),
                "description": meta.get("description", ""),
                "gh_description": meta.get("gh_description", ""),
                "visible_to_token": bool(meta.get("visible_to_token")),
                "project_item_id": meta.get("project_item_id", ""),
                "approved_at": meta.get("approved_at", ""),
                "archived": bool(meta.get("archived")),
                "pushed_at": meta.get("pushed_at", ""),
                "stats": None if not stats else {
                    "snapshot_date": stats.get("snapshot_date"),
                    "collected_at": stats.get("collected_at"),
                    "commits": stats.get("commits", 0),
                    "weeks_active": stats.get("weeks_active", 0),
                    "main_language": _main_language(stats.get("languages")),
                    "languages": stats.get("languages", {}),
                    "bytes": stats.get("bytes", 0),
                    "history_source": stats.get("history_source", ""),
                },
            })
        rows.sort(key=lambda r: r["pushed_at"], reverse=True)
        pub = _plain(public.get_item(Key={"pk": "CITY", "sk": "CURRENT"}).get("Item") or {})
        return jsonify({"repos": rows, "run": _run_state(),
                        "published": {"at": pub.get("published_at", ""), "count": pub.get("count", 0)}})

    public = dynamodb.Table(os.getenv("PUBLIC_CITY_TABLE", "ctrlaltjay-public-city"))
    items_table = dynamodb.Table("ctrlaltjay-portfolio-items")

    def _metas():
        resp = town.scan(FilterExpression="sk = :m", ExpressionAttributeValues={":m": "META"})
        items = resp.get("Items", [])
        while resp.get("LastEvaluatedKey"):
            resp = town.scan(FilterExpression="sk = :m", ExpressionAttributeValues={":m": "META"},
                             ExclusiveStartKey=resp["LastEvaluatedKey"])
            items += resp.get("Items", [])
        return [_plain(i) for i in items if i["pk"].startswith("REPO#")]

    def _project_urls():
        # Only published, live portfolio items can be linked from the city.
        resp = items_table.scan(ProjectionExpression="id, title, #s, is_draft, deleted_at", ExpressionAttributeNames={"#s": "section"})
        rows = resp.get("Items", [])
        while resp.get("LastEvaluatedKey"):
            resp = items_table.scan(ProjectionExpression="id, title, #s, is_draft, deleted_at", ExpressionAttributeNames={"#s": "section"},
                                    ExclusiveStartKey=resp["LastEvaluatedKey"])
            rows += resp.get("Items", [])
        live = [r for r in rows if not str(r.get("id", "")).startswith("__") and not r.get("is_draft") and not r.get("deleted_at")
                and r.get("section") in ("project", "experience")]
        return {r["id"]: f"/#item/{r['id']}" for r in live}, sorted(({"id": r["id"], "title": r.get("title", "")} for r in live), key=lambda r: r["title"].lower())

    def _meta(repo_id):
        if not re.fullmatch(r"\d{1,15}", str(repo_id)):
            abort(404)
        item = town.get_item(Key={"pk": f"REPO#{repo_id}", "sk": "META"}).get("Item")
        if not item:
            abort(404)
        return _plain(item)

    def _log(action, meta, detail=""):
        moment = datetime.now(timezone.utc)
        now = moment.strftime("%Y-%m-%dT%H:%M:%SZ")
        # Microseconds in the key keep actions in order even within a second.
        key = moment.strftime("%Y-%m-%dT%H:%M:%S.%fZ")
        town.put_item(Item={"pk": "APPROVAL", "sk": f"{key}#{uuid.uuid4().hex[:8]}", "at": now, "who": "owner",
                            "action": action, "repo_id": meta["github_id"] if meta else 0,
                            "repo": meta.get("full_name", "") if meta else "", "detail": detail[:200]})

    def _publish():
        urls, _ = _project_urls()
        buildings = []
        for meta in _metas():
            if meta.get("mode") != "approved":
                continue
            buildings.append(public_building(meta, _latest_stats(meta["pk"]), urls))
        buildings.sort(key=lambda b: -b["commits"])
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        snapshot = {"sample": False, "as_of": now, "buildings": buildings}
        public.put_item(Item={"pk": "CITY", "sk": "CURRENT", "data": json.dumps(snapshot), "published_at": now, "count": len(buildings)})
        return snapshot

    def _validate(meta):
        problems = []
        if meta.get("private") and not meta.get("public_name"):
            problems.append("A private repo needs a public name you choose.")
        if meta.get("private") and not meta.get("description"):
            problems.append("A private repo needs a description you write.")
        if not meta.get("visible_to_token"):
            problems.append("The GitHub token can't see this repo any more.")
        return problems

    @bp.route("/api/owner/townhall/repos/<repo_id>", methods=["PATCH"])
    def townhall_repo_update(repo_id):
        meta = _meta(repo_id)
        payload = request.get_json(silent=True) or {}
        fields = {}
        if "public_name" in payload:
            fields["public_name"] = _clean(payload.get("public_name"), NAME_LIMIT)
        if "description" in payload:
            fields["description"] = _clean(payload.get("description"), DESCRIPTION_LIMIT)
        if "project_item_id" in payload:
            pid = str(payload.get("project_item_id") or "")
            urls, _ = _project_urls()
            if pid and pid not in urls:
                return jsonify({"error": "That project page isn't live."}), 400
            fields["project_item_id"] = pid
        if fields:
            town.update_item(
                Key={"pk": meta["pk"], "sk": "META"},
                UpdateExpression="SET " + ", ".join(f"#{k} = :{k}" for k in fields),
                ExpressionAttributeNames={f"#{k}": k for k in fields},
                ExpressionAttributeValues={f":{k}": v for k, v in fields.items()},
            )
            meta.update(fields)
        # Changing the words on an approved building republishes, so the public
        # site never shows a name the owner has since changed.
        if meta.get("mode") == "approved" and fields:
            _publish()
            _log("update", meta, ", ".join(sorted(fields)))
        return jsonify({"ok": True})

    @bp.route("/api/owner/townhall/repos/<repo_id>/preview", methods=["GET"])
    def townhall_repo_preview(repo_id):
        meta = _meta(repo_id)
        urls, projects = _project_urls()
        return jsonify({"building": public_building(meta, _latest_stats(meta["pk"]), urls),
                        "problems": _validate(meta), "projects": projects})

    @bp.route("/api/owner/townhall/repos/<repo_id>/preview-city", methods=["GET"])
    def townhall_repo_preview_city(repo_id):
        meta = _meta(repo_id)
        urls, _ = _project_urls()
        return jsonify({"sample": False, "preview": True, "as_of": "",
                        "buildings": [public_building(meta, _latest_stats(meta["pk"]), urls)]})

    @bp.route("/owner/townhall/preview/<repo_id>", methods=["GET"])
    def townhall_preview_page(repo_id):
        _meta(repo_id)
        return render_template("city.html", css_v=static_version("css/city.css"), js_v=static_version("js/city.js"),
                               data_src=f"/api/owner/townhall/repos/{repo_id}/preview-city", preview=True)

    @bp.route("/api/owner/townhall/repos/<repo_id>/approve", methods=["POST"])
    def townhall_approve(repo_id):
        meta = _meta(repo_id)
        problems = _validate(meta)
        if problems:
            return jsonify({"error": " ".join(problems)}), 400
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        town.update_item(Key={"pk": meta["pk"], "sk": "META"}, UpdateExpression="SET #m = :a, approved_at = :t",
                         ExpressionAttributeNames={"#m": "mode"}, ExpressionAttributeValues={":a": "approved", ":t": now})
        meta["mode"] = "approved"
        _publish()
        _log("approve", meta, meta.get("public_name") or meta.get("full_name", ""))
        return jsonify({"ok": True})

    @bp.route("/api/owner/townhall/repos/<repo_id>/drawer", methods=["POST"])
    def townhall_drawer(repo_id):
        meta = _meta(repo_id)
        town.update_item(Key={"pk": meta["pk"], "sk": "META"}, UpdateExpression="SET #m = :h REMOVE approved_at",
                         ExpressionAttributeNames={"#m": "mode"}, ExpressionAttributeValues={":h": "hidden"})
        _publish()
        _log("drawer", meta)
        return jsonify({"ok": True})

    @bp.route("/api/owner/townhall/publish", methods=["POST"])
    def townhall_publish():
        snapshot = _publish()
        _log("publish", None, f"{len(snapshot['buildings'])} buildings")
        return jsonify({"ok": True, "buildings": len(snapshot["buildings"])})

    @bp.route("/api/owner/townhall/approvals", methods=["GET"])
    def townhall_approvals():
        rows = town.query(KeyConditionExpression=Key("pk").eq("APPROVAL"), ScanIndexForward=False, Limit=100).get("Items", [])
        return jsonify([{k: v for k, v in _plain(r).items() if k not in ("pk", "sk")} for r in rows])

    @bp.route("/api/owner/townhall/refresh", methods=["POST"])
    def townhall_refresh():
        if _run_state().get("status") == "running":
            return jsonify({"error": "A refresh is already running."}), 409
        # Marked as running before the collector starts, so a second press
        # can't start a second run.
        town.put_item(Item={"pk": "RUN", "sk": "LATEST", "status": "running", "trigger": "manual",
                            "started_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")})
        lambda_client.invoke(FunctionName=collector_fn, InvocationType="Event",
                             Payload=json.dumps({"action": "refresh", "trigger": "manual"}).encode())
        return jsonify({"ok": True}), 202

    app.register_blueprint(bp)
