# Security

## The owner-only area

Everything under `/api/admin/*`, the admin panel and the owner preview link is for the site owner only. There is one owner and no user accounts.

### Signing in
- Sign-in is a single passcode, stored as a hash (`ADMIN_PASSCODE_HASH`) or read from SSM Parameter Store as a SecureString.
- Five wrong attempts from one address lock that address out for 10 minutes.
- There is no second factor. That was the owner's decision on 19 Nov 2026; see `docs/DECISIONS.md`.

### Sessions
- A successful sign-in creates a random session ID. The browser holds it in a signed, `HttpOnly`, `Secure`, `SameSite=Lax` cookie; the server keeps a row for it, stored only as a SHA-256 hash.
- Every owner request checks that the row still exists and that the session is younger than `ADMIN_SESSION_HOURS` (default 12). Either check failing ends the session and removes its row.
- Signing out deletes the row, so a copied cookie stops working at the same moment.
- Rotating `SECRET_KEY` signs every session out.

### How the origin is protected
- The only public way in is CloudFront. The Lambda function URL refuses any request without the header CloudFront adds, so the app cannot be reached around it.
- While the site is switched off, a CloudFront Function answers every request with a holding page before anything reaches the app. The owner preview link lets one browser through with a cookie matching a secret in a CloudFront KeyValueStore; minting a new link revokes the old one. The admin panel still needs the passcode.

### Secrets
Secrets live in SSM Parameter Store as SecureStrings and are read by the app's Lambda role at start-up. None are kept in the repository, its docs or its Actions logs.

## Reporting a problem

If you find a security issue, please use the contact form on the site rather than opening a public issue. Include what you found and how to reproduce it.
