"""Authenticator app codes: setup, sign-in, recovery codes, replay and turning it off.

Runs in its own process with AWS faked by moto; see tests/run_all.py.
"""
import os, sys, json, time
import unittest
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from checks import Checks
os.environ.update(AWS_DEFAULT_REGION="ap-southeast-1", AWS_ACCESS_KEY_ID="x", AWS_SECRET_ACCESS_KEY="x",
                  SECRET_KEY="test-secret-key-0123456789abcdefghijkl", ADMIN_PASSCODE="right-passcode", ADMIN_TOTP_SSM_PARAM="/ctrlaltjay/admin-totp-secret")
from moto import mock_aws
mock_aws().start()
import boto3
ddb = boto3.resource("dynamodb", region_name="ap-southeast-1")
for name in ("ctrlaltjay-portfolio-items", "ctrlaltjay-resume-items", "ctrlaltjay-skills", "ctrlaltjay-stories"):
    ddb.create_table(TableName=name, KeySchema=[{"AttributeName": "id", "KeyType": "HASH"}], AttributeDefinitions=[{"AttributeName": "id", "AttributeType": "S"}], BillingMode="PAY_PER_REQUEST")
ddb.create_table(TableName="ctrlaltjay-casebooks", KeySchema=[{"AttributeName": "pk", "KeyType": "HASH"}, {"AttributeName": "sk", "KeyType": "RANGE"}],
    AttributeDefinitions=[{"AttributeName": "pk", "AttributeType": "S"}, {"AttributeName": "sk", "AttributeType": "S"}], BillingMode="PAY_PER_REQUEST")
sys.path.insert(0, ROOT)
import app as appmod, owner_totp
ssm = boto3.client("ssm", region_name="ap-southeast-1")
app = appmod.app


