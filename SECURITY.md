# Security

## The owner-only area

Everything under `/api/admin/*`, the admin panel and the owner preview link is for the site owner only. There is one owner and no user accounts.

### Signing in
- Sign-in is a single passcode, stored as a hash (`ADMIN_PASSCODE_HASH`) or read from SSM Parameter Store as a SecureString.
- Once the owner has set up an authenticator app at `/owner/security`, sign-in takes the passcode and then a 6-digit code (RFC 6238, 30-second steps, one step of clock drift either way). The passcode alone only opens a five-minute window to enter the code; it starts no session.
- Each code works once: the last accepted time step is stored and anything at or before it is refused.
- Eight one-time recovery codes are shown once at setup. Only SHA-256 hashes of them are stored. A used one is removed.
- The authenticator secret is an SSM SecureString (`/ctrlaltjay/admin-totp-secret`). The app is the only thing that can read, write or delete it, and only that one parameter. While it's being set up, the not-yet-active secret sits in a table row for at most 10 minutes, tied to the session that started the setup.
- Replacing the authenticator, getting new recovery codes or turning the authenticator off needs a session that was itself signed in with a code, so a passcode alone can't change them. Turning it off also asks for a fresh code or recovery code, then deletes the SSM parameter and the stored recovery hashes.
- Recovery codes can be downloaded as a text file. The file is built in the browser from the codes already on screen, so they aren't sent a second time.
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

### Town hall (Commit City and Source Map)
- Town hall (`/owner/townhall` and `/api/owner/townhall/*`) checks the owner session on the server like Casebook: an empty 404 for anyone else, `no-store` and `noindex` on every response, its script and styles served from behind the check, disallowed in `robots.txt`, never in the sitemap. The Admin Tools link to it comes from an owner-only endpoint, so the address isn't in any public file.
- The GitHub token is read only by the collector's Lambda role. The app's role can't read it, and nothing the public site runs calls GitHub.
- The collector writes only to `ctrlaltjay-town`. Public pages will read only `ctrlaltjay-public-city`, which only an owner action in Town hall writes.
- Every repo the token can see starts hidden. Real repo names, branches and paths stay in `ctrlaltjay-town`.
- What reaches the public site, by mode:
  - **Hidden:** nothing, anywhere: not in `/api/city`, the page, the sitemap or as a count. The public snapshot is rebuilt from approved repos only.
  - **Public repo, approved:** the name (the owner's or the repo's), the description, weekly commit counts, language shares, code size in bytes, last push date, the archived flag, the GitHub link and a link to a live CtrlAltJay project page.
  - **Private repo, approved:** only a public name and description the owner writes, weekly commit counts, language shares, the last push date and a size class (one of four). No real name, owner, branch, file name, commit message, link, byte count or archived flag.
- `/api/city` is built field by field from an allow-list (`public_building` in `townhall.py`), so a new field in the owner-side data can't reach the public site by accident.
- Approving, moving to the drawer and changing an approved building's words each republish the snapshot at once; the daily collector never does. Every one of those actions is logged with its time in `ctrlaltjay-town` (`APPROVAL` rows) and shown in Town hall's approvals log.
- Tours are plotted only in Town hall, behind the same owner check. The browser sends a path and line numbers; the excerpt itself is copied on the server, through the collector, at a fixed commit. File paths are checked before the collector reads anything.
- Before an excerpt can be published it's checked for secrets: private keys, AWS, GitHub, Slack, Stripe, Google and Claude or OpenAI key formats, JSON web tokens, links with passwords, passwords and tokens assigned in code, .env lines, private addresses, email addresses and random-looking strings. A finding blocks publishing until the lines change or the owner marks it as not a secret, which goes in the approvals log. Findings record the line and kind only, never the value. Excerpts are capped at 40 lines and keep the commit they came from.
- A private repo's public tour carries the owner's district names, stop titles, explanations and approved excerpts only: no real name, path, file name, branch, commit or link. District sizes are published as shares, not bytes.
- Putting a repo in the drawer deletes its public tour along with its building.
- `/api/map/<slug>` serves only published tour rows from `ctrlaltjay-public-city` (or the built-in sample); it never reads `ctrlaltjay-town`, so a tour still being plotted can't be fetched by guessing its name. Slugs are checked against a strict pattern before any lookup.
- The owner-only building preview (`/owner/townhall/preview/<id>`) renders the public page template against an owner-only endpoint, so it shows exactly what would publish without publishing it.

### How the origin is protected
- The only public way in is CloudFront. The Lambda function URL refuses any request without the header CloudFront adds, so the app cannot be reached around it.
- While the site is switched off, a CloudFront Function answers every request with a holding page before anything reaches the app. The owner preview link lets one browser through with a cookie matching a secret in a CloudFront KeyValueStore; minting a new link revokes the old one. The admin panel still needs the passcode.

### Secrets
Secrets live in SSM Parameter Store as SecureStrings and are read by the app's Lambda role at start-up. None are kept in the repository, its docs or its Actions logs.

## Reporting a problem

If you find a security issue, please use the contact form on the site rather than opening a public issue. Include what you found and how to reproduce it.
