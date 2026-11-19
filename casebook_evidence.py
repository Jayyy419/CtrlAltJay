"""Matching the owner's own material to what a case looks for.

Everything here works only from stored facts: portfolio items, resume rows
and stories. Matches carry the word and field that triggered them, so the
owner can see why an item was picked and overrule it.
"""
import re

STAR_FIELDS = ("situation", "task", "action", "result")

# Each competency is matched by word prefixes, so "collaborat" catches
# collaborate, collaborated and collaboration.
LEXICON = {
    "Teamwork": ["team", "collaborat", "together", "committee", "group", "co-found", "crew", "cross-functional"],
    "Leadership": ["lead", "led ", "founder", "director", "head of", "president", "chair", "mentor", "captain", "organis", "organiz"],
    "Communication": ["present", "workshop", "pitch", "communicat", "stakeholder", "explain", "teach", "writ", "liais"],
    "Problem-solving": ["solv", "problem", "debug", "optimi", "automat", "analys", "analyz", "improv", "root cause"],
    "Ownership": ["founder", "owner", "built", "launch", "end-to-end", "from scratch", "set up", "establish", "ran "],
    "Technical depth": ["python", "aws", "cloud", "machine learning", "data", "sql", "react", "next.js", "typescript",
                        "api", "database", "infrastructure", "docker", "linux", "tensorflow", "server"],
    "Learning fast": ["certif", "course", "bootcamp", "self-taught", "foundations", "cert prep", "programme"],
    "Client-facing": ["client", "customer", "stakeholder", "café", "cafe", "shop", "sponsor", "business owner"],
    "Process change": ["automat", "process", "workflow", "streamlin", "migrat", "rebuild", "standardi"],
    "Community": ["community", "volunteer", "youth", "outreach", "hall", "resident", "cca", "club", "social"],
    "Adaptability": ["overseas", "abroad", "adapt", "expedition", "transition", "navy", "new environment"],
    "Teamwork across cultures": ["overseas", "international", "cultur", "expedition", "thailand", "abroad", "exchange"],
    "Handling hardship": ["hardship", "pressure", "difficult", "tough", "setback", "deadline", "navy", "security"],
    "Why this cause": ["community", "volunteer", "cause", "sustainab", "charity", "foundation"],
    "Academic drive": ["director's list", "dean", "gpa", "honours", "scholarship", "award", "module"],
    "Initiative": ["founded", "started", "initiat", "side project", "launched", "set up", "won ", "build fund"],
    "Business sense": ["business", "revenue", "sales", "market", "entrepreneur", "startup", "finance", "budget", "operations"],
    "Delivery": ["shipped", "launched", "live ", "deploy", "completed", "production", "deliver"],
    "Resilience": ["setback", "transition", "recover", "pressure", "persever", "withdrawn"],
}

DEFAULT_COMPETENCIES = {
    "interview": ["Problem-solving", "Teamwork", "Communication", "Ownership", "Technical depth", "Learning fast"],
    "volunteering": ["Why this cause", "Adaptability", "Teamwork across cultures", "Handling hardship", "Community"],
    "scholarship": ["Leadership", "Community", "Academic drive", "Initiative", "Resilience"],
    "pitch": ["Problem-solving", "Technical depth", "Delivery", "Teamwork", "Business sense"],
    "leadership": ["Leadership", "Teamwork", "Communication", "Ownership", "Community"],
    "networking": ["Technical depth", "Initiative", "Business sense", "Communication"],
}

QUESTION_KINDS = {
    "motivation": "Motivation and fit",
    "behavioural": "Behavioural",
    "technical": "Technical",
    "case": "Case or problem-solving",
    "adaptability": "Adaptability",
    "teamwork": "Teamwork across cultures",
    "cause": "Why this cause",
    "hardship": "Handling hardship",
}


def _q(kind, text, why, comps):
    return {"kind": kind, "text": text, "why": why, "competencies": comps}


