"""Town hall tours: plotting Source Map stops and publishing the map.

Every route here hangs off the Town hall blueprint, so it inherits its
owner-only guard and no-store headers. Code is only ever read through the
collector, which holds the GitHub token; the app never sees it. An excerpt is
copied at a fixed commit when it's plotted, checked for secrets, and only
reaches the public table when the owner presses "Publish the map".
"""
import json
import re
import urllib.parse
import uuid
from datetime import datetime, timezone

from flask import abort, jsonify, render_template, request

import townhall_draft
from secret_scan import scan_lines
from source_map import SLUG_RE

MAX_STOPS = 20
MAX_EXCERPT_LINES = 40
MAX_LINE_CHARS = 400
TITLE_LIMIT = 80
EXPLANATION_LIMIT = 600
TOUR_TITLE_LIMIT = 100
LABEL_LIMIT = 30
# The map stays readable with this many districts; the rest are left off
# unless a stop is in one.
MAP_DISTRICTS = 8
ROOT = "."

LANGS = {
    "py": "python", "js": "javascript", "mjs": "javascript", "cjs": "javascript", "jsx": "javascript",
    "ts": "typescript", "tsx": "typescript", "sh": "shell", "bash": "shell", "go": "go", "rb": "ruby",
    "java": "java", "kt": "kotlin", "swift": "swift", "rs": "rust", "c": "c", "h": "c", "cpp": "cpp",
    "cs": "csharp", "php": "php", "html": "html", "css": "css", "scss": "css", "sql": "sql",
    "yml": "yaml", "yaml": "yaml", "json": "json", "md": "markdown", "toml": "toml", "dart": "dart",
}


def _now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _clean(value, limit):
    return re.sub(r"\s+", " ", str(value or "")).strip()[:limit]


def _clean_text(value, limit):
    # Explanations keep paragraph breaks but nothing else fancy.
    text = re.sub(r"[ \t]+", " ", str(value or "")).strip()
    return re.sub(r"\n{3,}", "\n\n", text)[:limit]


def slugify(text):
    slug = re.sub(r"[^a-z0-9]+", "-", str(text or "").lower()).strip("-")[:60].strip("-")
    return slug or "tour"


def district_of(path):
    return path.split("/", 1)[0] if "/" in path else ROOT


def lang_of(path):
    name = path.rsplit("/", 1)[-1].lower()
    if name == "dockerfile":
        return "dockerfile"
    return LANGS.get(name.rsplit(".", 1)[-1], "") if "." in name else ""


def _letter(i):
    out = ""
    i += 1
    while i:
        i, r = divmod(i - 1, 26)
        out = chr(65 + r) + out
    return out


def districts_from_files(files, previous):
    """Top-level folders with their total size, keeping labels already set."""
    labels = {d["name"]: d.get("label", "") for d in previous or []}
    sizes = {}
    for path, size in files:
        key = district_of(path)
        sizes[key] = sizes.get(key, 0) + int(size or 0)
    ordered = sorted(sizes.items(), key=lambda kv: -kv[1])
    return [{"name": name, "size": size, "label": labels.get(name, "")} for name, size in ordered]


def shown_districts(draft):
    districts = draft.get("districts") or []
    used = {s["district"] for s in draft.get("stops") or []}
    keep = [d for i, d in enumerate(districts) if i < MAP_DISTRICTS or d["name"] in used]
    known = {d["name"] for d in keep}
    keep += [{"name": n, "size": 0, "label": ""} for n in sorted(used - known)]
    return keep


def district_label(district, index, private):
    if district.get("label"):
        return district["label"]
    if private:
        return f"Area {_letter(index)}"
    return "top level" if district["name"] == ROOT else district["name"]


