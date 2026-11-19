"""Casebook research worker.

The app starts this asynchronously, so a run never sits in a web request.
A run searches the web for one casebook, then turns its notes into
questions. Nothing is copied from sources beyond titles, links and dates:
everything else is written in plain words by the model and checked here
before it is stored.
"""
import json
import os
import re
import uuid
from datetime import datetime, timezone
from decimal import Decimal

import boto3

_ssm = boto3.client("ssm")
_table = boto3.resource("dynamodb").Table(os.environ.get("CASEBOOKS_TABLE", "ctrlaltjay-casebooks"))

MODEL = os.environ.get("CASEBOOK_MODEL", "claude-opus-5-5")
MAX_SEARCHES = int(os.environ.get("CASEBOOK_MAX_SEARCHES", "25"))
# Per million tokens, and per search, in US dollars. Kept in config so a
# price change doesn't need a code change.
PRICE = {
    "input": float(os.environ.get("CASEBOOK_PRICE_INPUT", "4")),
    "output": float(os.environ.get("CASEBOOK_PRICE_OUTPUT", "20")),
    "cache_read": float(os.environ.get("CASEBOOK_PRICE_CACHE_READ", "0.2")),
    "cache_write": float(os.environ.get("CASEBOOK_PRICE_CACHE_WRITE", "5")),
    "search": float(os.environ.get("CASEBOOK_PRICE_SEARCH", "0.01")),
}
# Searching stops once this much of the run's budget is spent, leaving the
# rest for writing the notes up.
SEARCH_SHARE = 0.75
MAX_CONTINUATIONS = 8

OCCASIONS = {
    "interview": "internship or job interview",
    "volunteering": "overseas volunteering or community trip",
    "scholarship": "scholarship or exchange application",
    "pitch": "competition or hackathon pitch",
    "leadership": "CCA or leadership interview",
    "networking": "networking chat",
}
KINDS = ["motivation", "behavioural", "technical", "case", "adaptability", "teamwork", "cause", "hardship"]


def _now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _dec(value):
    return Decimal(str(round(float(value), 4)))


def _api_key():
    try:
        value = _ssm.get_parameter(Name=os.environ["CASEBOOK_API_KEY_SSM_PARAM"], WithDecryption=True)["Parameter"]["Value"]
    except _ssm.exceptions.ParameterNotFound:
        return ""
    return value.strip()


def _clip(text, limit):
    text = re.sub(r"\s+", " ", str(text or "")).strip()
    return text[:limit]


def _norm(text):
    return re.sub(r"[^a-z0-9]+", " ", str(text or "").lower()).strip()


class Run:
    def __init__(self, case_id, run_id, budget):
        self.case_id = case_id
        self.run_id = run_id
        self.budget = budget
        self.cost = 0.0
        self.searches = 0
        self.key = {"pk": f"CASE#{case_id}", "sk": "META"}

    def charge(self, usage):
        if usage is None:
            return
        searches = 0
        stu = getattr(usage, "server_tool_use", None)
        if stu is not None:
            searches = getattr(stu, "web_search_requests", 0) or 0
        cost = (
            (usage.input_tokens or 0) * PRICE["input"]
            + (usage.output_tokens or 0) * PRICE["output"]
            + (getattr(usage, "cache_read_input_tokens", 0) or 0) * PRICE["cache_read"]
            + (getattr(usage, "cache_creation_input_tokens", 0) or 0) * PRICE["cache_write"]
        ) / 1_000_000 + searches * PRICE["search"]
        self.cost += cost
        self.searches += searches

    def progress(self, text):
        _table.update_item(
            Key=self.key,
            UpdateExpression="SET research_progress = :p, research_run_cost = :c, research_run_searches = :s",
            ConditionExpression="research_run = :r",
            ExpressionAttributeValues={":p": _clip(text, 200), ":c": _dec(self.cost), ":s": self.searches, ":r": self.run_id},
        )


