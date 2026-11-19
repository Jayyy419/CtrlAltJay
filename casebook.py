"""Casebook: the owner-only interview and application prep area.

Everything here sits behind the owner session. Signed-out requests get an
empty 404, so the routes look the same as ones that don't exist.
"""
import hashlib
import json
import os
import re
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import boto3
from flask import Blueprint, Response, abort, jsonify, render_template, request

import casebook_drill
import casebook_evidence as ce

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
TEXT_LIMITS = {"organisation": 120, "role": 160, "notes": 4000, "posting_url": 500, "title": 160, "opener": 400}
THEIRS_LIMIT = 300
DRILL_RATINGS = ("missed", "shaky", "got")
DRILL_TOP_BOX = 3
MAX_THEIRS = 12
STORY_FIELD_LIMIT = 2000
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
ID_RE = re.compile(r"^[0-9a-f]{12}$")
REF_RE = re.compile(r"^(item|resume|story):[0-9A-Za-z-]{1,64}$")
MAX_COMPETENCIES = 12
MAX_QUESTIONS = 40
MAX_USD_PER_CASE = float(os.getenv("CASEBOOK_MAX_USD_PER_CASE", "3"))
MAX_USD_PER_MONTH = float(os.getenv("CASEBOOK_MAX_USD_PER_MONTH", "10"))
# Below this a run can't do enough searching to be worth starting.
MIN_RUN_USD = 0.5
# A run that hasn't finished in this long has died; the worker's own limit
# is 15 minutes.
STALE_RUN = timedelta(minutes=20)
POSTING_TEXT_LIMIT = 20000
UI_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "casebook_ui")
UI_FILES = {"app.js": "text/javascript; charset=utf-8", "app.css": "text/css; charset=utf-8"}

# Shown so the screens can be tried before research exists. Everything about
# the organisation is invented; the evidence uses real portfolio titles.
SAMPLE_CASEBOOK = {
    "casebook": {
        "id": "sample", "sample": True, "occasion": "interview", "organisation": "Accenture",
        "role": "Technology Analyst Intern", "date": "2026-12-03", "format": "video",
        "posting_url": "", "notes": "They said there'll be a case study.", "research_status": "done",
        "opener": "I like building things people use, and client work puts those people right in front of you.",
        "cost_usd": 0.42, "searches": 9, "researched_at": "2026-11-19T09:03:00Z",
    },
    "competencies": ["Process change", "Client-facing", "Cloud", "Teamwork", "Stakeholders", "Ownership"],
    "questions": [
        {"kind": "motivation", "text": "Why Accenture, and why technology consulting?", "provenance": "reported",
         "sources": [{"title": "Sample source (not real research)", "url": "", "date": "2026-10-12"}],
         "why": "They want to see you've thought about client work, not just the tech.",
         "evidence": [{"title": "Seads Singapore Website", "role": "lead"}, {"title": "Hall 7 Website", "role": "backup"}],
         "star": None},
        {"kind": "behavioural", "text": "Tell us about a time you changed how a team worked.", "provenance": "posting",
         "requirement": "improve client processes",
         "why": "The role is about changing how clients work, so they want a real example.",
         "evidence": [{"title": "Power Automate & Office Scripts Data Pipeline", "role": "lead"},
                      {"title": "Data Analyst / Automation Engineer", "role": "backup"}],
         "star": {"situation": "Shangri-La's finance team retyped Excel request forms by hand.",
                  "task": "Automate intake and approvals.",
                  "action": "Built a Power Automate flow with an Office Script that maps each form into a standard template and routes approvals.",
                  "result": ""}},
        {"kind": "technical", "text": "Walk us through a system you moved to the cloud.", "provenance": "usual",
         "why": "Common for analyst roles in a firm with a large cloud practice.",
         "evidence": [{"title": "Enterprise Cloud Migration for Trading Platform", "role": "lead"}], "star": None},
        {"kind": "case", "text": "A client's sign-ups dropped 20%. Where do you start?", "provenance": "usual",
         "why": "Tests how you structure a vague problem out loud.", "evidence": [], "star": None},
    ],
    "evidence": [
        {"title": "Power Automate & Office Scripts Data Pipeline", "covers": ["Process change", "Stakeholders"]},
        {"title": "Enterprise Cloud Migration for Trading Platform", "covers": ["Cloud", "Teamwork"]},
        {"title": "Seads Singapore Website", "covers": ["Client-facing", "Ownership"]},
        {"title": "Hall 7 Website", "covers": ["Client-facing", "Ownership"]},
    ],
    "loose_ends": [
        {"kind": "question", "text": "Nothing yet for a case question. Practise one sizing case and one diagnosis case."},
        {"kind": "skill", "text": "The posting asks for SQL. No item shows it beyond a single tag."},
        {"kind": "revise", "text": "Read up on the firm's latest annual results and its AI practice."},
    ],
    "questions_for_them": [
        {"id": "s1", "text": "What does a first client project usually look like for an intern?", "sources": [], "own": False, "ask": True},
        {"id": "s2", "text": "How do analysts get feedback during a project?", "sources": [], "own": False, "ask": True},
        {"id": "s3", "text": "Which teams would this role work with most?", "sources": [], "own": True, "ask": False},
    ],
}

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
    for key in ("role", "notes", "opener"):
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
    if "competencies" in payload:
        values = payload.get("competencies")
        if not isinstance(values, list):
            errors.append("competencies")
        else:
            seen, comps = set(), []
            for v in values:
                c = _clean(v, 40)
                if c and c.lower() not in seen:
                    seen.add(c.lower())
                    comps.append(c)
            fields["competencies"] = comps[:MAX_COMPETENCIES]
    if "posting_url" in payload or not partial:
        url = _clean(payload.get("posting_url"), TEXT_LIMITS["posting_url"])
        if url and not url.startswith(("https://", "http://")):
            errors.append("posting_url")
        fields["posting_url"] = url
    return fields, errors


