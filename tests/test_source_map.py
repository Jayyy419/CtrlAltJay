"""The public Source Map pages and API.

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
sys.path.insert(0, ROOT)
import app as appmod
c = appmod.app.test_client()


class SourceMap(Checks):
    def test_flow(self):

        r = c.get("/api/map/sample"); d = r.get_json()
        self.check("sample tour served", r.status_code == 200 and d["sample"] and len(d["stops"]) == 8)
        self.check("sample is cacheable", "max-age=300" in r.headers["Cache-Control"])
        self.check("every excerpt within 40 lines", all(len(s["excerpt"]["lines"]) <= 40 for s in d["stops"]))
        self.check("marks inside each excerpt", all(s["excerpt"]["start"] <= s["excerpt"]["mark"][0] <= s["excerpt"]["mark"][1] < s["excerpt"]["start"] + len(s["excerpt"]["lines"]) for s in d["stops"]))
        r = c.get("/map/sample"); h = r.get_data(as_text=True)
        self.check("page renders", r.status_code == 200 and 'data-stop="1"' in h)
        self.check("sample is noindex", "noindex" in h)
        self.check("stop 8 renders", c.get("/map/sample/8").status_code == 200)
        for p in ("/map/sample/0", "/map/sample/9", "/map/nothing-here", "/api/map/nothing-here", "/map/Bad_Slug", "/api/map/..%2Fx"):
            self.check(f"404 {p}", c.get(p).status_code == 404)

        # A published tour comes only from the public table.
        tour = dict(appmod.source_map.SAMPLE_TOUR if hasattr(appmod, "source_map") else __import__("source_map").SAMPLE_TOUR)
        tour.update(sample=False, slug="real-one", title="A real tour")
        ddb.Table("ctrlaltjay-town").put_item(Item={"pk": "TOUR#owner-only", "sk": "CURRENT", "data": json.dumps(tour)})
        self.check("owner-side rows never served", c.get("/api/map/owner-only").status_code == 404)
        ddb.Table("ctrlaltjay-public-city").put_item(Item={"pk": "TOUR#real-one", "sk": "CURRENT", "data": json.dumps(tour)})
        r = c.get("/api/map/real-one")
        self.check("published tour served", r.status_code == 200 and r.get_json()["title"] == "A real tour")
        h = c.get("/map/real-one/2").get_data(as_text=True)
        self.check("published tour is indexable", "noindex" not in h)
        self.check("sitemap has no map routes yet", "/map/" not in c.get("/sitemap.xml").get_data(as_text=True))
        src = open(ROOT + "/source_map.py").read()
        self.check("public module never touches the town table or GitHub", "TOWN_TABLE" not in src and "ctrlaltjay-town\"" not in src and "api.github.com" not in src)


if __name__ == "__main__":
    unittest.main()