def _case_brief(meta, posting_text):
    occasion = OCCASIONS.get(meta.get("occasion"), "interview")
    lines = [
        f"Occasion: {occasion}",
        f"Organisation: {meta.get('organisation', '')}",
    ]
    if meta.get("role"):
        lines.append(f"Role or programme: {meta['role']}")
    if meta.get("date"):
        lines.append(f"Date: {meta['date']}")
    if meta.get("format") and meta.get("format") != "unknown":
        lines.append(f"Format, if known: {meta['format'].replace('_', ' ')}")
    if meta.get("notes"):
        lines.append(f"Their own notes: {meta['notes']}")
    if meta.get("posting_url"):
        lines.append(f"Posting link: {meta['posting_url']}")
    brief = "\n".join(lines)
    if posting_text:
        brief += f"\n\n<posting>\n{posting_text}\n</posting>"
    return brief


SEARCH_SYSTEM = """You research an upcoming occasion for one person so they can prepare. Find:
1. What the organisation says it values, from its own pages where possible.
2. The interview or selection format for this role or programme.
3. Questions people report being asked for this or a similar role there, and where and when they reported it.
4. Anything recent about the organisation worth knowing before the date.

Rules:
- Only state what a source supports. If you can't find something, say so plainly; that is a useful answer.
- Prefer the organisation's own pages and first-hand reports from candidates. Note how old each source is.
- Write in your own words. Don't copy passages.
- Don't search for the person preparing, only the organisation and the role.
- If a posting link is given, fetch it first.

End with short notes under four headings that match the list above."""

WRITE_SYSTEM = """You turn research notes into a casebook for someone preparing for an occasion. Reply with JSON that matches the schema.

Provenance, which is checked after you reply:
- "reported": only when a numbered source says people were asked this question or one very close to it. List those source ids.
- "posting": only when the question follows from a requirement stated in the posting. Put a short phrase copied exactly from the posting in "requirement".
- "usual": everything else. This is your judgement of what's common for this kind of role, and it is labelled that way.
Never imply the organisation asks something without a source.

Content:
- 6 to 10 questions on the table, spread across kinds. "why" is one plain sentence on why they'd ask it.
- competencies: up to 6 short labels (one to three words) for what this organisation looks for, taken from what it says it values.
- questions_for_them: 3 to 5 questions worth asking the organisation, grounded in what research found.
- topics_to_revise: up to 5 short topics to read up on before the day.
- values, format and recent: one plain sentence per item, with the source ids that support it.
- not_found: things research looked for but could not find.
- sources: for each source id you rely on, a few words on what it supports.
Write plainly. No em dashes. Don't use the words delve, leverage, seamless, robust, elevate, unlock or empower."""

ID_LIST = {"type": "array", "items": {"type": "integer"}}
FINDING = {
    "type": "object",
    "properties": {"text": {"type": "string"}, "source_ids": ID_LIST},
    "required": ["text", "source_ids"],
    "additionalProperties": False,
}
SCHEMA = {
    "type": "object",
    "properties": {
        "values": {"type": "array", "items": FINDING},
        "format": {"type": "array", "items": FINDING},
        "recent": {"type": "array", "items": FINDING},
        "not_found": {"type": "array", "items": {"type": "string"}},
        "posting_summary": {"type": "string"},
        "competencies": {"type": "array", "items": {"type": "string"}},
        "questions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "kind": {"type": "string", "enum": KINDS},
                    "text": {"type": "string"},
                    "why": {"type": "string"},
                    "provenance": {"type": "string", "enum": ["reported", "posting", "usual"]},
                    "source_ids": ID_LIST,
                    "requirement": {"type": "string"},
                    "competencies": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["kind", "text", "why", "provenance", "source_ids", "requirement", "competencies"],
                "additionalProperties": False,
            },
        },
        "questions_for_them": {"type": "array", "items": FINDING},
        "topics_to_revise": {"type": "array", "items": {"type": "string"}},
        "sources": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"id": {"type": "integer"}, "supports": {"type": "string"}},
                "required": ["id", "supports"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["values", "format", "recent", "not_found", "posting_summary", "competencies",
                 "questions", "questions_for_them", "topics_to_revise", "sources"],
    "additionalProperties": False,
}


def _block_dict(block):
    return block.model_dump() if hasattr(block, "model_dump") else dict(block)


