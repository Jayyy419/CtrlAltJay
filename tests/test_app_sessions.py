"""Owner sessions: sign-in, sign-out, expiry and copied cookies.

Runs in its own process with AWS faked by moto; see tests/run_all.py.
"""
import os, sys, time
import unittest
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from checks import Checks
os.environ.update(AWS_DEFAULT_REGION="ap-southeast-1", AWS_ACCESS_KEY_ID="x", AWS_SECRET_ACCESS_KEY="x",
                  SECRET_KEY="test-secret-key-0123456789abcdefghijkl", ADMIN_PASSCODE="right-passcode",
                  FLASK_DEBUG="1", ADMIN_SESSION_HOURS="12")
from moto import mock_aws
mock = mock_aws(); mock.start()
import boto3
ddb = boto3.resource("dynamodb", region_name="ap-southeast-1")
for name in ("ctrlaltjay-portfolio-items", "ctrlaltjay-resume-items", "ctrlaltjay-skills"):
    ddb.create_table(TableName=name, KeySchema=[{"AttributeName": "id", "KeyType": "HASH"}],
                     AttributeDefinitions=[{"AttributeName": "id", "AttributeType": "S"}], BillingMode="PAY_PER_REQUEST")
sys.path.insert(0, ROOT)
import app as appmod
app = appmod.app
items = ddb.Table("ctrlaltjay-portfolio-items")
def rows(): return [i for i in items.scan()["Items"] if i["id"].startswith("__adminsession_")]
def status(c): return c.get("/api/admin/auth-status").get_json()["is_admin"]
def admin_get(c): return c.get("/api/admin/skills").status_code



class OwnerSessions(Checks):
    def test_flow(self):

        a = app.test_client()
        self.check("signed out: owner API denied (403)", admin_get(a) == 403)
        self.check("wrong passcode rejected", a.post("/admin/auth", json={"passcode": "nope"}).status_code == 401)
        self.check("right passcode accepted", a.post("/admin/auth", json={"passcode": "right-passcode"}).status_code == 200)
        self.check("one server-side session row, hashed id", len(rows()) == 1 and "right" not in rows()[0]["id"])
        self.check("signed in: owner API allowed (200)", admin_get(a) == 200 and status(a) is True)
        cookie = a.get_cookie("session")
        self.check("cookie is persistent with an expiry", cookie is not None and cookie.expires is not None)

        # copy the cookie into a second "browser", then sign out of the first
        b = app.test_client(); b.set_cookie("session", cookie.value)
        self.check("copied cookie works before sign-out", admin_get(b) == 200)
        a.post("/admin/logout")
        self.check("sign-out deletes the server row", len(rows()) == 0)
        self.check("signed-out browser denied", admin_get(a) == 403)
        self.check("copied cookie denied after sign-out", admin_get(b) == 403 and status(b) is False)

        # expiry: sign in, then age the session past the limit
        c = app.test_client(); c.post("/admin/auth", json={"passcode": "right-passcode"})
        with c.session_transaction() as s: s["admin_at"] = int(time.time()) - appmod.ADMIN_SESSION_SECONDS - 5
        self.check("session older than the limit denied", admin_get(c) == 403)
        self.check("aged-out session's server row removed", len(rows()) == 0)
        d = app.test_client(); d.post("/admin/auth", json={"passcode": "right-passcode"})
        for r in rows(): items.update_item(Key={"id": r["id"]}, UpdateExpression="SET expires_at = :e", ExpressionAttributeValues={":e": 1})
        self.check("server row past expires_at denied and removed", admin_get(d) == 403 and len(rows()) == 0)
        # old-style cookie (is_admin only, from before this change) no longer works
        e = app.test_client()
        with e.session_transaction() as s: s["is_admin"] = True
        self.check("pre-change is_admin-only cookie denied", admin_get(e) == 403)
        self.check("public data still served signed out", app.test_client().get("/api/public-data").status_code == 200)


if __name__ == "__main__":
    unittest.main()
