# Security

## The owner-only area

Everything under `/api/admin/*`, the admin panel and the owner preview link is for the site owner only. There is one owner and no user accounts.

### Signing in
- Sign-in is a single passcode, stored as a hash (`ADMIN_PASSCODE_HASH`) or read from SSM Parameter Store as a SecureString.
- Once the owner has set up an authenticator app at `/owner/security`, sign-in takes the passcode and then a 6-digit code (RFC 6238, 30-second steps, one step of clock drift either way). The passcode alone only opens a five-minute window to enter the code; it starts no session.
- Each code works once: the last accepted time step is stored and anything at or before it is refused.
- Eight one-time recovery codes are shown once at setup. Only SHA-256 hashes of them are stored. A used one is removed.
- The authenticator secret is an SSM SecureString (`/ctrlaltjay/admin-totp-secret`). The app is the only thing that can read or write it, and only that one parameter. While it's being set up, the not-yet-active secret sits in a table row for at most 10 minutes, tied to the session that started the setup.
- Replacing the authenticator or getting new recovery codes needs a session that was itself signed in with a code, so a passcode alone can't change them.
- Wrong passcodes and wrong codes count towards the same limit: five from one address lock it out for 10 minutes.
- If the authenticator is lost along with every recovery code, deleting the SSM parameter in the AWS console turns the code step off, and sign-in goes back to the passcode alone until a new authenticator is set up.

### Sessions
- A successful sign-in creates a random session ID. The browser holds it in a signed, `HttpOnly`, `Secure`, `SameSite=Lax` cookie; the server keeps a row for it, stored only as a SHA-256 hash.
- Every owner request checks that the row still exists and that the session is younger than `ADMIN_SESSION_HOURS` (default 12). Either check failing ends the session and removes its row.
- Once an authenticator is set up, sessions that were started with the passcode alone stop counting. Each app instance re-checks whether one is set up at most once a minute, so this can take up to a minute.
- Signing out deletes the row, so a copied cookie stops working at the same moment.
- Rotating `SECRET_KEY` signs every session out.

### Casebook
- Every Casebook route checks the owner session on the server, and anyone else gets an empty 404, the same as for a route that doesn't exist. That includes the page itself and its script and styles, which are not in the public `/static` folder.
- Responses are `no-store` and `noindex`, and CloudFront's default behaviour doesn't cache app routes. The paths are disallowed in `robots.txt` and never appear in the sitemap or on any public page.
- Casebook data is in its own encrypted tables with point-in-time recovery. Casebook only scans the public tables to match evidence and never writes to them.
- Its Claude API key is a separate SecureString that only the research function's role can read; the main app cannot.
- Pasted job postings are passed to a research run in the invocation payload and never written to a table. A casebook keeps a short summary in plain words, the link, and at most a short phrase quoted from a requirement.
- Research stores sources as title, link, date and a short note. Text cited from sources is not stored.
- Starting research is an owner-only route; a run can only spend up to the per-run and monthly caps, and a retried invocation is refused so it can't charge twice.

### How the origin is protected
- The only public way in is CloudFront. The Lambda function URL refuses any request without the header CloudFront adds, so the app cannot be reached around it.
- While the site is switched off, a CloudFront Function answers every request with a holding page before anything reaches the app. The owner preview link lets one browser through with a cookie matching a secret in a CloudFront KeyValueStore; minting a new link revokes the old one. The admin panel still needs the passcode.

### Secrets
Secrets live in SSM Parameter Store as SecureStrings and are read by the app's Lambda role at start-up. None are kept in the repository, its docs or its Actions logs.

## Reporting a problem

If you find a security issue, please use the contact form on the site rather than opening a public issue. Include what you found and how to reproduce it.