def _search(client, run, meta, posting_text):
    tools = [{"type": "web_search_20260318", "name": "web_search", "max_uses": MAX_SEARCHES}]
    if meta.get("posting_url"):
        tools.append({"type": "web_fetch_20260318", "name": "web_fetch", "max_uses": 3})
    messages = [{"role": "user", "content": _case_brief(meta, posting_text)}]
    blocks = []
    for _ in range(MAX_CONTINUATIONS):
        with client.messages.stream(
            model=MODEL,
            max_tokens=32000,
            system=SEARCH_SYSTEM,
            tools=tools,
            output_config={"effort": "high"},
            messages=messages,
        ) as stream:
            message = stream.get_final_message()
        run.charge(message.usage)
        content = [_block_dict(b) for b in message.content]
        blocks += content
        queries = [b.get("input", {}).get("query") for b in content
                   if b.get("type") == "server_tool_use" and b.get("name") == "web_search"]
        queries = [q for q in queries if q]
        run.progress(f"Searched {run.searches} times. Last: {queries[-1]}" if queries else f"Searched {run.searches} times so far")
        if message.stop_reason == "refusal":
            raise RuntimeError("The model declined this research.")
        if message.stop_reason != "pause_turn":
            break
        if run.cost >= run.budget * SEARCH_SHARE:
            break
        # A paused turn is sent back unchanged so the server carries on.
        messages.append({"role": "assistant", "content": message.content})
    return blocks


def _collect(blocks):
    """Sources seen in the run, numbered, plus the notes with source markers."""
    sources, by_url = [], {}

    def add(url, title, date=""):
        if not url or not url.startswith(("http://", "https://")):
            return None
        if url not in by_url:
            by_url[url] = len(sources) + 1
            sources.append({"id": by_url[url], "url": url[:500], "title": _clip(title, 200) or url[:200], "date": _clip(date, 40)})
        elif date and not sources[by_url[url] - 1]["date"]:
            sources[by_url[url] - 1]["date"] = _clip(date, 40)
        return by_url[url]

    fetched = []
    notes = []
    for b in blocks:
        kind = b.get("type")
        if kind == "web_search_tool_result" and isinstance(b.get("content"), list):
            for r in b["content"]:
                add(r.get("url"), r.get("title"), r.get("page_age") or "")
        elif kind == "web_fetch_tool_result":
            doc = (b.get("content") or {}).get("content") or {}
            data = (doc.get("source") or {}).get("data")
            if isinstance(data, str):
                fetched.append(data)
        elif kind == "text":
            marks = []
            for c in b.get("citations") or []:
                n = add(c.get("url"), c.get("title"))
                if n and n not in marks:
                    marks.append(n)
            notes.append(b.get("text", "") + "".join(f" [S{n}]" for n in marks))
    return sources, "".join(notes).strip(), fetched


def _write(client, run, meta, notes, sources, posting_text, fetched):
    source_list = "\n".join(f"S{s['id']}: {s['title']} ({s['url']}){', ' + s['date'] if s['date'] else ''}" for s in sources)
    posting = posting_text or ("\n\n".join(fetched)[:20000] if fetched else "")
    content = (
        f"{_case_brief(meta, '')}\n\n<notes>\n{notes or 'No notes: research found nothing usable.'}\n</notes>\n\n"
        f"<sources>\n{source_list or 'None'}\n</sources>"
    )
    if posting:
        content += f"\n\n<posting>\n{posting}\n</posting>"
    with client.messages.stream(
        model=MODEL,
        max_tokens=16000,
        system=WRITE_SYSTEM,
        output_config={"effort": "medium", "format": {"type": "json_schema", "schema": SCHEMA}},
        messages=[{"role": "user", "content": content}],
    ) as stream:
        message = stream.get_final_message()
    run.charge(message.usage)
    if message.stop_reason == "refusal":
        raise RuntimeError("The model declined this research.")
    text = next((b.text for b in message.content if b.type == "text"), "")
    return json.loads(text)


