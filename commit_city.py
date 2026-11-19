"""Commit City, the public page.

It reads only the published snapshot in ctrlaltjay-public-city, which Town
hall writes when the owner approves. It never reads the owner-side table and
never calls GitHub. Until anything is published it shows a sample city,
clearly marked as one.
"""
import json
import os
import time
from datetime import datetime, timezone

from flask import Blueprint, jsonify, render_template

bp = Blueprint("commit_city", __name__)
WEEK = 7 * 24 * 3600

# GitHub's own language colours for the languages likely to appear; anything
# else gets a steady colour picked from its name.
LANG_COLORS = {
    "Python": "#3572A5", "TypeScript": "#3178c6", "JavaScript": "#f1e05a", "HTML": "#e34c26", "CSS": "#663399",
    "Go": "#00ADD8", "Java": "#b07219", "Kotlin": "#A97BFF", "Swift": "#F05138", "Rust": "#dea584", "C": "#555555",
    "C++": "#f34b7d", "C#": "#178600", "Ruby": "#701516", "PHP": "#4F5D95", "Shell": "#89e051", "Dockerfile": "#384d54",
    "Jupyter Notebook": "#DA5B0B", "Dart": "#00B4AB", "Vue": "#41b883", "SCSS": "#c6538c", "Svelte": "#ff3e00",
}
FALLBACK_COLORS = ["#7fb6ff", "#4ec9b0", "#dcdcaa", "#c586c0", "#ce9178", "#9cdcfe"]


def language_color(name):
    if name in LANG_COLORS:
        return LANG_COLORS[name]
    return FALLBACK_COLORS[sum(ord(c) for c in name or "x") % len(FALLBACK_COLORS)]


def _sample_weeks(seed, start_ts, count, density):
    weeks, x = [], seed
    for i in range(count):
        x = (x * 9301 + 49297) % 233280
        r = x / 233280
        if r < density:
            weeks.append([start_ts + i * WEEK, max(1, round(r * 14 / density))])
    return weeks


def sample_city():
    """Invented projects, so the page works before anything is approved."""
    now = int(time.time())
    this_week = now - (now % WEEK)
    specs = [
        ("Lighthouse API", "A small API that keeps a fleet of bots in touch.", [("Python", 0.72), ("Shell", 0.18), ("Dockerfile", 0.10)], 420000, 140, 0.8, False, 2),
        ("Garden Planner", "Plans what to plant where, by season.", [("TypeScript", 0.81), ("CSS", 0.19)], 610000, 95, 0.55, False, 40),
        ("Pocket Ledger", "A budget app that fits in a terminal.", [("Go", 1.0)], 150000, 60, 0.35, False, 90),
        ("Tram Times", "Live arrival boards for a city that has trams.", [("JavaScript", 0.64), ("HTML", 0.36)], 90000, 40, 0.7, False, 3),
        ("Archive 2019", "A university project, kept for the record.", [("Java", 1.0)], 300000, 30, 0.2, True, 300),
        ("Studio Site", "A portfolio site for a design studio.", [("CSS", 0.55), ("HTML", 0.45)], 220000, 25, 0.9, False, 20),
    ]
    buildings = []
    for i, (name, desc, langs, size, span, density, archived, days_since_push) in enumerate(specs):
        start = this_week - span * WEEK - (i * 3) * WEEK
        weeks = _sample_weeks(7 + i * 4, start, span, density)
        buildings.append({
            "name": name, "description": desc,
            "languages": [[l, s] for l, s in langs], "main_language": langs[0][0], "color": language_color(langs[0][0]),
            "bytes": size, "weeks": weeks, "first_week": weeks[0][0] if weeks else start,
            "commits": sum(c for _, c in weeks), "weeks_active": len(weeks),
            "last_push": now - days_since_push * 86400, "archived": archived,
            "project_url": "", "tour_url": "",
        })
    return {"sample": True, "as_of": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "buildings": buildings}


def register_commit_city(app, dynamodb, static_version):
    public = dynamodb.Table(os.getenv("PUBLIC_CITY_TABLE", "ctrlaltjay-public-city"))

    def published():
        item = public.get_item(Key={"pk": "CITY", "sk": "CURRENT"}).get("Item")
        if not item or not item.get("data"):
            return None
        return json.loads(item["data"])

    @bp.route("/city", methods=["GET"])
    def city_page():
        return render_template("city.html", css_v=static_version("css/city.css"), js_v=static_version("js/city.js"))

    @bp.route("/api/city", methods=["GET"])
    def city_data():
        city = published() or sample_city()
        resp = jsonify(city)
        resp.headers["Cache-Control"] = "public, max-age=300"
        return resp

    app.register_blueprint(bp)