class AuthenticatorSignIn(Checks):
    def test_flow(self):
        def code(secret, offset=0): return owner_totp.code_at(secret, int(time.time() // 30) + offset)
        def signed_in(c): return c.get("/api/admin/auth-status").get_json().get("is_admin")

        anon = app.test_client()
        for m, p in [("GET", "/owner/security"), ("GET", "/api/owner/security"), ("POST", "/api/owner/security/start"), ("POST", "/api/owner/security/confirm"), ("POST", "/api/owner/security/recovery")]:
            self.check(f"signed out 404 {m} {p}", anon.open(p, method=m, json={}).status_code == 404)
        self.check("robots covers /owner/", b"Disallow: /owner/" in anon.get("/robots.txt").data)

        # before setup: passcode alone works, as today
        a = app.test_client()
        r = a.post("/admin/auth", json={"passcode": "right-passcode"})
        self.check("not set up: passcode signs in", r.status_code == 200 and "needs_code" not in r.get_json() and signed_in(a))
        r = a.get("/owner/security")
        self.check("setup page owner-only, no-store, noindex", r.status_code == 200 and "no-store" in r.headers["Cache-Control"] and "noindex" in r.headers["X-Robots-Tag"])
        s = a.get("/api/owner/security").get_json()
        self.check("status: not enrolled", s == {"enrolled": False, "recovery_left": 0, "this_session_used_code": False})
        st = a.post("/api/owner/security/start").get_json()
        secret = st["key"].replace(" ", "")
        self.check("start gives QR svg and key", st["qr_svg"].startswith("<svg") and len(secret) == 32)
        self.check("secret not in SSM before confirm", "Parameters" in ssm.describe_parameters() and not ssm.describe_parameters()["Parameters"])
        self.check("wrong code refused", a.post("/api/owner/security/confirm", json={"code": "000000" if code(secret) != "000000" else "111111"}).status_code == 400)
        other = app.test_client(); other.post("/admin/auth", json={"passcode": "right-passcode"})
        self.check("another session can't confirm this setup", other.post("/api/owner/security/confirm", json={"code": code(secret)}).status_code == 400)
        r = a.post("/api/owner/security/confirm", json={"code": code(secret)})
        codes = r.get_json()["recovery_codes"]
        self.check("confirm: 8 recovery codes", r.status_code == 200 and len(codes) == 8)
        p = ssm.get_parameter(Name="/ctrlaltjay/admin-totp-secret", WithDecryption=True)["Parameter"]
        tags = ssm.list_tags_for_resource(ResourceType="Parameter", ResourceId="/ctrlaltjay/admin-totp-secret")["TagList"]
        self.check("secret saved as SecureString, tagged", p["Type"] == "SecureString" and p["Value"] == secret and {"Key": "Project", "Value": "CtrlAltJay"} in tags)
        row = appmod.table_items.get_item(Key={"id": "__admintotp_state"})["Item"]
        self.check("only hashes of recovery codes stored", all(c not in json.dumps(row, default=str) for c in codes) and len(row["recovery"]) == 8)
        self.check("pending secret removed", "Item" not in appmod.table_items.get_item(Key={"id": "__admintotp_pending"}))
        self.check("setting-up session stays signed in", signed_in(a))
        owner_totp.forget_cache()
        self.check("old passcode-only session no longer counts", not signed_in(other) and other.get("/api/owner/casebooks").status_code == 404)

        # sign-in now needs both
        b = app.test_client()
        r = b.post("/admin/auth", json={"passcode": "right-passcode"})
        self.check("passcode alone: asks for code, not signed in", r.get_json() == {"needs_code": True} and not signed_in(b))
        self.check("passcode alone can't reach owner API", b.get("/api/owner/casebooks").status_code == 404)
        self.check("code without passcode step refused", app.test_client().post("/admin/auth/code", json={"code": code(secret)}).status_code == 401)
        self.check("wrong code refused", b.post("/admin/auth/code", json={"code": "123456" if code(secret) != "123456" else "654321"}).status_code == 401)
        self.check("same code that set it up can't be reused", b.post("/admin/auth/code", json={"code": code(secret)}).status_code == 401)
        # advance: use next step's code
        time_code = code(secret, 1)
        r = b.post("/admin/auth/code", json={"code": time_code})
        self.check("next valid code signs in", r.status_code == 200 and signed_in(b))
        c2 = app.test_client(); c2.post("/admin/auth", json={"passcode": "right-passcode"})
        self.check("a used code can't be replayed", c2.post("/admin/auth/code", json={"code": time_code}).status_code == 401 and not signed_in(c2))
        r = c2.post("/admin/auth/code", json={"code": codes[0].lower()})
        self.check("recovery code works (any case)", r.status_code == 200 and signed_in(c2))
        c3 = app.test_client(); c3.post("/admin/auth", json={"passcode": "right-passcode"})
        self.check("recovery code works only once", c3.post("/admin/auth/code", json={"code": codes[0]}).status_code == 401)
        self.check("recovery count drops", c2.get("/api/owner/security").get_json()["recovery_left"] == 7)
        self.check("recovery-code session can manage security", c2.get("/api/owner/security").get_json()["this_session_used_code"])
        # passcode-only after enrolment can't swap the authenticator
        self.check("can't start a new setup without a code session", other.post("/api/owner/security/start").status_code == 404)
        # lockout: wrong codes count towards the passcode lockout
        d = app.test_client(); d.environ_base = {"REMOTE_ADDR": "10.9.9.9"}
        d.post("/admin/auth", json={"passcode": "right-passcode"})
        statuses = [d.post("/admin/auth/code", json={"code": "999999" if code(secret) != "999999" else "888888"}).status_code for _ in range(6)]
        self.check(f"wrong codes lock out {statuses}", 429 in statuses)
        # expiry of the code window
        e = app.test_client(); e.post("/admin/auth", json={"passcode": "right-passcode"})
        with e.session_transaction() as sess: sess["admin_pending_at"] = int(time.time()) - 400
        r = e.post("/admin/auth/code", json={"code": code(secret, 1)})
        self.check("code window expires after 5 minutes", r.status_code == 401 and r.get_json().get("restart"))
        # new recovery codes
        r = c2.post("/api/owner/security/recovery")
        new = r.get_json()["recovery_codes"]
        self.check("new recovery codes replace old", r.status_code == 200 and c2.get("/api/owner/security").get_json()["recovery_left"] == 8)
        f = app.test_client(); f.post("/admin/auth", json={"passcode": "right-passcode"})
        self.check("old recovery code dead after renewal", f.post("/admin/auth/code", json={"code": codes[1]}).status_code == 401)
        # turning it off from the page
        other2 = app.test_client(); other2.post("/admin/auth", json={"passcode": "right-passcode"})
        self.check("passcode-only session can't turn it off", other2.post("/api/owner/security/remove", json={"code": code(secret, 2)}).status_code == 404)
        self.check("wrong code doesn't turn it off", c2.post("/api/owner/security/remove", json={"code": "000000" if code(secret, 2) != "000000" else "111111"}).status_code == 400)
        r = c2.post("/api/owner/security/remove", json={"code": new[0]})
        self.check("recovery code turns it off", r.status_code == 200)
        self.check("secret deleted from SSM", not ssm.describe_parameters()["Parameters"])
        self.check("state row with recovery hashes deleted", "Item" not in appmod.table_items.get_item(Key={"id": "__admintotp_state"}))
        k = app.test_client(); r = k.post("/admin/auth", json={"passcode": "right-passcode"})
        self.check("after turning off, passcode alone signs in", "needs_code" not in r.get_json() and signed_in(k))
        self.check("remove when not enrolled is refused", k.post("/api/owner/security/remove", json={"code": "123456"}).status_code == 403)
        # set it up again so the escape-hatch test below still has something to delete
        st = k.post("/api/owner/security/start").get_json(); secret = st["key"].replace(" ", "")
        k.post("/api/owner/security/confirm", json={"code": code(secret)})
        # escape hatch: deleting the parameter returns to passcode-only
        ssm.delete_parameter(Name="/ctrlaltjay/admin-totp-secret"); owner_totp.forget_cache()
        g = app.test_client(); r = g.post("/admin/auth", json={"passcode": "right-passcode"})
        self.check("deleting the parameter turns the code check off", "needs_code" not in r.get_json() and signed_in(g))
        h = app.test_client()
        self.check("tools list 404 signed out", h.get("/api/owner/tools").status_code == 404)
        h.post("/admin/auth", json={"passcode": "right-passcode"})
        t = h.get("/api/owner/tools")
        self.check("tools list for owner, no-store", t.status_code == 200 and [x["href"] for x in t.get_json()] == ["/owner/security", "/owner/casebook", "/owner/townhall"] and "no-store" in t.headers["Cache-Control"])
        page = app.test_client().get("/").data.decode()
        self.check("public page has no owner addresses", "/owner/security" not in page and "/owner/casebook" not in page)


if __name__ == "__main__":
    unittest.main()