def _checked(result, sources, posting_texts):
    """Apply the provenance rules in code, whatever the model claimed."""
    valid = {s["id"] for s in sources}
    posting_norm = " ".join(_norm(t) for t in posting_texts if t)

    def ids(values):
        return sorted({i for i in values or [] if i in valid})

    def findings(items, limit):
        out = []
        for it in (items or [])[:limit]:
            text = _clip(it.get("text"), 300)
            if text:
                out.append({"text": text, "source_ids": ids(it.get("source_ids"))})
        return out

    questions = []
    for q in (result.get("questions") or [])[:12]:
        text = _clip(q.get("text"), 300)
        if not text:
            continue
        prov = q.get("provenance")
        src = ids(q.get("source_ids"))
        requirement = _clip(q.get("requirement"), 160)
        if prov == "reported" and not src:
            prov = "usual"
        if prov == "posting":
            if not requirement or not posting_norm or _norm(requirement) not in posting_norm:
                prov = "usual"
        if prov != "posting":
            requirement = ""
        if prov == "usual":
            src = []
        questions.append({
            "kind": q.get("kind") if q.get("kind") in KINDS else "behavioural",
            "text": text, "why": _clip(q.get("why"), 300), "provenance": prov,
            "source_ids": src, "requirement": requirement,
            "competencies": [_clip(c, 40) for c in (q.get("competencies") or [])[:4] if _clip(c, 40)],
        })

    supports = {s.get("id"): _clip(s.get("supports"), 200) for s in result.get("sources") or []}
    brief = {
        "values": findings(result.get("values"), 6),
        "format": findings(result.get("format"), 4),
        "recent": findings(result.get("recent"), 5),
        "not_found": [_clip(t, 200) for t in (result.get("not_found") or [])[:6] if _clip(t, 200)],
        "posting_summary": _clip(result.get("posting_summary"), 600),
    }
    theirs = findings(result.get("questions_for_them"), 5)
    used = set()
    for group in (brief["values"], brief["format"], brief["recent"], theirs, questions):
        for it in group:
            used.update(it["source_ids"])
    kept = [dict(s, supports=supports.get(s["id"], "")) for s in sources if s["id"] in used]
    return {
        "brief": brief,
        "questions": questions,
        "questions_for_them": theirs,
        "topics": [_clip(t, 160) for t in (result.get("topics_to_revise") or [])[:5] if _clip(t, 160)],
        "competencies": [_clip(c, 40) for c in (result.get("competencies") or [])[:6] if _clip(c, 40)],
        "sources": kept,
    }


def _store(run, meta, checked):
    pk = run.key["pk"]
    old = _table.query(KeyConditionExpression="pk = :pk", ExpressionAttributeValues={":pk": pk})["Items"]
    now = datetime.now(timezone.utc)
    stamp = now.strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    with _table.batch_writer() as batch:
        # A new run replaces the last run's questions and sources. The
        # owner's own questions and the usual ones stay.
        for row in old:
            if row["sk"].startswith("SRC#") or (row["sk"].startswith("Q#") and row.get("origin") == "research"):
                batch.delete_item(Key={"pk": row["pk"], "sk": row["sk"]})
        for s in checked["sources"]:
            batch.put_item(Item={"pk": pk, "sk": f"SRC#{s['id']:03d}", "id": s["id"], "url": s["url"], "title": s["title"],
                                 "date": s["date"], "supports": s["supports"], "accessed": now.strftime("%Y-%m-%d")})
        have = {_norm(r.get("text")) for r in old if r["sk"].startswith("Q#") and r.get("origin") != "research"}
        for i, q in enumerate(checked["questions"]):
            if _norm(q["text"]) in have:
                continue
            qid = uuid.uuid4().hex[:12]
            batch.put_item(Item={"pk": pk, "sk": f"Q#{qid}", "id": qid, "origin": "research", **q, "created_at": f"{stamp}#{i:02d}"})

    comps = list(meta.get("competencies") or [])
    for c in checked["competencies"]:
        if len(comps) >= 12:
            break
        if c.lower() not in {x.lower() for x in comps}:
            comps.append(c)
    # Keep the owner's own questions for them and their picks for the sheet;
    # don't bring back ones they took off.
    previous = meta.get("questions_for_them") or []
    previous = [p if isinstance(p, dict) else {"text": p} for p in previous]
    picked = {p.get("text") for p in previous if p.get("ask")}
    dismissed = set(meta.get("theirs_dismissed") or [])
    theirs = [dict(q, ask=q.get("text") in picked) for q in checked["questions_for_them"] if q.get("text") not in dismissed]
    theirs += [p for p in previous if p.get("own")]
    checked["questions_for_them"] = theirs[:12]
    _table.update_item(
        Key=run.key,
        UpdateExpression=(
            "SET research_status = :d, researched_at = :t, research_brief = :b, research_topics = :tp, "
            "questions_for_them = :qt, competencies = :c, research_progress = :p, research_error = :e"
        ),
        ConditionExpression="research_run = :r",
        ExpressionAttributeValues={
            ":d": "done", ":t": _now(), ":b": checked["brief"], ":tp": checked["topics"],
            ":qt": checked["questions_for_them"], ":c": comps, ":p": "", ":e": "", ":r": run.run_id,
        },
    )