def public_tour(meta, draft, project_url, building_name):
    """Exactly what one tour puts on the public site.

    For a private repo, districts carry the owner's labels and stops carry no
    path, file name, commit or link: only the title, explanation and the
    excerpt the owner approved.
    """
    private = bool(meta.get("private"))
    districts = shown_districts(draft)
    total = sum(max(0, d["size"]) for d in districts) or 1
    labels = {d["name"]: district_label(d, i, private) for i, d in enumerate(districts)}
    stops = []
    for s in draft.get("stops") or []:
        stop = {
            "title": s["title"], "district": labels.get(s["district"], ""), "lang": s.get("lang", ""),
            "explanation": s["explanation"],
            "excerpt": {"start": s["start"], "mark": list(s["mark"]), "lines": list(s["lines"])},
            "permalink": "",
        }
        if not private and meta.get("html_url"):
            stop["permalink"] = f"{meta['html_url']}/blob/{s['sha']}/{urllib.parse.quote(s['path'])}#L{s['start']}-L{s['end']}"
        stops.append(stop)
    return {
        "sample": False,
        "slug": draft.get("slug", ""),
        "title": draft.get("title") or f"A tour of {building_name}",
        "repo_name": building_name,
        "private": private,
        "project_url": project_url,
        "building_slug": f"b{meta['github_id']}",
        "districts": [{"name": labels[d["name"]], "size": max(1, round(100 * d["size"] / total))} for d in districts],
        "stops": stops,
    }


def tour_problems(meta, draft, slug_taken):
    problems = []
    if meta.get("mode") != "approved":
        problems.append("Approve the repo for the skyline first.")
    if not meta.get("visible_to_token"):
        problems.append("The GitHub token can't see this repo any more.")
    slug = draft.get("slug", "")
    if not SLUG_RE.match(slug) or slug == "sample":
        problems.append("The map needs an address made of lowercase letters, numbers and dashes.")
    elif slug_taken:
        problems.append("Another tour already uses that address.")
    stops = draft.get("stops") or []
    if not stops:
        problems.append("Plot at least one stop.")
    for n, s in enumerate(stops, 1):
        if not s.get("title") or not s.get("explanation"):
            problems.append(f"Stop {n} needs a title and an explanation.")
        if len(s.get("lines") or []) > MAX_EXCERPT_LINES:
            problems.append(f"Stop {n} is longer than {MAX_EXCERPT_LINES} lines.")
        # Checked again here, so an excerpt can't slip through on an old result.
        findings = scan_lines(s.get("lines") or [], s.get("start", 1))
        if findings and (s.get("scan") or {}).get("status") != "false_positive":
            f = findings[0]
            problems.append(f"Stop {n}: line {f['line']} looks like {f['kind'].lower()}. Change the lines or mark it as not a secret.")
    return problems


