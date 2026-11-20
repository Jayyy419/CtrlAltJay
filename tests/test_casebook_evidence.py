"""Casebook evidence matching, coverage, STAR outlines and the story bank.

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
    ddb.create_table(TableName=name, KeySchema=[{"AttributeName": "id", "KeyType": "HASH"}],
        AttributeDefinitions=[{"AttributeName": "id", "AttributeType": "S"}], BillingMode="PAY_PER_REQUEST")
ddb.create_table(TableName="ctrlaltjay-casebooks", KeySchema=[{"AttributeName": "pk", "KeyType": "HASH"}, {"AttributeName": "sk", "KeyType": "RANGE"}],
    AttributeDefinitions=[{"AttributeName": "pk", "AttributeType": "S"}, {"AttributeName": "sk", "AttributeType": "S"}], BillingMode="PAY_PER_REQUEST")
# Made-up portfolio rows, shaped like the real tables, so ranking can be checked.
ITEMS = [
    {"id": "yep1", "section": "experience", "title": "Youth Expedition Project: Thailand trip", "category": "Volunteering",
     "summary": "Two weeks in a Thailand village with a volunteer team, running sessions for children and helping the community build a classroom.",
     "description": "An overseas expedition: our team adapted to a new environment and difficult conditions, and worked with the host community across cultures.",
     "skills": "Teamwork,Communication"},
    {"id": "hall1", "section": "project", "title": "Hall Website", "category": "Web",
     "summary": "Built a website for a hall of residence club so residents could sign up for events.", "skills": "Python,Web Development"},
    {"id": "auto1", "section": "experience", "title": "Automation Intern", "category": "Internships",
     "summary": "Automated finance request forms so the team stopped retyping them by hand.", "skills": "Python,Process Automation"},
    {"id": "club1", "section": "experience", "title": "Club Treasurer", "category": "CCA",
     "summary": "Kept a student club's accounts and ran its yearly charity drive.", "skills": "Finance"},
]
RESUME = [{"id": "r1", "title": "Bachelor of Computing", "organisation": "A university", "summary": "Computer science degree."}]
for it in ITEMS: ddb.Table("ctrlaltjay-portfolio-items").put_item(Item=it)
for it in RESUME: ddb.Table("ctrlaltjay-resume-items").put_item(Item=it)
ddb.Table("ctrlaltjay-portfolio-items").put_item(Item={"id": "gone", "title": "Deleted team thing", "summary": "team", "deleted_at": "x"})
ddb.Table("ctrlaltjay-skills").put_item(Item={"id": "s1", "name": "Python"})
sys.path.insert(0, ROOT)
import app as appmod
app = appmod.app


class CasebookEvidence(Checks):
    def test_flow(self):
        def snap(): return json.dumps([[i for i in ddb.Table(t).scan()["Items"] if not i["id"].startswith("__")] for t in ("ctrlaltjay-portfolio-items", "ctrlaltjay-resume-items", "ctrlaltjay-skills")], default=str, sort_keys=True)
        before = snap()

        anon = app.test_client()
        for m, p in [("PUT", "/api/owner/casebooks/abcdef123456/coverage"), ("POST", "/api/owner/casebooks/abcdef123456/questions"),
                     ("PATCH", "/api/owner/casebooks/abcdef123456/questions/abcdef123456"), ("GET", "/api/owner/evidence/pool")]:
            r = anon.open(p, method=m, json={})
            self.check(f"signed out 404 {m} {p}", r.status_code == 404 and "no-store" in r.headers["Cache-Control"])

        o = app.test_client(); o.post("/admin/auth", json={"passcode": "right-passcode"})
        cid = o.post("/api/owner/casebooks", json={"occasion": "volunteering", "organisation": "YEP", "role": "Thailand trip"}).get_json()["id"]
        v = o.get(f"/api/owner/casebooks/{cid}").get_json()
        self.check("default competencies for volunteering", v["competencies"] == ["Why this cause", "Adaptability", "Teamwork across cultures", "Handling hardship", "Community"])
        self.check("evidence ranked, YEP first", v["evidence"][0]["title"].startswith("Youth Expedition Project"))
        self.check("each match says why", all(e["why"] and all(e["why"].values()) for e in v["evidence"]))
        self.check("deleted items never appear", all("Deleted" not in e["title"] for e in v["evidence"]))
        self.check("no questions yet", v["questions"] == [])

        r = o.post(f"/api/owner/casebooks/{cid}/questions", json={"usual": True})
        self.check("usual questions added", r.status_code == 201 and r.get_json()["added"] == 5)
        r = o.post(f"/api/owner/casebooks/{cid}/questions", json={"usual": True})
        self.check("usual not duplicated", r.get_json()["added"] == 0)
        r = o.post(f"/api/owner/casebooks/{cid}/questions", json={"text": "What will you do if you get sick?", "kind": "hardship"})
        self.check("own question added", r.status_code == 201)
        self.check("blank question rejected", o.post(f"/api/owner/casebooks/{cid}/questions", json={"text": " ", "kind": "hardship"}).status_code == 400)
        v = o.get(f"/api/owner/casebooks/{cid}").get_json()
        qs = v["questions"]
        self.check("6 questions in order", len(qs) == 6 and qs[0]["text"].startswith("Why this cause") and qs[-1]["provenance"] == "own")
        self.check("usual labelled usual", all(q["provenance"] == "usual" for q in qs[:5]))
        self.check("questions get evidence", all(q["evidence"] for q in qs[:5]))
        self.check("result never filled from items", all(q["star"]["result"] == "" for q in qs if q["star"] and q["evidence"] and q["evidence"][0]["type"] != "story"))
        yep = [e for e in v["evidence"] if e["title"].startswith("Youth Expedition")][0]
        star_src = [q["star"] for q in qs if q["evidence"] and q["evidence"][0]["ref"] == yep["ref"] and q["star"]]
        self.check("star situation comes from stored summary", star_src and star_src[0]["situation"] and star_src[0]["from"].get("situation") in ("summary", "description"))

        # coverage overrides
        ref = v["evidence"][1]["ref"]; comp = v["competencies"][1]
        was = comp in v["evidence"][1]["covers"]
        r = o.put(f"/api/owner/casebooks/{cid}/coverage", json={"ref": ref, "competency": comp, "covers": not was})
        v2 = o.get(f"/api/owner/casebooks/{cid}").get_json()
        row = [e for e in v2["evidence"] if e["ref"] == ref]
        self.check("override flips a cell", r.status_code == 200 and (not row and was) or (row and (comp in row[0]["covers"]) == (not was) and comp in row[0]["overridden"]))
        o.put(f"/api/owner/casebooks/{cid}/coverage", json={"ref": ref, "competency": comp, "covers": None})
        o.put(f"/api/owner/casebooks/{cid}/coverage", json={"ref": ref, "hidden": True})
        v3 = o.get(f"/api/owner/casebooks/{cid}").get_json()
        self.check("left-out item disappears and is listed", all(e["ref"] != ref for e in v3["evidence"]) and v3["hidden"][0]["ref"] == ref)
        o.put(f"/api/owner/casebooks/{cid}/coverage", json={"ref": ref, "hidden": False})
        self.check("bad ref rejected", o.put(f"/api/owner/casebooks/{cid}/coverage", json={"ref": "item:nope", "competency": comp, "covers": True}).status_code == 400)
        self.check("bad competency rejected", o.put(f"/api/owner/casebooks/{cid}/coverage", json={"ref": ref, "competency": "Juggling", "covers": True}).status_code == 400)

        # competencies editing
        r = o.patch(f"/api/owner/casebooks/{cid}", json={"competencies": ["Community", "community", "Python", " "]})
        v4 = o.get(f"/api/owner/casebooks/{cid}").get_json()
        self.check("competencies deduped and saved", v4["competencies"] == ["Community", "Python"])
        self.check("missing competency becomes a loose end or is covered", any("Python" in e["covers"] for e in v4["evidence"]) or any("Python" in l["text"] for l in v4["loose_ends"]))
        o.patch(f"/api/owner/casebooks/{cid}", json={"competencies": ["Community", "Underwater welding"]})
        v5 = o.get(f"/api/owner/casebooks/{cid}").get_json()
        self.check("uncovered competency is a loose end", any(l["kind"] == "skill" and "Underwater welding" in l["text"] for l in v5["loose_ends"]))

        # stories
        item_id = yep["ref"].split(":")[1]
        st = o.post("/api/owner/stories", json={"title": "YEP Thailand", "situation": "Two weeks in a village.", "task": "", "action": "Ran the kids' sessions.", "result": "", "item_ids": [item_id], "skills": []}).get_json()
        qid = qs[1]["id"]
        r = o.patch(f"/api/owner/casebooks/{cid}/questions/{qid}", json={"story_id": st["id"]})
        v6 = o.get(f"/api/owner/casebooks/{cid}").get_json()
        q = [x for x in v6["questions"] if x["id"] == qid][0]
        self.check("story becomes lead evidence", q["evidence"][0]["ref"] == "story:" + st["id"])
        self.check("story STAR used verbatim with gaps", q["star"]["situation"] == "Two weeks in a village." and q["star"]["task"] == "" and q["star"]["result"] == "")
        self.check("unfinished story is a loose end", any(l["kind"] == "story" and "task, result" in l["text"] for l in v6["loose_ends"]))
        stories = o.get("/api/owner/stories").get_json()
        self.check("story shows where it's used", stories[0]["used_in"] == [{"id": cid, "title": "YEP: Thailand trip"}])
        r = o.patch(f"/api/owner/casebooks/{cid}/questions/{qid}", json={"evidence_refs": ["item:nope"]})
        self.check("bad evidence ref rejected", r.status_code == 400)
        o.delete(f"/api/owner/stories/{st['id']}")
        v7 = o.get(f"/api/owner/casebooks/{cid}").get_json()
        q = [x for x in v7["questions"] if x["id"] == qid][0]
        self.check("deleting a story unlinks it", q["story_id"] == "" and q["evidence"] and q["evidence"][0]["type"] != "story")
        self.check("question delete", o.delete(f"/api/owner/casebooks/{cid}/questions/{qid}").status_code == 200 and len(o.get(f"/api/owner/casebooks/{cid}").get_json()["questions"]) == 5)
        pool = o.get("/api/owner/evidence/pool").get_json()
        self.check("pool lists items and skills", len(pool["items"]) == len(ITEMS) + len(RESUME) and pool["skills"] == ["Python"])
        self.check("public tables unchanged", snap() == before)


if __name__ == "__main__":
    unittest.main()
