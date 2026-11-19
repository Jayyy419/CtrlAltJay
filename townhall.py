"""Town hall: the owner-only area behind Commit City and Source Map.

Everything here sits behind the owner session. Signed-out requests get an
empty 404, the same as a route that doesn't exist. Nothing in this module is
read by public pages; they only read what Town hall publishes to the public
table.
"""
import json
import os
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import boto3
from boto3.dynamodb.conditions import Key

from flask import Blueprint, Response, abort, jsonify, render_template

UI_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "townhall_ui")
UI_FILES = {"app.js": "text/javascript; charset=utf-8", "app.css": "text/css; charset=utf-8"}
# A refresh that hasn't finished in this long has died; the collector's own
# limit is 15 minutes.
STALE_RUN = timedelta(minutes=20)

bp = Blueprint("townhall", __name__)


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


def register_townhall(app, is_owner, dynamodb):
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
        return jsonify({"repos": rows, "run": _run_state()})

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
