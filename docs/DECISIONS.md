# Decisions

Significant choices about how CtrlAltJay works, newest first, with what was considered and set aside.

## 19 Nov 2026: Owner sign-in stays a single passcode, with server-side sessions

**Decided:** keep the passcode as the only sign-in factor. Add a server-side session record so sessions expire (`ADMIN_SESSION_HOURS`, default 12) and signing out ends them everywhere.

**Why:** the owner chose not to add a passkey or second factor for now. Before this change a session lived only in a signed cookie with no expiry, so a copied cookie stayed valid until `SECRET_KEY` was rotated.

**Set aside:** a passkey (WebAuthn) as a required second step. It is the stronger option and can be added later without changing the session design.

**How:** each sign-in writes a row to `ctrlaltjay-portfolio-items` under a `__adminsession_` id, holding only a SHA-256 hash of the session ID. That table already holds the rate-limit rows, and every public read already skips `__` ids, so no new table or IAM change was needed.