def _settle(run):
    """Record what the run cost on the case and against the month."""
    _table.update_item(
        Key=run.key,
        UpdateExpression="ADD cost_usd :c, searches :s SET research_run_cost = :c, research_run_searches = :s",
        ExpressionAttributeValues={":c": _dec(run.cost), ":s": run.searches},
    )
    month = datetime.now(timezone.utc).strftime("%Y-%m")
    _table.update_item(
        Key={"pk": "SPEND", "sk": month},
        UpdateExpression="ADD spent_usd :c, runs :one",
        ExpressionAttributeValues={":c": _dec(run.cost), ":one": 1},
    )


def _research(event):
    import anthropic

    case_id, run_id = event.get("case_id", ""), event.get("run_id", "")
    if not re.fullmatch(r"[0-9a-f]{12}", case_id) or not re.fullmatch(r"[0-9a-f]{32}", run_id):
        return {"error": "bad request"}
    key = {"pk": f"CASE#{case_id}", "sk": "META"}
    # Only a queued run starts. A retried invocation finds it already
    # running or finished and stops, so a run is never paid for twice.
    try:
        _table.update_item(
            Key=key,
            UpdateExpression="SET research_status = :running, research_progress = :p",
            ConditionExpression="research_run = :r AND research_status = :queued",
            ExpressionAttributeValues={":running": "running", ":p": "Starting", ":r": run_id, ":queued": "queued"},
        )
    except _table.meta.client.exceptions.ConditionalCheckFailedException:
        return {"skipped": True}

    run = Run(case_id, run_id, float(event.get("budget_usd") or 0))
    meta = _table.get_item(Key=key)["Item"]
    posting_text = str(event.get("posting_text") or "")[:20000]
    try:
        api_key = _api_key()
        if not api_key:
            raise RuntimeError("The research key isn't set up yet.")
        client = anthropic.Anthropic(api_key=api_key, max_retries=2)
        run.progress("Searching")
        blocks = _search(client, run, meta, posting_text)
        sources, notes, fetched = _collect(blocks)
        run.progress(f"Searched {run.searches} times. Writing it up")
        result = _write(client, run, meta, notes, sources, posting_text, fetched)
        checked = _checked(result, sources, [posting_text] + fetched)
        _store(run, meta, checked)
        return {"ok": True}
    except Exception as exc:  # noqa: BLE001 - every failure has to be recorded on the case
        message = str(exc) if isinstance(exc, RuntimeError) else "Research ran into an error and stopped."
        if exc.__class__.__name__ == "AuthenticationError":
            message = "The research key was rejected. It may need replacing."
        elif exc.__class__.__name__ == "RateLimitError":
            message = "The API was busy. Try again in a few minutes."
        _table.update_item(
            Key=key,
            UpdateExpression="SET research_status = :f, research_error = :e, research_progress = :p",
            ConditionExpression="research_run = :r",
            ExpressionAttributeValues={":f": "failed", ":e": message, ":p": "", ":r": run_id},
        )
        print(json.dumps({"case": case_id, "run": run_id, "error": exc.__class__.__name__}))
        return {"error": exc.__class__.__name__}
    finally:
        _settle(run)


def handler(event, context):
    action = (event or {}).get("action")
    if action == "check":
        return {"key_configured": bool(_api_key())}
    if action == "research":
        return _research(event)
    return {"error": "unknown action"}
