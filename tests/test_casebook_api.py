"""Casebook API and screens: owner-only routes, private headers, posting text never stored.

Runs in its own process with AWS faked by moto; see tests/run_all.py.
"""
import os, sys, json
import unittest
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from checks import Checks
os.environ.update(AWS_DEFAULT_REGION="ap-southeast-1", AWS_ACCESS_KEY_ID="x", AWS_SECRET_ACCESS_KEY="x",
                  SECRET_KEY="test-secret-key-0123456789abcdefghijkl", ADMIN_PASSCODE="right-passcode", FLASK_DEBUG="1")
from moto import mock_aws
mock_aws().start()
import boto3
ddb = boto3.resource("dynamodb", region_name="ap-southeast-1")
for name in ("ctrlaltjay-portfolio-items", "ctrlaltjay-resume-items", "ctrlaltjay-skills", "ctrlaltjay-stories"):
    ddb.create_table(TableName=name, KeySchema=[{"AttributeName": "id", "KeyType": "HASH"}],
        AttributeDefinitions=[{"AttributeName": "id", "AttributeType": "S"}], BillingMode="PAY_PER_REQUEST")
ddb.create_table(TableName="ctrlaltjay-casebooks", KeySchema=[{"AttributeName": "pk", "KeyType": "HASH"}, {"AttributeName": "sk", "KeyType": "RANGE"}],
    AttributeDefinitions=[{"AttributeName": "pk", "AttributeType": "S"}, {"AttributeName": "sk", "AttributeType": "S"}], BillingMode="PAY_PER_REQUEST")
ddb.Table("ctrlaltjay-portfolio-items").put_item(Item={"id": "p1", "section": "project", "title": "Public item", "category": "AI / ML"})
sys.path.insert(0, ROOT)
import app as appmod
app = appmod.app


