"""The secret check that guards Source Map excerpts."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from secret_scan import scan_lines  # noqa: E402

# Built from parts so this file never holds a whole key-shaped string.
FAKE_AWS = "AKIA" + "Q" * 4 + "7" * 4 + "ZXCVBNMA"
FAKE_GH = "ghp_" + "a1B2" * 9
FAKE_JWT = "eyJhbGciOiJIUzI1NiJ9" + ".eyJzdWIiOiIxMjM0NTY3ODkwIn0" + ".dozjgNryP4J3jVmNHl0w5N_XgL0n3I9PlFUP0THsR8U"

CASES = [
    ('key = "%s"' % FAKE_AWS, "AWS access key"),
    ("token = '%s'" % FAKE_GH, "GitHub token"),
    ("DB_PASSWORD=hunter2hunter", ".env line"),
    ('password = "s3cretValue"', "Password or secret in the code"),
    ('password = os.environ["PW"]', None),
    ("API_KEY=changeme", None),
    ('url = "postgres://user:pa55word@db.host/x"', "Link with a password"),
    ('host = "10.0.4.12"', "Private address"),
    ('host = "api.corp"', "Private address"),
    ('contact = "someone@gmail.com"', "Email address"),
    ('contact = "me@example.com"', None),
    ('blob = "Zx8Qp2LmN7vR4tK9wB3yH6jD1sF5gA0c"', "Random-looking string"),
    ("def route_ping(ping, registry):", None),
    ("    bot = registry.get(ping.bot_id)", None),
    ('import { createApplicationRouterInstance } from "./router";', None),
    ("DEBUG=true", None),
    ("PORT=8080", None),
    ("-----BEGIN RSA PRIVATE KEY-----", "Private key"),
    ('x = "%s"' % FAKE_JWT, "JSON web token"),
]


class SecretScan(unittest.TestCase):
    def test_cases(self):
        for line, want in CASES:
            with self.subTest(line[:40]):
                found = scan_lines([line])
                self.assertEqual(found[0]["kind"] if found else None, want)

    def test_line_numbers_follow_the_excerpt(self):
        found = scan_lines(["a = 1", "b = 2", 'pw = "%s"' % FAKE_GH], start=40)
        self.assertEqual(found, [{"line": 42, "kind": "GitHub token"}])

    def test_findings_never_hold_the_value(self):
        found = scan_lines(['token = "%s"' % FAKE_GH])
        self.assertNotIn(FAKE_GH, repr(found))


if __name__ == "__main__":
    unittest.main()