# Generic questions for each occasion. They make no claim about any
# organisation, which is why they carry the "Usual for this kind of role"
# label and never "Reported".
USUAL_QUESTIONS = {
    "interview": [
        _q("motivation", "Why this role, and why us?", "Checks you've thought about this place and not just any job.", []),
        _q("motivation", "Walk us through your background.", "An easy opener that sets up everything after it.", ["Ownership"]),
        _q("behavioural", "Tell us about a time your team disagreed. What did you do?", "Shows how you work with people when it isn't smooth.", ["Teamwork", "Communication"]),
        _q("behavioural", "Tell us about something you built or ran from start to finish.", "They want to hear what you own, in your own words.", ["Ownership", "Problem-solving"]),
        _q("behavioural", "Tell us about a time something went wrong.", "Tests honesty and how you recover.", ["Problem-solving", "Ownership"]),
        _q("technical", "Walk us through a technical decision you'd make differently now.", "Shows depth and whether you learn from your own work.", ["Technical depth"]),
        _q("behavioural", "How do you pick up something new quickly?", "Interns are hired to learn fast.", ["Learning fast"]),
    ],
    "volunteering": [
        _q("cause", "Why this cause, and why now?", "They want people who'll stay committed when it gets tiring.", ["Why this cause", "Community"]),
        _q("adaptability", "Tell us about a time you had to adjust to somewhere new.", "The trip will put you somewhere unfamiliar.", ["Adaptability"]),
        _q("teamwork", "How do you work with people from a different background?", "You'll be working with a host community and a mixed team.", ["Teamwork across cultures"]),
        _q("hardship", "What would you do if conditions on the trip got hard?", "Checks you've thought about the hard parts, not just the photos.", ["Handling hardship"]),
        _q("behavioural", "What have you done for a community before?", "Past giving is the best sign of future giving.", ["Community"]),
    ],
    "scholarship": [
        _q("motivation", "Why this scholarship or programme?", "They want to see a fit between you and what they fund.", []),
        _q("behavioural", "Tell us about a time you led something.", "Most panels look for leadership first.", ["Leadership"]),
        _q("behavioural", "What have you given back to your community?", "Scholarships often expect you to contribute in return.", ["Community"]),
        _q("behavioural", "What's an achievement you're proud of?", "Lets you show drive in your own words.", ["Academic drive", "Initiative"]),
        _q("behavioural", "Tell us about a setback and how you handled it.", "Tests resilience and honesty.", ["Resilience"]),
    ],
    "pitch": [
        _q("case", "What problem are you solving, and for whom?", "Judges check the problem is real before anything else.", ["Problem-solving", "Business sense"]),
        _q("behavioural", "Why is your team the one to build this?", "They back teams as much as ideas.", ["Teamwork", "Delivery"]),
        _q("technical", "How does it work under the hood?", "Checks the build is real and not just slides.", ["Technical depth"]),
        _q("behavioural", "What have you shipped so far?", "Progress beats promises.", ["Delivery"]),
        _q("case", "How will this keep going after the competition?", "Tests whether you've thought past the demo.", ["Business sense"]),
    ],
    "leadership": [
        _q("motivation", "Why do you want this role?", "They want to know you'll show up when it's busy.", []),
        _q("behavioural", "Tell us about a time you led a team.", "The core of any leadership interview.", ["Leadership", "Teamwork"]),
        _q("behavioural", "How would you handle a member who isn't pulling their weight?", "Every committee has one.", ["Leadership", "Communication"]),
        _q("behavioural", "What would you change in your first month?", "Shows initiative and whether you've done your homework.", ["Ownership", "Initiative"]),
        _q("behavioural", "Tell us about something you organised for others.", "Shows you can run things, not just attend them.", ["Community", "Leadership"]),
    ],
    "networking": [
        _q("motivation", "What are you working on right now?", "The opener in almost every chat.", ["Technical depth", "Initiative"]),
        _q("motivation", "What kind of role are you looking for?", "Helps them work out how they can help.", []),
        _q("behavioural", "What's a project you're proud of?", "Gives them something to remember you by.", ["Ownership"]),
    ],
}

ITEM_TEXT_FIELDS = ("title", "summary", "description", "challenges", "deliverables", "extra_notes",
                    "skills", "category", "subsection", "tag")
TYPE_WEIGHT = {"story": 1.2, "item": 1.0, "resume": 0.8, "certification": 0.5}
STOP_WORDS = {"and", "the", "for", "with", "this", "that", "your", "skills", "skill"}
MAX_RANKED = 12


def _keywords(competency):
    if competency in LEXICON:
        return LEXICON[competency]
    words = [w for w in re.findall(r"[a-z0-9.+#/-]{3,}", competency.lower()) if w not in STOP_WORDS]
    return words or [competency.lower()]


def _sentences(text, limit=400):
    text = re.sub(r"\s+", " ", str(text or "")).strip()
    if len(text) <= limit:
        return text
    cut = text[:limit]
    end = max(cut.rfind(". "), cut.rfind("! "), cut.rfind("? "))
    return cut[: end + 1] if end > 80 else cut.rsplit(" ", 1)[0] + "..."