class CasebookApi(Checks):
    def test_flow(self):

        anon = app.test_client()
        routes = [("GET", "/api/owner/casebooks"), ("POST", "/api/owner/casebooks"), ("GET", "/api/owner/casebooks/abcdef123456"),
                  ("PATCH", "/api/owner/casebooks/abcdef123456"), ("DELETE", "/api/owner/casebooks/abcdef123456"),
                  ("GET", "/api/owner/stories"), ("POST", "/api/owner/stories"), ("PUT", "/api/owner/stories/abcdef123456"),
                  ("DELETE", "/api/owner/stories/abcdef123456"), ("GET", "/api/owner/casebook/options")]
        out = [anon.open(path, method=m, json={"occasion": "interview", "organisation": "X"}) for m, path in routes]
        self.check("signed out: all 10 routes 404", all(r.status_code == 404 for r in out))
        self.check("signed out: no casebook data in any body", all(b"organisation" not in r.data and b"CASE#" not in r.data for r in out))
        self.check("signed out: same 404 as a route that doesn't exist", out[0].data == anon.get("/api/owner/nonexistent-route").data or out[0].status_code == anon.get("/no-such-page-xyz").status_code)
        self.check("signed out: no-store + noindex on the 404", all("no-store" in r.headers.get("Cache-Control", "") and "noindex" in r.headers.get("X-Robots-Tag", "") for r in out))

        o = app.test_client(); o.post("/admin/auth", json={"passcode": "right-passcode"})
        r = o.post("/api/owner/casebooks", json={"occasion": "interview", "organisation": "Accenture", "role": "Technology Analyst Intern",
            "date": "2026-12-03", "format": "video", "posting_url": "https://example.com/job", "notes": "They said there'll be a case study.",
            "posting_text": "FULL POSTING TEXT THAT MUST NOT BE STORED"})
        cb = r.get_json()
        self.check("create: 201", r.status_code == 201)
        self.check("create: posting text not stored, flag set", "posting_text" not in cb and cb["posting_provided"] is True)
        self.check("create: headers no-store + noindex", "no-store" in r.headers["Cache-Control"] and "noindex" in r.headers["X-Robots-Tag"])
        raw = json.dumps(ddb.Table("ctrlaltjay-casebooks").scan()["Items"], default=str)
        self.check("create: posting text absent from the table", "MUST NOT BE STORED" not in raw)
        self.check("validation: bad occasion/date/url rejected", o.post("/api/owner/casebooks", json={"occasion": "party", "organisation": "", "date": "3 Dec", "posting_url": "ftp://x"}).get_json()["fields"] == ["occasion", "organisation", "date", "posting_url"])
        self.check("list: one casebook", [c["organisation"] for c in o.get("/api/owner/casebooks").get_json()] == ["Accenture"])
        g = o.get(f"/api/owner/casebooks/{cb['id']}").get_json()
        self.check("get: meta + empty sections", g["casebook"]["role"] == "Technology Analyst Intern" and g["questions"] == [] and g["competencies"])
        p = o.patch(f"/api/owner/casebooks/{cb['id']}", json={"format": "panel", "notes": "Panel of three."}).get_json()
        self.check("patch: fields updated", p["format"] == "panel" and p["notes"] == "Panel of three." and p["organisation"] == "Accenture")
        self.check("patch: bad id shape 404", o.get("/api/owner/casebooks/../../etc").status_code == 404)
        s = o.post("/api/owner/stories", json={"title": "Shangri-La automation", "situation": "Finance team retyped Excel forms.", "result": "", "skills": ["Power Automate / Zapier"], "item_ids": ["p1"]})
        st = s.get_json()
        self.check("story: created", s.status_code == 201 and st["skills"] == ["Power Automate / Zapier"])
        self.check("story: title required", o.post("/api/owner/stories", json={"title": ""}).status_code == 400)
        u = o.put(f"/api/owner/stories/{st['id']}", json={"title": "Shangri-La automation", "result": "[your result here]"}).get_json()
        self.check("story: updated", u["result"] == "[your result here]")
        self.check("story: deleted", o.delete(f"/api/owner/stories/{st['id']}").status_code == 200 and o.get("/api/owner/stories").get_json() == [])
        self.check("casebook: deleted with its rows", o.delete(f"/api/owner/casebooks/{cb['id']}").status_code == 200 and ddb.Table("ctrlaltjay-casebooks").scan()["Count"] == 0)
        self.check("public table: only the original item besides session rows", [i["id"] for i in ddb.Table("ctrlaltjay-portfolio-items").scan()["Items"] if not i["id"].startswith("__")] == ["p1"])
        rb = anon.get("/robots.txt").data.decode()
        self.check("robots disallows owner paths", "Disallow: /api/owner/" in rb and "Disallow: /owner/" in rb)
        self.check("sitemap has no owner paths", b"owner" not in anon.get("/sitemap.xml").data)
        o.post("/admin/logout")
        self.check("after sign-out: routes 404 again", o.get("/api/owner/casebooks").status_code == 404)

        # step 3 screens
        o = app.test_client(); o.post("/admin/auth", json={"passcode": "right-passcode"})
        for path in ("/owner/casebook", "/owner/casebook/app.js", "/owner/casebook/app.css", "/api/owner/casebooks/sample"):
            r = anon.get(path)
            self.check("signed out 404: " + path, r.status_code == 404 and b"Casebook" not in r.data and b"Accenture" not in r.data)
        for path in ("/owner/casebook", "/owner/casebook/app.js", "/owner/casebook/app.css", "/api/owner/casebooks/sample"):
            r = o.get(path)
            self.check("owner 200 + private headers: " + path, r.status_code == 200 and "no-store" in r.headers["Cache-Control"] and "noindex" in r.headers["X-Robots-Tag"])
        self.check("asset whitelist: other files 404", o.get("/owner/casebook/..%2Fapp.py").status_code == 404 and o.get("/owner/casebook/research.py").status_code == 404)
        self.check("js content type", o.get("/owner/casebook/app.js").headers["Content-Type"].startswith("text/javascript"))
        self.check("sample marked", o.get("/api/owner/casebooks/sample").get_json()["casebook"]["sample"] is True)
        self.check("robots disallows /owner/", b"Disallow: /owner/" in anon.get("/robots.txt").data)
        sm = anon.get("/sitemap.xml").data
        self.check("sitemap has no owner routes", b"/owner" not in sm and b"casebook" not in sm.lower())


if __name__ == "__main__":
    unittest.main()