def register_tours(app, bp, town, public, metas, meta_of, building_name, project_urls, publish_city, log, static_version, invoke_collector):

    def collector(payload):
        call = app.config.get("TOWN_COLLECTOR_CALL") or invoke_collector
        result = call(payload) or {}
        if result.get("error"):
            abort(_error(result["error"], 502))
        return result

    def _error(message, status=400):
        resp = jsonify({"error": message})
        resp.status_code = status
        return resp

    def load_draft(repo_id):
        item = town.get_item(Key={"pk": f"TOUR#{repo_id}", "sk": "DRAFT"}).get("Item") or {}
        return {
            "repo_id": int(repo_id), "title": item.get("title", ""), "slug": item.get("slug", ""),
            "sha": item.get("sha", ""), "branch": item.get("branch", ""),
            "districts": json.loads(item.get("districts") or "[]"), "stops": json.loads(item.get("stops") or "[]"),
            "published_slug": item.get("published_slug", ""), "published_at": item.get("published_at", ""),
            "updated_at": item.get("updated_at", ""),
        }

    def save_draft(draft):
        town.put_item(Item={
            "pk": f"TOUR#{draft['repo_id']}", "sk": "DRAFT", "repo_id": int(draft["repo_id"]),
            "title": draft.get("title", ""), "slug": draft.get("slug", ""), "sha": draft.get("sha", ""),
            "branch": draft.get("branch", ""), "districts": json.dumps(draft.get("districts") or []),
            "stops": json.dumps(draft.get("stops") or []), "published_slug": draft.get("published_slug", ""),
            "published_at": draft.get("published_at", ""), "updated_at": _now(),
        })

    def all_drafts():
        resp = town.scan(FilterExpression="sk = :d AND begins_with(pk, :t)", ExpressionAttributeValues={":d": "DRAFT", ":t": "TOUR#"})
        items = resp.get("Items", [])
        while resp.get("LastEvaluatedKey"):
            resp = town.scan(FilterExpression="sk = :d AND begins_with(pk, :t)", ExpressionAttributeValues={":d": "DRAFT", ":t": "TOUR#"},
                             ExclusiveStartKey=resp["LastEvaluatedKey"])
            items += resp.get("Items", [])
        return items

    def slug_taken(repo_id, slug):
        return any(int(i.get("repo_id", 0)) != int(repo_id) and slug in (i.get("published_slug"), i.get("slug")) for i in all_drafts())

    def find_stop(draft, stop_id):
        for i, s in enumerate(draft["stops"]):
            if s["id"] == stop_id:
                return i, s
        abort(404)

    def stop_view(s):
        return {k: s.get(k) for k in ("id", "title", "explanation", "path", "start", "end", "mark", "lines", "sha", "lang", "district", "scan", "needs_look", "plotted_at")}

    def draft_view(meta, draft):
        name = building_name(meta)
        if not draft["slug"]:
            draft["slug"] = slugify(name)
        private = bool(meta.get("private"))
        districts = shown_districts(draft)
        return {
            "repo": {"id": meta["github_id"], "name": name, "full_name": meta.get("full_name", ""), "private": private,
                     "mode": meta.get("mode", "hidden"), "html_url": meta.get("html_url", "") if not private else ""},
            "title": draft["title"], "slug": draft["slug"], "sha": draft["sha"], "branch": draft["branch"],
            "districts": [dict(d, shown_label=district_label(d, i, private)) for i, d in enumerate(districts)],
            "stops": [stop_view(s) for s in draft["stops"]],
            "published_slug": draft["published_slug"], "published_at": draft["published_at"],
            "problems": tour_problems(meta, draft, slug_taken(meta["github_id"], draft["slug"])),
            "draft_help": dict(townhall_draft.spend(town), enabled=bool(app.config.get("TOWN_DRAFT_API_KEY")) and townhall_draft.MAX_USD_PER_MONTH > 0),
        }

    def tour_for_public(meta, draft):
        urls, _ = project_urls()
        return public_tour(meta, draft, urls.get(meta.get("project_item_id") or "", ""), building_name(meta))

    def take_down(meta, draft):
        if draft.get("published_slug"):
            public.delete_item(Key={"pk": f"TOUR#{draft['published_slug']}", "sk": "CURRENT"})
        draft["published_slug"] = ""
        draft["published_at"] = ""

    def take_down_saved(meta):
        draft = load_draft(meta["github_id"])
        if draft["published_slug"]:
            take_down(meta, draft)
            save_draft(draft)
            return True
        return False

    @bp.route("/api/owner/townhall/tours", methods=["GET"])
    def tours_list():
        drafts = {int(i["repo_id"]): i for i in all_drafts()}
        rows = []
        for meta in metas():
            item = drafts.get(int(meta["github_id"]))
            if meta.get("mode") != "approved" and not item:
                continue
            stops = json.loads(item.get("stops") or "[]") if item else []
            rows.append({
                "id": meta["github_id"], "name": building_name(meta), "full_name": meta.get("full_name", ""),
                "private": bool(meta.get("private")), "mode": meta.get("mode", "hidden"), "stops": len(stops),
                "needs_look": sum(1 for s in stops if s.get("needs_look")),
                "flagged": sum(1 for s in stops if (s.get("scan") or {}).get("status") == "flagged"),
                "published_slug": item.get("published_slug", "") if item else "",
                "published_at": item.get("published_at", "") if item else "",
            })
        rows.sort(key=lambda r: (not r["published_slug"], -r["stops"], r["name"].lower()))
        return jsonify({"tours": rows})

    @bp.route("/api/owner/townhall/tours/<repo_id>", methods=["GET"])
    def tour_get(repo_id):
        meta = meta_of(repo_id)
        return jsonify(draft_view(meta, load_draft(repo_id)))

    @bp.route("/api/owner/townhall/tours/<repo_id>", methods=["PATCH"])
    def tour_update(repo_id):
        meta = meta_of(repo_id)
        draft = load_draft(repo_id)
        payload = request.get_json(silent=True) or {}
        if "title" in payload:
            draft["title"] = _clean(payload.get("title"), TOUR_TITLE_LIMIT)
        if "slug" in payload:
            slug = str(payload.get("slug") or "").strip().lower()
            if not SLUG_RE.match(slug) or slug == "sample":
                return _error("Use lowercase letters, numbers and dashes for the address.")
            if slug_taken(repo_id, slug):
                return _error("Another tour already uses that address.")
            draft["slug"] = slug
        if isinstance(payload.get("labels"), dict):
            for d in draft["districts"]:
                if d["name"] in payload["labels"]:
                    d["label"] = _clean(payload["labels"][d["name"]], LABEL_LIMIT)
        if isinstance(payload.get("order"), list):
            ids = [str(x) for x in payload["order"]]
            if sorted(ids) != sorted(s["id"] for s in draft["stops"]):
                return _error("The route changed in another window. Reload and try again.", 409)
            by_id = {s["id"]: s for s in draft["stops"]}
            draft["stops"] = [by_id[i] for i in ids]
        if isinstance(payload.get("stop"), dict):
            _, s = find_stop(draft, str(payload["stop"].get("id")))
            edit = payload["stop"]
            if "title" in edit:
                s["title"] = _clean(edit.get("title"), TITLE_LIMIT)
            if "explanation" in edit:
                s["explanation"] = _clean_text(edit.get("explanation"), EXPLANATION_LIMIT)
            if "mark" in edit:
                mark = _mark(edit.get("mark"), s["start"], s["end"])
                if not mark:
                    return _error(f"Highlight lines between {s['start']} and {s['end']}.")
                s["mark"] = mark
        save_draft(draft)
        return jsonify(draft_view(meta, draft))

    def _mark(value, start, end):
        try:
            a, b = int(value[0]), int(value[1])
        except (TypeError, ValueError, IndexError):
            return None
        if a > b:
            a, b = b, a
        return [a, b] if start <= a and b <= end else None

    @bp.route("/api/owner/townhall/tours/<repo_id>/tree", methods=["POST"])
    def tour_tree(repo_id):
        meta = meta_of(repo_id)
        draft = load_draft(repo_id)
        result = collector({"action": "tree", "repo_id": int(repo_id)})
        draft["sha"], draft["branch"] = result["sha"], result.get("branch", "")
        draft["districts"] = districts_from_files(result["files"], draft["districts"])
        save_draft(draft)
        view = draft_view(meta, draft)
        view["files"] = result["files"]
        view["truncated"] = bool(result.get("truncated"))
        return jsonify(view)

    @bp.route("/api/owner/townhall/tours/<repo_id>/file", methods=["POST"])
    def tour_file(repo_id):
        meta_of(repo_id)
        draft = load_draft(repo_id)
        path = str((request.get_json(silent=True) or {}).get("path") or "")
        if not draft["sha"]:
            return _error("Open the file list first.")
        result = collector({"action": "file", "repo_id": int(repo_id), "sha": draft["sha"], "path": path})
        return jsonify({"path": path, "sha": draft["sha"], "lang": lang_of(path), "lines": result["lines"]})

    @bp.route("/api/owner/townhall/tours/<repo_id>/stops", methods=["POST"])
    def tour_plot(repo_id):
        meta = meta_of(repo_id)
        draft = load_draft(repo_id)
        payload = request.get_json(silent=True) or {}
        path = str(payload.get("path") or "")
        replace = str(payload.get("replace") or "")
        if not replace and len(draft["stops"]) >= MAX_STOPS:
            return _error(f"A tour can have up to {MAX_STOPS} stops.")
        try:
            start, end = int(payload.get("start")), int(payload.get("end"))
        except (TypeError, ValueError):
            return _error("Choose the lines for this stop.")
        if start > end:
            start, end = end, start
        if start < 1 or end - start + 1 > MAX_EXCERPT_LINES:
            return _error(f"A stop can show up to {MAX_EXCERPT_LINES} lines.")
        if not draft["sha"]:
            return _error("Open the file list first.")
        # The excerpt is copied on the server at the commit the file list came
        # from; nothing the browser sends ends up in it.
        lines = collector({"action": "file", "repo_id": int(repo_id), "sha": draft["sha"], "path": path})["lines"]
        if end > len(lines):
            return _error(f"That file has {len(lines)} lines.")
        excerpt = lines[start - 1:end]
        if any(len(line) > MAX_LINE_CHARS for line in excerpt):
            return _error("A line in that range is too long to show. Pick other lines.")
        mark = _mark(payload.get("mark") or [start, end], start, end) or [start, end]
        findings = scan_lines(excerpt, start)
        stop = {
            "id": uuid.uuid4().hex[:10], "title": _clean(payload.get("title"), TITLE_LIMIT),
            "explanation": _clean_text(payload.get("explanation"), EXPLANATION_LIMIT),
            "path": path, "start": start, "end": end, "mark": mark, "lines": excerpt, "sha": draft["sha"],
            "lang": lang_of(path), "district": district_of(path),
            "scan": {"status": "flagged" if findings else "clear", "findings": findings, "checked_at": _now()},
            "needs_look": None, "plotted_at": _now(),
        }
        if replace:
            i, old = find_stop(draft, replace)
            stop["id"] = old["id"]
            stop["title"] = stop["title"] or old["title"]
            stop["explanation"] = stop["explanation"] or old["explanation"]
            draft["stops"][i] = stop
        else:
            at = payload.get("at")
            at = int(at) if isinstance(at, int) and 0 <= at <= len(draft["stops"]) else len(draft["stops"])
            draft["stops"].insert(at, stop)
        save_draft(draft)
        view = draft_view(meta, draft)
        view["plotted"] = stop["id"]
        return jsonify(view), 201

    @bp.route("/api/owner/townhall/tours/<repo_id>/stops/<stop_id>", methods=["DELETE"])
    def tour_unplot(repo_id, stop_id):
        meta = meta_of(repo_id)
        draft = load_draft(repo_id)
        i, _ = find_stop(draft, stop_id)
        draft["stops"].pop(i)
        save_draft(draft)
        return jsonify(draft_view(meta, draft))

    @bp.route("/api/owner/townhall/tours/<repo_id>/stops/<stop_id>/not-a-secret", methods=["POST"])
    def tour_false_positive(repo_id, stop_id):
        meta = meta_of(repo_id)
        draft = load_draft(repo_id)
        n, s = find_stop(draft, stop_id)
        findings = scan_lines(s["lines"], s["start"])
        s["scan"] = {"status": "false_positive" if findings else "clear", "findings": findings, "checked_at": _now()}
        save_draft(draft)
        if findings:
            kinds = sorted({f["kind"].lower() for f in findings})
            log("not_a_secret", meta, f"stop {n + 1}, {', '.join(kinds)}")
        return jsonify(draft_view(meta, draft))

    @bp.route("/api/owner/townhall/tours/<repo_id>/stops/<stop_id>/keep", methods=["POST"])
    def tour_keep(repo_id, stop_id):
        meta = meta_of(repo_id)
        draft = load_draft(repo_id)
        n, s = find_stop(draft, stop_id)
        look = s.get("needs_look") or {}
        s["accepted_window"] = look.get("window")
        s["needs_look"] = None
        save_draft(draft)
        log("keep_stop", meta, f"stop {n + 1}")
        return jsonify(draft_view(meta, draft))

    @bp.route("/api/owner/townhall/tours/<repo_id>/stops/<stop_id>/draft", methods=["POST"])
    def tour_draft(repo_id, stop_id):
        meta = meta_of(repo_id)
        draft = load_draft(repo_id)
        n, s = find_stop(draft, stop_id)
        try:
            result = townhall_draft.draft_stop(
                town, app.config.get("TOWN_DRAFT_API_KEY", ""), building_name(meta) or "A project", meta.get("description") or meta.get("gh_description") or "",
                s, n + 1, [x.get("title", "") for x in draft["stops"]], client_factory=app.config.get("TOWN_DRAFT_CLIENT"))
        except townhall_draft.DraftError as err:
            return jsonify({"error": str(err), "budget": townhall_draft.spend(town)}), 400
        result["budget"] = townhall_draft.spend(town)
        return jsonify(result)

    @bp.route("/api/owner/townhall/tours/<repo_id>/preview-tour", methods=["GET"])
    def tour_preview_data(repo_id):
        meta = meta_of(repo_id)
        draft = load_draft(repo_id)
        if not draft["slug"]:
            draft["slug"] = slugify(building_name(meta))
        tour = tour_for_public(meta, draft)
        tour["preview"] = True
        return jsonify(tour)

    @bp.route("/owner/townhall/tour-preview/<repo_id>", methods=["GET"])
    @bp.route("/owner/townhall/tour-preview/<repo_id>/<int:stop>", methods=["GET"])
    def tour_preview_page(repo_id, stop=1):
        meta = meta_of(repo_id)
        draft = load_draft(repo_id)
        if not draft["stops"]:
            abort(404)
        tour = tour_for_public(meta, draft)
        stop = min(max(1, stop), len(tour["stops"]))
        return render_template("map.html", tour=tour, stop=stop, preview=True,
                               data_src=f"/api/owner/townhall/tours/{repo_id}/preview-tour",
                               base=f"/owner/townhall/tour-preview/{repo_id}",
                               css_v=static_version("css/map.css"), js_v=static_version("js/map.js"))

    @bp.route("/api/owner/townhall/tours/<repo_id>/publish", methods=["POST"])
    def tour_publish(repo_id):
        meta = meta_of(repo_id)
        draft = load_draft(repo_id)
        if not draft["slug"]:
            draft["slug"] = slugify(building_name(meta))
        problems = tour_problems(meta, draft, slug_taken(repo_id, draft["slug"]))
        if problems:
            return _error(" ".join(problems))
        tour = tour_for_public(meta, draft)
        now = _now()
        tour["published_at"] = now
        if draft["published_slug"] and draft["published_slug"] != draft["slug"]:
            public.delete_item(Key={"pk": f"TOUR#{draft['published_slug']}", "sk": "CURRENT"})
        public.put_item(Item={"pk": f"TOUR#{draft['slug']}", "sk": "CURRENT", "data": json.dumps(tour), "published_at": now})
        draft["published_slug"], draft["published_at"] = draft["slug"], now
        save_draft(draft)
        publish_city()
        log("publish_map", meta, f"/map/{draft['slug']}, {len(tour['stops'])} stops")
        return jsonify(draft_view(meta, draft))

    @bp.route("/api/owner/townhall/tours/<repo_id>/unpublish", methods=["POST"])
    def tour_unpublish(repo_id):
        meta = meta_of(repo_id)
        draft = load_draft(repo_id)
        was = draft["published_slug"]
        take_down(meta, draft)
        save_draft(draft)
        publish_city()
        if was:
            log("unpublish_map", meta, f"/map/{was}")
        return jsonify(draft_view(meta, draft))

    def published_slugs():
        return {int(i["repo_id"]): i["published_slug"] for i in all_drafts() if i.get("published_slug")}

    return {"take_down": take_down_saved, "published_slugs": published_slugs}