def build_pool(items, resume_rows, stories):
    """Flatten the owner's material into entries with searchable fields."""
    pool = []
    titles = {}
    for it in items:
        if str(it.get("id", "")).startswith("__") or it.get("deleted_at"):
            continue
        cert = (it.get("subsection") or it.get("category")) == "Certifications"
        fields = {f: str(it.get(f) or "") for f in ITEM_TEXT_FIELDS}
        titles[it["id"]] = it.get("title", "")
        pool.append({
            "ref": "item:" + it["id"], "id": it["id"], "title": it.get("title", ""),
            "type": "certification" if cert else "item", "section": it.get("section", ""),
            "skills": [s.strip() for s in str(it.get("skills") or "").split(",") if s.strip()],
            "fields": fields, "raw": it,
        })
    for row in resume_rows:
        if str(row.get("id", "")).startswith("__"):
            continue
        titles[row["id"]] = row.get("title", "")
        label = row.get("title", "")
        if row.get("subtitle"):
            label = f"{row.get('subtitle')}, {label}"
        pool.append({
            "ref": "resume:" + row["id"], "id": row["id"], "title": label, "type": "resume",
            "section": row.get("lane", ""), "skills": [],
            "fields": {"title": label, "description": str(row.get("description") or "")}, "raw": row,
        })
    for st in stories:
        linked = [titles.get(i, "") for i in st.get("item_ids") or []]
        fields = {f: str(st.get(f) or "") for f in STAR_FIELDS}
        fields["title"] = st.get("title", "")
        fields["skills"] = ", ".join(st.get("skills") or [])
        fields["linked"] = ", ".join(t for t in linked if t)
        pool.append({
            "ref": "story:" + st["id"], "id": st["id"], "title": st.get("title", ""), "type": "story",
            "section": "story", "skills": list(st.get("skills") or []), "fields": fields, "raw": st,
        })
    return pool


def match(entry, competency):
    """Return (field, word) for the first hit, or None."""
    if competency in entry["skills"]:
        return ("skills", competency)
    for word in _keywords(competency):
        # A trailing space in the lexicon means a whole word, so "won" doesn't
        # match "wonder".
        tail = r"(?![a-z0-9])" if word.endswith(" ") else ""
        pattern = re.compile(r"(?<![a-z0-9])" + re.escape(word.strip().lower()) + tail)
        for field, text in entry["fields"].items():
            if text and pattern.search(text.lower()):
                return (field, word.strip())
    return None


def coverage(pool, competencies, overrides=None, hidden=None):
    """Score every entry against the case's competencies, overrides applied."""
    overrides = overrides or {}
    hidden = set(hidden or [])
    scored = []
    for entry in pool:
        if entry["ref"] in hidden:
            continue
        forced = overrides.get(entry["ref"], {})
        covers, why, auto = [], {}, 0
        for comp in competencies:
            hit = match(entry, comp)
            auto += 1 if hit else 0
            state = forced.get(comp)
            if state is True or (state is None and hit):
                covers.append(comp)
                why[comp] = "you marked it" if state is True else f"\u201c{hit[1]}\u201d in {hit[0]}"
        # An item the owner has corrected stays listed even with no cells, so
        # the correction can be undone.
        if not covers and not forced:
            continue
        # Ranking uses automatic matches only, so correcting a cell never
        # moves its row.
        score = auto * TYPE_WEIGHT.get(entry["type"], 1.0) + (0.1 if entry["skills"] else 0)
        scored.append({"entry": entry, "covers": covers, "why": why, "score": score,
                       "overridden": sorted(c for c, v in forced.items() if v is not None)})
    scored.sort(key=lambda s: (-s["score"], s["entry"]["title"].lower()))
    return scored


def outline(entry):
    """A STAR outline from stored fields only. Empty means a visible gap."""
    if entry is None:
        return dict({f: "" for f in STAR_FIELDS}, **{"from": {}})
    raw = entry["raw"]
    if entry["type"] == "story":
        star = {f: str(raw.get(f) or "") for f in STAR_FIELDS}
        star["from"] = {f: "story" for f in STAR_FIELDS if star[f]}
        return star
    star = {f: "" for f in STAR_FIELDS}
    src = {}
    if entry["type"] == "resume":
        if raw.get("description"):
            star["situation"], src["situation"] = _sentences(raw["description"]), "resume"
    else:
        situation = raw.get("summary") or raw.get("description")
        if situation:
            star["situation"] = _sentences(situation)
            src["situation"] = "summary" if raw.get("summary") else "description"
        if raw.get("challenges"):
            star["task"], src["task"] = _sentences(raw["challenges"]), "challenges"
        action = raw.get("deliverables") or (raw.get("description") if raw.get("summary") else "")
        if action:
            star["action"] = _sentences(action)
            src["action"] = "deliverables" if raw.get("deliverables") else "description"
    # Results are never filled from an item: an outcome has to come from the
    # owner, through a story, so nothing gets overstated.
    star["from"] = src
    return star


def pick_evidence(question, scored, by_ref):
    """Lead and back-up evidence for a question: chosen ones first, then best match."""
    chosen = [r for r in (question.get("evidence_refs") or []) if r in by_ref]
    if question.get("story_id") and "story:" + question["story_id"] in by_ref:
        story_ref = "story:" + question["story_id"]
        chosen = [story_ref] + [r for r in chosen if r != story_ref]
    if len(chosen) < 2:
        comps = question.get("competencies") or []
        ranked = scored
        if comps:
            ranked = sorted(
                (s for s in scored if set(comps) & set(s["covers"])),
                key=lambda s: (-len(set(comps) & set(s["covers"])), -s["score"]),
            )
        for s in ranked:
            if len(chosen) >= 2:
                break
            if s["entry"]["ref"] not in chosen:
                chosen.append(s["entry"]["ref"])
    return chosen[:2]