def theirs_list(meta):
    """Questions for them, each with a stable id.

    Research writes them without ids; an id is derived from the text so the
    same question keeps it until it's edited.
    """
    out = []
    for item in meta.get("questions_for_them") or []:
        if isinstance(item, str):
            item = {"text": item}
        text = item.get("text", "")
        out.append({
            "id": item.get("id") or "r" + hashlib.sha1(text.encode("utf-8")).hexdigest()[:9],
            "text": text, "source_ids": list(item.get("source_ids") or []),
            "own": bool(item.get("own")), "ask": bool(item.get("ask")),
        })
    return out


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
    # The public tables are only ever scanned from here, never written.
    public_items = dynamodb.Table("ctrlaltjay-portfolio-items")
    public_resume = dynamodb.Table("ctrlaltjay-resume-items")
    public_skills = dynamodb.Table("ctrlaltjay-skills")

    def _scan(table, **kwargs):
        resp = table.scan(**kwargs)
        items = resp.get("Items", [])
        while resp.get("LastEvaluatedKey"):
            resp = table.scan(ExclusiveStartKey=resp["LastEvaluatedKey"], **kwargs)
            items += resp.get("Items", [])
        return [_plain(i) for i in items]

    def _pool():
        return ce.build_pool(_scan(public_items), _scan(public_resume), _scan(stories))

    def _competencies(meta):
        if "competencies" in meta:
            return list(meta["competencies"])
        return list(ce.DEFAULT_COMPETENCIES.get(meta.get("occasion"), []))

    research_fn = os.getenv("CASEBOOK_RESEARCH_FUNCTION", "ctrlaltjay-casebook-research")
    lambda_client = boto3.client("lambda")

    def _month_spent():
        month = datetime.now(timezone.utc).strftime("%Y-%m")
        row = casebooks.get_item(Key={"pk": "SPEND", "sk": month}).get("Item") or {}
        return float(row.get("spent_usd") or 0)

    def _research_state(meta):
        status = meta.get("research_status", "not_started")
        started = meta.get("research_started_at", "")
        if status in ("queued", "running") and started:
            began = datetime.strptime(started, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
            if datetime.now(timezone.utc) - began > STALE_RUN:
                status = "failed"
        spent = _month_spent()
        return {
            "status": status,
            "progress": meta.get("research_progress", ""),
            "error": meta.get("research_error", "") if status == "failed" and meta.get("research_error")
            else ("Research stopped without finishing." if status == "failed" else ""),
            "started_at": started,
            "run_cost": float(meta.get("research_run_cost") or 0),
            "run_searches": int(meta.get("research_run_searches") or 0),
            "per_case": MAX_USD_PER_CASE,
            "per_month": MAX_USD_PER_MONTH,
            "spent_month": round(spent, 2),
            "available": round(min(MAX_USD_PER_CASE, MAX_USD_PER_MONTH - spent), 2),
        }

    def _view(meta, rows):
        pool = _pool()
        by_ref = {e["ref"]: e for e in pool}
        comps = _competencies(meta)
        hidden = list(meta.get("hidden") or [])
        overrides = meta.get("overrides") or {}
        scored = ce.coverage(pool, comps, overrides, hidden)
        sources = {int(r["id"]): {"id": int(r["id"]), "title": r.get("title", ""), "url": r.get("url", ""),
                                  "date": r.get("date", ""), "supports": r.get("supports", "")}
                   for r in rows if r["sk"].startswith("SRC#")}

        def cite(ids):
            return [sources[int(i)] for i in ids or [] if int(i) in sources]

        q_rows = sorted((r for r in rows if r["sk"].startswith("Q#")), key=lambda r: (r.get("created_at", ""), r["sk"]))
        # Questions keep their own competencies even if the case list changes,
        # so evidence is picked against both.
        extra = [c for q in q_rows for c in (q.get("competencies") or []) if c not in comps]
        scored_q = ce.coverage(pool, comps + list(dict.fromkeys(extra)), overrides, hidden) if extra else scored

        questions, loose = [], []
        for q in q_rows:
            refs = ce.pick_evidence(q, scored_q, by_ref)
            lead = by_ref[refs[0]] if refs else None
            star = ce.outline(lead) if q.get("kind") != "motivation" else None
            questions.append({
                "id": q["id"], "kind": q.get("kind"), "text": q.get("text"), "provenance": q.get("provenance"),
                "why": q.get("why", ""), "competencies": q.get("competencies") or [],
                "sources": cite(q.get("source_ids")), "requirement": q.get("requirement", ""),
                "chosen": bool(q.get("evidence_refs")), "story_id": q.get("story_id", ""),
                "evidence": [{"ref": r, "title": by_ref[r]["title"], "type": by_ref[r]["type"],
                              "role": "lead" if i == 0 else "backup"} for i, r in enumerate(refs)],
                "star": star,
                "drill": {"box": int(q.get("drill_box") or 0), "rating": q.get("drill_rating", ""),
                          "last": q.get("drill_last", ""), "count": int(q.get("drill_count") or 0)},
            })
            if not refs:
                loose.append({"kind": "question", "text": f"Nothing answers \u201c{q.get('text')}\u201d yet."})
            elif lead["type"] == "story" and star:
                missing = [f for f in ce.STAR_FIELDS if not star[f]]
                if missing:
                    loose.append({"kind": "story", "text": f"\u201c{lead['title']}\u201d still needs its {', '.join(missing)}."})
        for topic in meta.get("research_topics") or []:
            loose.append({"kind": "revise", "text": topic})
        for comp in comps:
            if not any(comp in s["covers"] for s in scored):
                loose.append({"kind": "skill", "text": f"Nothing in your material shows {comp} yet."})

        return {
            "casebook": meta,
            "competencies": comps,
            "questions": questions,
            "evidence": [{"ref": s["entry"]["ref"], "title": s["entry"]["title"], "type": s["entry"]["type"],
                          "covers": s["covers"], "why": s["why"], "overridden": s["overridden"]}
                         for s in scored[:ce.MAX_RANKED]],
            "matched_total": len(scored),
            "hidden": [{"ref": r, "title": by_ref[r]["title"]} for r in hidden if r in by_ref],
            "stories": [{"id": e["id"], "title": e["title"]} for e in pool if e["type"] == "story"],
            "loose_ends": loose,
            "questions_for_them": [{"id": t["id"], "text": t["text"], "sources": cite(t["source_ids"]), "own": t["own"], "ask": t["ask"]}
                                   for t in theirs_list(meta)],
            "brief": {k: ([{"text": f.get("text", ""), "sources": cite(f.get("source_ids"))} for f in v]
                          if k in ("values", "format", "recent") else v)
                      for k, v in meta["research_brief"].items()} if meta.get("research_brief") else None,
            "research": _research_state(meta),
            "drill_help": _drill_help(),
        }

    def _drill_help():
        return dict(casebook_drill.budget(casebooks), enabled=bool(app.config.get("OWNER_CLAUDE_API_KEY")) and casebook_drill.MAX_USD_PER_MONTH > 0)

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

    @bp.route("/owner/casebook", methods=["GET"])
    def casebook_page():
        return render_template("casebook.html")

    @bp.route("/owner/casebook/<name>", methods=["GET"])
    def casebook_asset(name):
        # The screen's code is served from here rather than /static so nothing
        # about Casebook is public, not even its scripts.
        if name not in UI_FILES:
            abort(404)
        with open(os.path.join(UI_DIR, name), encoding="utf-8") as fh:
            return Response(fh.read(), mimetype=UI_FILES[name].split(";")[0], content_type=UI_FILES[name])

    @bp.route("/api/owner/casebooks/<case_id>/questions/<qid>/drill", methods=["POST"])
    def question_drill(case_id, qid):
        if not ID_RE.match(case_id) or not ID_RE.match(qid):
            abort(404)
        rating = (request.get_json(silent=True) or {}).get("rating")
        if rating not in DRILL_RATINGS:
            return jsonify({"error": "Rate it Missed it, Shaky or Got it."}), 400
        key = {"pk": f"CASE#{case_id}", "sk": f"Q#{qid}"}
        row = casebooks.get_item(Key=key).get("Item")
        if not row:
            abort(404)
        box = int(row.get("drill_box") or 0)
        # Three boxes: a miss starts over, shaky steps back, got it moves on.
        box = 0 if rating == "missed" else max(0, box - 1) if rating == "shaky" else min(DRILL_TOP_BOX, box + 1)
        casebooks.update_item(Key=key, UpdateExpression="SET drill_box = :b, drill_rating = :r, drill_last = :t ADD drill_count :one",
                              ExpressionAttributeValues={":b": box, ":r": rating, ":t": _now(), ":one": 1})
        return jsonify({"box": box, "rating": rating})

    @bp.route("/api/owner/casebooks/<case_id>/drill/feedback", methods=["POST"])
    def drill_feedback(case_id):
        payload = request.get_json(silent=True) or {}
        qid = str(payload.get("qid") or "")
        if case_id == "sample":
            m = re.fullmatch(r"s(\d{1,2})", qid)
            questions = SAMPLE_CASEBOOK["questions"]
            if not m or int(m.group(1)) >= len(questions):
                abort(404)
            question = questions[int(m.group(1))]
        else:
            if not ID_RE.match(case_id) or not ID_RE.match(qid):
                abort(404)
            meta = _plain(_meta(case_id))
            question = next((q for q in _view(meta, [_plain(r) for r in _rows(case_id)])["questions"] if q["id"] == qid), None)
            if not question:
                abort(404)
        try:
            seconds = max(0, min(3600, int(payload.get("seconds") or 0)))
        except (TypeError, ValueError):
            seconds = 0
        try:
            result = casebook_drill.feedback(casebooks, app.config.get("OWNER_CLAUDE_API_KEY", ""), question, payload.get("answer"),
                                             seconds, client_factory=app.config.get("CASEBOOK_DRILL_CLIENT"))
        except casebook_drill.DrillError as err:
            return jsonify({"error": str(err), "budget": _drill_help()}), 400
        result["budget"] = _drill_help()
        return jsonify(result)

    @bp.route("/api/owner/casebooks/sample", methods=["GET"])
    def casebook_sample():
        return jsonify(dict(SAMPLE_CASEBOOK, drill_help=_drill_help()))

    @bp.route("/api/owner/casebook/options", methods=["GET"])
    def options():
        return jsonify({"occasions": OCCASIONS, "formats": FORMATS, "kinds": ce.QUESTION_KINDS})

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
            **{k: v for k, v in fields.items() if k != "competencies"},
            # Pasted posting text is only ever handed to a research run, never
            # stored: the casebook keeps a summary and the link instead.
            "posting_provided": bool(str(payload.get("posting_text") or "").strip()),
            "competencies": fields.get("competencies") or ce.DEFAULT_COMPETENCIES.get(fields["occasion"], []),
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
            return jsonify(_view(_plain(meta), [_plain(r) for r in _rows(case_id)]))

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

    @bp.route("/api/owner/casebooks/<case_id>/research", methods=["POST"])
    def casebook_research(case_id):
        if not ID_RE.match(case_id):
            abort(404)
        meta = _plain(_meta(case_id))
        state = _research_state(meta)
        if state["status"] in ("queued", "running"):
            return jsonify({"error": "Research is already running for this case."}), 409
        budget = state["available"]
        if budget < MIN_RUN_USD:
            return jsonify({"error": f"This month's research budget is used up (US${state['spent_month']:.2f} of "
                                     f"US${MAX_USD_PER_MONTH:.2f}). It resets on the 1st."}), 400
        posting_text = str((request.get_json(silent=True) or {}).get("posting_text") or "").strip()[:POSTING_TEXT_LIMIT]
        run_id = uuid.uuid4().hex
        casebooks.update_item(
            Key={"pk": f"CASE#{case_id}", "sk": "META"},
            UpdateExpression=("SET research_status = :q, research_run = :r, research_started_at = :t, "
                              "research_progress = :p, research_error = :e, research_run_cost = :z, "
                              "research_run_searches = :n, posting_provided = :pp"),
            ExpressionAttributeValues={":q": "queued", ":r": run_id, ":t": _now(), ":p": "Waiting to start",
                                       ":e": "", ":z": Decimal("0"), ":n": 0,
                                       ":pp": bool(posting_text) or bool(meta.get("posting_provided"))},
        )
        # The pasted posting goes to the run in the invocation and is never
        # written to a table.
        lambda_client.invoke(
            FunctionName=research_fn,
            InvocationType="Event",
            Payload=json.dumps({"action": "research", "case_id": case_id, "run_id": run_id,
                                "budget_usd": budget, "posting_text": posting_text}).encode(),
        )
        return jsonify({"ok": True, "budget": budget}), 202

    @bp.route("/api/owner/casebooks/<case_id>/coverage", methods=["PUT"])
    def casebook_coverage(case_id):
        if not ID_RE.match(case_id):
            abort(404)
        meta = _plain(_meta(case_id))
        payload = request.get_json(silent=True) or {}
        ref = str(payload.get("ref") or "")
        if not REF_RE.match(ref) or ref not in {e["ref"] for e in _pool()}:
            return jsonify({"error": "That item isn't in your material any more."}), 400
        overrides = dict(meta.get("overrides") or {})
        hidden = list(meta.get("hidden") or [])
        if "hidden" in payload:
            hidden = [r for r in hidden if r != ref] + ([ref] if payload.get("hidden") else [])
        else:
            comp = payload.get("competency")
            if comp not in _competencies(meta):
                return jsonify({"error": "That isn't one of the things this case looks for."}), 400
            per_item = dict(overrides.get(ref) or {})
            covers = payload.get("covers")
            if covers is None:
                per_item.pop(comp, None)
            else:
                per_item[comp] = bool(covers)
            if per_item:
                overrides[ref] = per_item
            else:
                overrides.pop(ref, None)
        casebooks.update_item(
            Key={"pk": f"CASE#{case_id}", "sk": "META"},
            UpdateExpression="SET #o = :o, #h = :h, updated_at = :u",
            ExpressionAttributeNames={"#o": "overrides", "#h": "hidden"},
            ExpressionAttributeValues={":o": overrides, ":h": hidden, ":u": _now()},
        )
        return jsonify({"ok": True})

    def _question_fields(payload, refs_allowed):
        fields, errors = {}, []
        if "text" in payload:
            text = _clean(payload.get("text"), 300)
            if not text:
                errors.append("text")
            fields["text"] = text
        if "kind" in payload:
            if payload.get("kind") not in ce.QUESTION_KINDS:
                errors.append("kind")
            fields["kind"] = payload.get("kind")
        if "evidence_refs" in payload:
            refs = payload.get("evidence_refs") or []
            if not isinstance(refs, list) or any(r not in refs_allowed for r in refs):
                errors.append("evidence_refs")
            else:
                fields["evidence_refs"] = list(dict.fromkeys(refs))[:2]
        if "story_id" in payload:
            sid = str(payload.get("story_id") or "")
            if sid and "story:" + sid not in refs_allowed:
                errors.append("story_id")
            fields["story_id"] = sid
        return fields, errors

    @bp.route("/api/owner/casebooks/<case_id>/questions", methods=["POST"])
    def question_collection(case_id):
        if not ID_RE.match(case_id):
            abort(404)
        meta = _plain(_meta(case_id))
        existing = [r for r in _rows(case_id) if r["sk"].startswith("Q#")]
        payload = request.get_json(silent=True) or {}
        # Microseconds plus an index keep questions in the order they were
        # added, even several in the same second.
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
        if payload.get("usual"):
            have = {str(r.get("text", "")).lower() for r in existing}
            new = [dict(q, provenance="usual") for q in ce.USUAL_QUESTIONS.get(meta.get("occasion"), [])
                   if q["text"].lower() not in have]
        else:
            fields, errors = _question_fields({"text": payload.get("text"), "kind": payload.get("kind") or "behavioural"}, set())
            if errors:
                return jsonify({"error": "A question needs some words and a kind.", "fields": errors}), 400
            new = [dict(fields, provenance="own", why="", competencies=[])]
        if len(existing) + len(new) > MAX_QUESTIONS:
            return jsonify({"error": f"A case holds up to {MAX_QUESTIONS} questions."}), 400
        with casebooks.batch_writer() as batch:
            for i, q in enumerate(new):
                qid = uuid.uuid4().hex[:12]
                batch.put_item(Item={"pk": f"CASE#{case_id}", "sk": f"Q#{qid}", "id": qid, **q,
                                     "created_at": f"{now}#{i:02d}"})
        return jsonify({"added": len(new)}), 201

    @bp.route("/api/owner/casebooks/<case_id>/questions/<qid>", methods=["PATCH", "DELETE"])
    def question_item(case_id, qid):
        if not ID_RE.match(case_id) or not ID_RE.match(qid):
            abort(404)
        _meta(case_id)
        key = {"pk": f"CASE#{case_id}", "sk": f"Q#{qid}"}
        row = casebooks.get_item(Key=key).get("Item")
        if not row:
            abort(404)
        if request.method == "DELETE":
            casebooks.delete_item(Key=key)
            return jsonify({"ok": True})
        fields, errors = _question_fields(request.get_json(silent=True) or {}, {e["ref"] for e in _pool()})
        if errors:
            return jsonify({"error": "Check these fields.", "fields": errors}), 400
        casebooks.put_item(Item={**row, **fields, "updated_at": _now()})
        return jsonify({"ok": True})

    def _save_theirs(meta, items, dismissed=None):
        expr, values = "SET questions_for_them = :q, updated_at = :t", {":q": items, ":t": _now()}
        if dismissed is not None:
            expr += ", theirs_dismissed = :d"
            values[":d"] = dismissed[-50:]
        casebooks.update_item(Key={"pk": meta["pk"], "sk": "META"}, UpdateExpression=expr, ExpressionAttributeValues=values)

    def _theirs_case(case_id):
        if not ID_RE.match(case_id):
            abort(404)
        meta = _plain(_meta(case_id))
        return meta, theirs_list(meta)

    def _theirs_view(case_id):
        meta = _plain(_meta(case_id))
        return jsonify(_view(meta, [_plain(r) for r in _rows(case_id)]))

    @bp.route("/api/owner/casebooks/<case_id>/theirs", methods=["POST"])
    def theirs_add(case_id):
        meta, items = _theirs_case(case_id)
        text = _clean((request.get_json(silent=True) or {}).get("text"), THEIRS_LIMIT)
        if not text:
            return jsonify({"error": "Write the question first."}), 400
        if len(items) >= MAX_THEIRS:
            return jsonify({"error": f"Keep it to {MAX_THEIRS} questions for them."}), 400
        items.append({"id": uuid.uuid4().hex[:10], "text": text, "source_ids": [], "own": True, "ask": True})
        _save_theirs(meta, items)
        return _theirs_view(case_id), 201

    @bp.route("/api/owner/casebooks/<case_id>/theirs/<tid>", methods=["PATCH", "DELETE"])
    def theirs_item(case_id, tid):
        meta, items = _theirs_case(case_id)
        hit = [i for i in items if i["id"] == tid]
        if not hit:
            abort(404)
        item = hit[0]
        if request.method == "DELETE":
            items.remove(item)
            # Research shouldn't bring back a question the owner took off.
            dismissed = list(meta.get("theirs_dismissed") or [])
            if not item["own"]:
                dismissed.append(item["text"])
            _save_theirs(meta, items, dismissed)
            return _theirs_view(case_id)
        payload = request.get_json(silent=True) or {}
        if "text" in payload:
            text = _clean(payload.get("text"), THEIRS_LIMIT)
            if not text:
                return jsonify({"error": "The question can't be empty."}), 400
            if text != item["text"]:
                item["text"], item["own"], item["source_ids"] = text, True, []
                item["id"] = uuid.uuid4().hex[:10] if item["id"].startswith("r") else item["id"]
        if "ask" in payload:
            item["ask"] = bool(payload.get("ask"))
        _save_theirs(meta, items)
        return _theirs_view(case_id)

    @bp.route("/api/owner/evidence/pool", methods=["GET"])
    def evidence_pool():
        pool = _pool()
        skills = sorted({s.get("name", "") for s in _scan(public_skills) if s.get("name")}, key=str.lower)
        return jsonify({
            "items": [{"ref": e["ref"], "id": e["id"], "title": e["title"], "type": e["type"]}
                      for e in pool if e["type"] != "story"],
            "skills": skills,
        })

    def _story_usage():
        rows = _scan(casebooks)
        titles = {r["pk"]: (f"{r.get('organisation')}: {r.get('role')}" if r.get("role") else r.get("organisation"))
                  for r in rows if r["sk"] == "META"}
        used = {}
        for r in rows:
            if r["sk"].startswith("Q#") and r.get("story_id") and r["pk"] in titles:
                used.setdefault(r["story_id"], {})[r["pk"][5:]] = titles[r["pk"]]
        return used

    @bp.route("/api/owner/stories", methods=["GET", "POST"])
    def story_collection():
        if request.method == "GET":
            resp = stories.scan()
            items = resp.get("Items", [])
            while resp.get("LastEvaluatedKey"):
                resp = stories.scan(ExclusiveStartKey=resp["LastEvaluatedKey"])
                items += resp.get("Items", [])
            used = _story_usage()
            out = []
            for i in items:
                story = _plain(i)
                story["used_in"] = [{"id": k, "title": v} for k, v in used.get(story["id"], {}).items()]
                out.append(story)
            return jsonify(sorted(out, key=lambda i: i.get("updated_at", ""), reverse=True))

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
            # Questions that used the story fall back to their best match.
            for r in _scan(casebooks):
                if r["sk"].startswith("Q#") and r.get("story_id") == story_id:
                    casebooks.update_item(Key={"pk": r["pk"], "sk": r["sk"]}, UpdateExpression="REMOVE story_id")
            return jsonify({"ok": True})
        fields, errors = _story_fields(request.get_json(silent=True) or {})
        if errors:
            return jsonify({"error": "A story needs a title.", "fields": errors}), 400
        item = {**existing, **fields, "updated_at": _now()}
        stories.put_item(Item=item)
        return jsonify(_plain(item))

    app.register_blueprint(bp)
