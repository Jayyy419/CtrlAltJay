"""Plotting, publishing and stale checks for Source Map tours, with the collector faked.

Runs in its own process with AWS faked by moto; see tests/run_all.py.
"""
import os, sys, json
import unittest
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from checks import Checks
os.environ.update(AWS_DEFAULT_REGION="ap-southeast-1", AWS_ACCESS_KEY_ID="x", AWS_SECRET_ACCESS_KEY="x",
                  SECRET_KEY="test-secret-key-0123456789abcdefghijkl", ADMIN_PASSCODE="right-passcode")
from moto import mock_aws
mock_aws().start()
import boto3
ddb = boto3.resource("dynamodb", region_name="ap-southeast-1")
for name in ("ctrlaltjay-portfolio-items", "ctrlaltjay-resume-items", "ctrlaltjay-skills", "ctrlaltjay-stories"):
    ddb.create_table(TableName=name, KeySchema=[{"AttributeName": "id", "KeyType": "HASH"}], AttributeDefinitions=[{"AttributeName": "id", "AttributeType": "S"}], BillingMode="PAY_PER_REQUEST")
for name in ("ctrlaltjay-public-city", "ctrlaltjay-town"):
    ddb.create_table(TableName=name, KeySchema=[{"AttributeName": "pk", "KeyType": "HASH"}, {"AttributeName": "sk", "KeyType": "RANGE"}],
        AttributeDefinitions=[{"AttributeName": "pk", "AttributeType": "S"}, {"AttributeName": "sk", "AttributeType": "S"}], BillingMode="PAY_PER_REQUEST")
town = ddb.Table("ctrlaltjay-town"); pub = ddb.Table("ctrlaltjay-public-city")
SHA = "a" * 40
def meta(i, full, private, mode="approved", **kw):
    town.put_item(Item=dict({"pk": f"REPO#{i}", "sk": "META", "github_id": i, "full_name": full, "private": private, "mode": mode,
        "default_branch": "main", "html_url": f"https://github.com/{full}", "visible_to_token": True, "pushed_at": "2026-11-18T00:00:00Z"}, **kw))
    town.put_item(Item={"pk": f"REPO#{i}", "sk": "STATS#2026-11-19", "commits": 10, "weeks": [[1700000000, 3]], "languages": {"Python": 1000}, "bytes": 1000})
meta(101, "jay/pubrepo", False)
meta(202, "jay/secret-client-work", True, public_name="Client dashboard", description="A dashboard I built.")
meta(303, "jay/hiddenrepo", False, mode="hidden")
FILES = {
 "api/handlers.py": ["import x"] + [f"def f{i}(): return {i}" for i in range(1, 60)],
 "core/router.py": ["def route(p):", "    return p", 'token = "ghp_' + "a1B2" * 9 + '"', "x = 1"],
 "client_acme/billing.py": ["def bill(c):", "    return c.total * 1.09"],
 "README.md": ["# hello"],
}
calls = []
def fake(payload):
    calls.append(payload)
    if payload["action"] == "tree":
        return {"sha": SHA, "branch": "main", "truncated": False, "files": [[p, len("\n".join(l))] for p, l in FILES.items()]}
    if payload["action"] == "file":
        if payload["path"] not in FILES: return {"error": "That file isn't there at this commit."}
        return {"lines": FILES[payload["path"]]}
sys.path.insert(0, ROOT)
import app as appmod
app = appmod.app
app.config["TOWN_COLLECTOR_CALL"] = fake


