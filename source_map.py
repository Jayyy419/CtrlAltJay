"""Source Map, the public tours.

Tours are read only from the published rows in ctrlaltjay-public-city, which
Town hall writes when the owner publishes a map. Nothing here reads the
owner-side table or calls GitHub. A sample tour, clearly marked, lets the
page work before any map is published.
"""
import json
import os
import re

from flask import Blueprint, abort, jsonify, render_template

bp = Blueprint("source_map", __name__)
SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,60}$")

SAMPLE_TOUR = {
    "sample": True,
    "slug": "sample",
    "title": "How Lighthouse API answers a ping",
    "repo_name": "Lighthouse API",
    "private": False,
    "project_url": "",
    "building_slug": "",
    "districts": [
        {"name": "api", "size": 34}, {"name": "core", "size": 26}, {"name": "bots", "size": 18},
        {"name": "storage", "size": 14}, {"name": "tests", "size": 8},
    ],
    "stops": [
        {"title": "The front door", "district": "api", "lang": "python",
         "explanation": "Every ping arrives here. The handler only checks the shape of the request and hands it on, so this file stays boring on purpose.",
         "excerpt": {"start": 12, "mark": [14, 16], "lines": [
             "@app.post(\"/ping\")", "def ping(body: PingBody):", "    ping = Ping.from_body(body)",
             "    reply = route_ping(ping, registry)", "    return reply.to_response()"]},
         "permalink": ""},
        {"title": "Checking who's knocking", "district": "api", "lang": "python",
         "explanation": "Before anything else, the caller's key is checked against the list of fleets it may talk to. A wrong key costs one dictionary lookup, not a database call.",
         "excerpt": {"start": 40, "mark": [42, 44], "lines": [
             "def authorise(request):", "    key = request.headers.get(\"x-fleet-key\", \"\")",
             "    fleet = FLEETS.get(hash_key(key))", "    if fleet is None:", "        raise NotAllowed()", "    return fleet"]},
         "permalink": ""},
        {"title": "Finding the right bot", "district": "core", "lang": "python",
         "explanation": "Every ping names a bot. This function looks it up in the registry and refuses early if the bot is asleep, so the slow part only runs for bots that can answer.",
         "excerpt": {"start": 5, "mark": [7, 10], "lines": [
             "def route_ping(ping, registry):", "    # Unknown bots are refused before any work happens.",
             "    bot = registry.get(ping.bot_id)", "    if bot is None:", "        raise UnknownBot(ping.bot_id)",
             "    if not bot.awake:", "        return Reply.later(bot, retry_after=30)",
             "    job = bot.queue.push(ping.payload)", "    log.info(\"queued %s for %s\", job.id, bot.name)",
             "    return Reply.accepted(job)"]},
         "permalink": ""},
        {"title": "The bot wakes up", "district": "bots", "lang": "python",
         "explanation": "Bots sleep between jobs. Waking one restores its last state from storage, which is why a cold bot takes a beat longer to answer.",
         "excerpt": {"start": 22, "mark": [24, 26], "lines": [
             "async def wake(self):", "    if self.awake:", "        return", "    self.state = await store.load(self.id)",
             "    self.awake = True"]},
         "permalink": ""},
        {"title": "Writing it down", "district": "storage", "lang": "python",
         "explanation": "Each answer is saved before it's sent, so a crash between the two never loses a reply. The write is small: an id, a status and a timestamp.",
         "excerpt": {"start": 8, "mark": [9, 12], "lines": [
             "def save_reply(reply):", "    row = {\"id\": reply.id, \"status\": reply.status,",
             "           \"at\": now_iso()}", "    table.put_item(Item=row)", "    return row"]},
         "permalink": ""},
        {"title": "Sending the answer back", "district": "core", "lang": "python",
         "explanation": "Replies go back the same way the ping came in. Late replies are dropped on purpose: by then the caller has moved on.",
         "excerpt": {"start": 60, "mark": [61, 64], "lines": [
             "def deliver(reply, ping):", "    if ping.expired():", "        log.info(\"dropped late reply %s\", reply.id)",
             "        return False", "    return transport.send(ping.reply_to, reply)"]},
         "permalink": ""},
        {"title": "How I know it works", "district": "tests", "lang": "python",
         "explanation": "One test walks a ping through the whole route with a fake bot. If any stop on this tour breaks, this is the test that goes red.",
         "excerpt": {"start": 1, "mark": [4, 8], "lines": [
             "def test_ping_round_trip(fake_bot):", "    registry = Registry([fake_bot])", "    ping = Ping(bot_id=fake_bot.id, payload=\"hello\")",
             "    reply = route_ping(ping, registry)", "    assert reply.status == \"accepted\"", "    fake_bot.run_once()",
             "    assert store.last_reply(fake_bot.id).status == \"done\"", "    assert transport.sent_to(ping.reply_to)"]},
         "permalink": ""},
        {"title": "Back at the door", "district": "api", "lang": "python",
         "explanation": "The response leaves through the same handler it came in by. That's the whole trip: door, router, bot, storage, and back.",
         "excerpt": {"start": 80, "mark": [81, 83], "lines": [
             "def to_response(self):", "    body = {\"id\": self.id, \"status\": self.status}",
             "    code = 202 if self.status == \"accepted\" else 200", "    return JSONResponse(body, status_code=code)"]},
         "permalink": ""},
    ],
}


def register_source_map(app, dynamodb, static_version):
    public = dynamodb.Table(os.getenv("PUBLIC_CITY_TABLE", "ctrlaltjay-public-city"))

    def published(slug):
        item = public.get_item(Key={"pk": f"TOUR#{slug}", "sk": "CURRENT"}).get("Item")
        return json.loads(item["data"]) if item and item.get("data") else None

    def tour_or_404(slug):
        if not SLUG_RE.match(slug):
            abort(404)
        if slug == "sample":
            return SAMPLE_TOUR
        tour = published(slug)
        if not tour:
            abort(404)
        return tour

    @bp.route("/map/<slug>", methods=["GET"])
    @bp.route("/map/<slug>/<int:stop>", methods=["GET"])
    def map_page(slug, stop=1):
        tour = tour_or_404(slug)
        if stop < 1 or stop > len(tour["stops"]):
            abort(404)
        return render_template("map.html", tour=tour, stop=stop, css_v=static_version("css/map.css"), js_v=static_version("js/map.js"))

    @bp.route("/api/map/<slug>", methods=["GET"])
    def map_data(slug):
        resp = jsonify(tour_or_404(slug))
        resp.headers["Cache-Control"] = "public, max-age=300"
        return resp

    app.register_blueprint(bp)
