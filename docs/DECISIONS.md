# Decisions

Significant choices about how CtrlAltJay works, newest first, with what was considered and set aside.

## 19 Nov 2026: Casebook research runs in two passes and checks its own labels

**Decided:**
- Research runs on Claude Opus 5.5 with the `web_search_20260318` tool. Model and caps are stack parameters: US$3 per run, US$10 per month, 25 searches per run. The owner chose these on 19 Nov 2026, expecting about three researched cases a month.
- Pass one searches and takes notes; pass two turns the notes into JSON against a schema. One pass with structured output would also carry the search results and citations, and splitting keeps each request simple.
- Provenance labels are enforced in code after the model replies, not left to the prompt.
- Sources are stored as title, link, the page's own date and a few words on what they support. Cited text from sources is never stored. Pasted posting text travels only in the invocation payload.
- Spend is tracked from each response's usage at configured prices, per case and in a monthly row.
- No refusal fallback to another model. Cost tracking assumes one model's prices, and a declined run stops, is marked failed and records what it cost.

**Why:**
- The spec says never to claim an organisation asks something without a source; a check in code holds even when the model gets it wrong.
- Async Lambda invocations can be retried; claiming the run first means a retry can't double the bill.

**Set aside:**
- Sonnet 5.5 at about half the token cost. The owner preferred quality over price.
- Server-side refusal fallbacks (see above).

## 19 Nov 2026: Casebook evidence is worked out on read, from keywords

**Decided:**
- Matching uses a fixed keyword list per competency (and the words themselves for anything the owner adds), run over the stored text of items, resume rows and stories. Each match records which word in which field triggered it.
- Evidence, coverage and STAR outlines are computed on every read. Only the owner's choices are stored: corrections to the grid and left-out items on `META`, chosen evidence and a linked story on each `Q#` row. The planned `EV#` rows were dropped.
- Outlines copy stored fields as they are. The result is never filled from an item, only from a story the owner writes.
- Questions added before research are either the usual ones for the occasion (a fixed list, labelled "Usual for this kind of role") or the owner's own, which carry a fourth label, "Added by you".

**Why:**
- Only 25 of the 119 items carry skill tags, so tags alone would miss most of the evidence. Text matching with a visible reason is easy to check and correct, and costs nothing per use.
- Computing on read means an edit to a portfolio item shows up in every case straight away.

**Set aside:**
- Asking the Claude API to do the matching. It costs money on every view and its reasons are harder to check. Research in step 5 may still suggest what a case looks for.

## 19 Nov 2026: Casebook gets its own tables, function and key

**Decided:**
- `ctrlaltjay-casebooks` uses one partition per casebook, with sort keys `META`, `SRC#`, `Q#` and `EV#`. One query loads a whole casebook, and deleting one is a single partition.
- Stories get their own table, because they outlive any one casebook.
- Research runs in a separate Lambda function with its own role, started asynchronously.
- Its Claude key is separate from the site chat's key.

**Why:**
- A research run with web search can outlast the app's 30-second limit and CloudFront's origin timeout.
- A separate role is the only way to make the key readable by research alone.

**Set aside:**
- Separate tables for sources, questions and evidence, as the starting data model sketched. Every read needs them together, so splitting them only adds queries.

**Also decided:** pasted job postings are never stored, only passed to a run. The casebook keeps the link and a summary in my own words.

## 19 Nov 2026: Commit City is drawn as an isometric night city

**Decided:** the owner picked the bold "Night city" direction over a side-on dusk street and a blueprint drawing. It's drawn as SVG in the browser from the published numbers, so the page stays a single request and the picture is crisp at any size.

**How it stays usable:** the frame is measured once with every building standing, so scrubbing never crops the picture. On phones the card moves under the city, and a row of 44px building buttons sits beside it, because the buildings themselves can be smaller than a fingertip. The table view carries every number for screen readers.

**Set aside:** canvas or WebGL. They'd make the buildings unreachable by keyboard and screen readers without a second, parallel structure.

## 19 Nov 2026: Town hall keeps owner data and published data in separate tables

**Decided:**
- `ctrlaltjay-town` holds everything owner-side in one partition per repo (`META`, dated `STATS#` rows), plus collector runs, and later tours and the approvals log. `ctrlaltjay-public-city` holds only what the owner publishes. This adjusts the spec's starting model (separate repos, repo_stats, tours, tour_stops and approvals tables) the same way Casebook's was: rows read together live together.
- A separate collector Lambda holds the GitHub token; the app never does.
- Weekly history comes from `/stats/contributors`, which covers a repo's whole life, with commit paging as the fallback. `/stats/commit_activity` only covers a year.
- Building width will use total bytes from `/languages`. It changes only when code is added or removed, unlike line counts, and it's the same number GitHub uses for its language bar.

**Why:** public pages can be pointed at a table that, by construction, holds nothing unapproved. A mistake in a public query can't leak a hidden repo if the hidden repo was never in the table it reads.

**Set aside:** static JSON in S3 for the public snapshot. A table keeps publishing and the approvals log in one transaction-friendly place, and needs no new bucket permissions.

## 19 Nov 2026: Owner sign-in adds an authenticator app code

**Decided:** sign-in becomes the passcode plus a 6-digit code from an authenticator app (TOTP), with eight one-time recovery codes. This replaces the single-passcode decision below, now that Town hall will be able to browse private repos and publish from them.

**Why:** the owner chose an authenticator code over a passkey. It is simpler to build and use, though weaker against phishing.

**How:**
- The code check is written by hand from RFC 6238 and checked against its test vectors, rather than adding a library for about thirty lines. `segno` draws the QR code as SVG on the server.
- The secret is an SSM SecureString that the app writes during setup, so the app role gained read, write and tag access to that one parameter.
- The check only switches on once the parameter exists, so deploying it couldn't lock the owner out, and deleting the parameter is the way back in.

**Set aside:** a passkey (WebAuthn), as the stronger option.

## 19 Nov 2026: Owner sign-in stays a single passcode, with server-side sessions

**Decided:** keep the passcode as the only sign-in factor. Add a server-side session record so sessions expire (`ADMIN_SESSION_HOURS`, default 12) and signing out ends them everywhere.

**Why:** the owner chose not to add a passkey or second factor for now. Before this change a session lived only in a signed cookie with no expiry, so a copied cookie stayed valid until `SECRET_KEY` was rotated.

**Set aside:** a passkey (WebAuthn) as a required second step. It is the stronger option and can be added later without changing the session design.

**How:** each sign-in writes a row to `ctrlaltjay-portfolio-items` under a `__adminsession_` id, holding only a SHA-256 hash of the session ID. That table already holds the rate-limit rows, and every public read already skips `__` ids, so no new table or IAM change was needed.