class Tours(Checks):
    def test_flow(self):

        anon = app.test_client()
        for m, p in [("GET", "/api/owner/townhall/tours"), ("GET", "/api/owner/townhall/tours/101"), ("POST", "/api/owner/townhall/tours/101/tree"),
                     ("POST", "/api/owner/townhall/tours/101/file"), ("POST", "/api/owner/townhall/tours/101/stops"), ("POST", "/api/owner/townhall/tours/101/publish"),
                     ("GET", "/owner/townhall/tour-preview/101"), ("GET", "/api/owner/townhall/tours/101/preview-tour")]:
            r = anon.open(p, method=m, json={})
            self.check(f"signed out 404 {m} {p}", r.status_code == 404 and "no-store" in r.headers.get("Cache-Control", ""))
        self.check("signed out never reached the collector", not calls)

        o = app.test_client(); o.post("/admin/auth", json={"passcode": "right-passcode"})
        L = o.get("/api/owner/townhall/tours").get_json()["tours"]
        self.check("tours list shows approved repos only", sorted(t["id"] for t in L) == [101, 202])
        t = o.post("/api/owner/townhall/tours/101/tree").get_json()
        self.check("tree gives files and districts", len(t["files"]) == 4 and {d["name"] for d in t["districts"]} >= {"api", "core", "."})
        self.check("default address from name", t["slug"] == "pubrepo")
        f = o.post("/api/owner/townhall/tours/101/file", json={"path": "api/handlers.py"}).get_json()
        self.check("file lines served", len(f["lines"]) == 60 and f["lang"] == "python")
        r = o.post("/api/owner/townhall/tours/101/stops", json={"path": "api/handlers.py", "start": 1, "end": 41})
        self.check("41 lines refused", r.status_code == 400 and "40" in r.get_json()["error"])
        r = o.post("/api/owner/townhall/tours/101/stops", json={"path": "api/handlers.py", "start": 2, "end": 6, "mark": [3, 4], "title": "Handlers", "explanation": "Where it starts.", "lines": ["EVIL"]})
        d = r.get_json(); s1 = d["stops"][0]
        self.check("stop plotted from the server copy", r.status_code == 201 and s1["lines"] == FILES["api/handlers.py"][1:6] and "EVIL" not in s1["lines"])
        self.check("stop keeps sha and marks", s1["sha"] == SHA and s1["mark"] == [3, 4] and s1["scan"]["status"] == "clear")
        r = o.post("/api/owner/townhall/tours/101/stops", json={"path": "core/router.py", "start": 1, "end": 4, "title": "Router", "explanation": "Routes."})
        s2 = r.get_json()["stops"][1]
        self.check("secret flagged on line 3", s2["scan"]["status"] == "flagged" and s2["scan"]["findings"][0]["line"] == 3)
        self.check("finding holds no value", "a1B2" not in json.dumps(s2["scan"]))
        d = o.get("/api/owner/townhall/tours/101").get_json()
        self.check("publish blocked while flagged", any("not a secret" in p for p in d["problems"]))
        r = o.post("/api/owner/townhall/tours/101/publish")
        self.check("publish refused", r.status_code == 400 and pub.get_item(Key={"pk": "TOUR#pubrepo", "sk": "CURRENT"}).get("Item") is None)
        r = o.post(f"/api/owner/townhall/tours/101/stops/{s2['id']}/not-a-secret").get_json()
        self.check("marked as not a secret", r["stops"][1]["scan"]["status"] == "false_positive" and not r["problems"])
        r = o.patch("/api/owner/townhall/tours/101", json={"order": [s2["id"], s1["id"]]}).get_json()
        self.check("reorder", [s["id"] for s in r["stops"]] == [s2["id"], s1["id"]])
        self.check("bad reorder refused", o.patch("/api/owner/townhall/tours/101", json={"order": [s1["id"]]}).status_code == 409)
        self.check("bad mark refused", o.patch("/api/owner/townhall/tours/101", json={"stop": {"id": s1["id"], "mark": [1, 9]}}).status_code == 400)
        self.check("sample address refused", o.patch("/api/owner/townhall/tours/101", json={"slug": "sample"}).status_code == 400)
        o.patch("/api/owner/townhall/tours/101", json={"title": "How pubrepo works", "slug": "pubrepo-tour"})
        self.check("preview page renders", o.get("/owner/townhall/tour-preview/101/2").status_code == 200)
        r = o.post("/api/owner/townhall/tours/101/publish")
        self.check("published", r.status_code == 200 and r.get_json()["published_slug"] == "pubrepo-tour")
        api = anon.get("/api/map/pubrepo-tour").get_json()
        self.check("public tour served", api["title"] == "How pubrepo works" and len(api["stops"]) == 2)
        self.check("public permalinks at the sha", api["stops"][1]["permalink"] == f"https://github.com/jay/pubrepo/blob/{SHA}/api/handlers.py#L2-L6")
        city = json.loads(pub.get_item(Key={"pk": "CITY", "sk": "CURRENT"})["Item"]["data"])
        b = [x for x in city["buildings"] if x["slug"] == "b101"][0]
        self.check("building links to the tour", b["tour_url"] == "/map/pubrepo-tour")
        self.check("public page renders", anon.get("/map/pubrepo-tour/2").status_code == 200)

        # Private repo: no paths, names, branches or links.
        o.post("/api/owner/townhall/tours/202/tree")
        o.post("/api/owner/townhall/tours/202/stops", json={"path": "client_acme/billing.py", "start": 1, "end": 2, "title": "Billing", "explanation": "Tax is added here."})
        r = o.post("/api/owner/townhall/tours/202/publish")
        self.check("private published", r.status_code == 200)
        slug = r.get_json()["published_slug"]
        raw = anon.get(f"/api/map/{slug}").get_data(as_text=True) + anon.get(f"/map/{slug}").get_data(as_text=True)
        self.check("private tour leaks no real names or paths", not any(x in raw for x in ("secret-client-work", "client_acme", "billing.py", "jay/", "github.com", SHA, "main\"")))
        self.check("private district gets a neutral label", "Area A" in raw)
        self.check("private excerpt is there", "c.total * 1.09" in raw)

        # Hidden repo: no tour routes for it, and the drawer takes a tour down.
        self.check("hidden repo tour list absent", 303 not in [t["id"] for t in o.get("/api/owner/townhall/tours").get_json()["tours"]])
        o.post("/api/owner/townhall/repos/101/drawer")
        self.check("drawer takes the tour down", anon.get("/api/map/pubrepo-tour").status_code == 404)
        city = json.loads(pub.get_item(Key={"pk": "CITY", "sk": "CURRENT"})["Item"]["data"])
        self.check("drawer removes the building", all(x["slug"] != "b101" for x in city["buildings"]))
        log = o.get("/api/owner/townhall/approvals").get_json()
        acts = [x["action"] for x in log]
        self.check("approvals log records map actions", {"publish_map", "not_a_secret", "drawer"} <= set(acts))
        self.check("publish refused when not approved", o.post("/api/owner/townhall/tours/101/publish").status_code == 400)

        # Stale check in the collector.
        import importlib
        os.environ["GITHUB_TOKEN_SSM_PARAM"] = "/x"
        sys.path.insert(0, os.path.join(ROOT, "town_collector"))
        import collector
        class FakeGH:
            def __init__(self, files): self.files = files; self.calls = 0
        collector._head = lambda gh, meta: ("b" * 40, "t")
        changed = {"client_acme/billing.py": ["def bill(c):", "    return c.total * 1.10"]}
        collector._read = lambda gh, meta, sha, path: (changed.get(path, FILES.get(path)), None)
        n = collector.stale_check(FakeGH(None))
        dr = json.loads(town.get_item(Key={"pk": "TOUR#202", "sk": "DRAFT"})["Item"]["stops"])
        self.check("stale check marks changed stop", n == 1 and dr[0]["needs_look"])
        self.check("public tour keeps approved excerpt", "c.total * 1.09" in anon.get(f"/api/map/{slug}").get_data(as_text=True))
        d = o.post(f"/api/owner/townhall/tours/202/stops/{dr[0]['id']}/keep").get_json()
        self.check("keep as is clears it", d["stops"][0]["needs_look"] is None)
        n = collector.stale_check(FakeGH(None))
        self.check("kept stop not flagged again", n == 0)
        changed["client_acme/billing.py"] = ["def bill(c):", "    return c.total * 1.12"]
        self.check("further change flags again", collector.stale_check(FakeGH(None)) == 1)
        src = open(ROOT + "/source_map.py").read()
        self.check("public module still never reads the town table", "TOWN_TABLE" not in src)


if __name__ == "__main__":
    unittest.main()
