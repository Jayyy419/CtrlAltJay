# Changelog

All notable changes to the CtrlAltJay portfolio are documented here.

## 20 Nov 2026: AWS sweep skill

### Added
- `.claude/skills/aws-sweep`: a Claude Code skill that sweeps the AWS account the portfolio shares with the other projects. It checks costs and day-to-day spikes, resources left over or idle in every region, `Project` and `Environment` tags (including resources that were never tagged), budgets and their alerts, and IAM sign-in basics. It fixes only what is safe (missing tags from its project registry, a budget for a project without one) and asks before deleting or changing anything else. Its scripts are read-only and run through the AWS MCP connector.

## 20 Nov 2026: Claude SDK 2.11

### Changed
- `anthropic` 0.119.0 to 2.11.0 in the app and the research worker. Every Claude call (site chat, smart search, Casebook research, Drill feedback, Town hall draft help) now uses API version 2026-10-21 and sends the key as `Authorization: Bearer`. No code change was needed: nothing sent `temperature`, `top_p` or `top_k`, documents or citations in user turns, or used `httpx` directly. Replaces Dependabot #141.
- The SDK is now under the Apache 2.0 licence (it was MIT up to 1.x).

## 20 Nov 2026: Test suite

### Added
- 13 test modules in `tests/`: owner sessions, authenticator sign-in, Casebook (API, evidence, research worker and its API, questions for them, Drill), Town hall (collector, approval and publishing, tours, draft help), Source Map and the secret check. AWS is faked with moto; Claude and GitHub with stand-ins.
- `tests/run_all.py` runs each module in its own process. A Tests workflow runs it on every pull request, and the deploy runs it before anything ships.
- `requirements-dev.txt` (moto), kept out of the Lambda package.

## 20 Nov 2026: Guestbook endpoint removed

### Removed
- `/api/notes` and the owner's `/api/admin/notes` routes. The guestbook's page was taken out on 15 Oct and nothing called them since. No notes were stored; the one leftover rate-limit record was deleted.

## 20 Nov 2026: Claude spend reported to Upkeep

### Changed
- `UpkeepUsageUrl` now defaults to Upkeep's origin, so usage reporting only waits on the key in Parameter Store.

### Added
- Every Claude response (site chat, smart search, Drill feedback, Town hall draft help and Casebook research) can report its model name and token counts to Upkeep, so the owner's portal shows the month's Claude spend for this site. Nothing else is sent: no prompts, answers, visitor details or IDs. It's off until `UpkeepUsageUrl` is set and the `/ctrlaltjay/upkeep-usage-key` parameter exists; see `docs/OPERATIONS.md`.
- A first unit test suite (`tests/`, standard-library `unittest`), run by the deploy before it builds.

## 20 Nov 2026: Python 3.14 and Pillow 13

### Security
- Pillow 12.2.0 to 13.0.0. That clears every pip-audit finding against Pillow, including the JPEG decoder overflows.

### Changed
- The Lambda functions run on python3.14 (Amazon Linux 2023) instead of python3.11 (Amazon Linux 2, which reached end of life in June 2026). python3.11 had no Pillow 13 wheel and is deprecated on 30 Jun 2027. The deploy and site power workflows build with Python 3.14, and the deploy's syntax check now runs on that version.

## 20 Nov 2026: Dependency updates

### Changed
- apig-wsgi 2.20.0, boto3 1.43.111, click 8.5.0, gunicorn 26.2.0, MarkupSafe 3.0.4, packaging 26.3 and python-dotenv 1.2.4, in place of seven Dependabot pull requests that were based on the history before the rewrite.

## 20 Nov 2026: Dependency security update

### Security
- Werkzeug 3.1.8 to 3.1.9, for PYSEC-2026-4312.
- Pillow stays on 12.2.0 for now. The advisories against it are fixed in 12.3.0 and 13.0.0, but neither ships a wheel that installs on the python3.11 Lambda runtime (Amazon Linux 2). Moving to Pillow 13 waits on moving the function to python3.12 or later.

## 20 Nov 2026: Sentrix description

### Fixed
- The Now building entry for Sentrix shows a real one-line description instead of a placeholder.

## 19 Nov 2026: Casebook, step 7

### Added
- Drill, from the Drill button on any case. Two modes:
  - Flashcards: answer out loud, turn the card to see your evidence and STAR outline, then rate it Missed it, Shaky or Got it (or press 1, 2, 3).
  - Interview room: a two-minute countdown and a box to type your answer, then How it went (time and words) beside your notes, and the same rating.
- Ratings are saved per question and decide the order: missed and shaky questions come first next round. Ratings on the sample case aren't saved.
- "Get feedback from Claude" in the Interview room: which STAR parts came through, what went well and what to work on. It only runs when pressed, is capped at US$1 a month, and keeps neither your answer nor the feedback.

### Changed
- Town hall draft help and Drill feedback share one spending-cap helper (`claude_budget.py`).

## 19 Nov 2026: Casebook, step 6

### Added
- Questions for them: add your own, edit or remove any, and mark the ones you want "On the sheet". A new research run keeps your own questions and your picks, and doesn't bring back ones you removed.
- "Open with" on the case form: a line or two you'll open with, shown at the top of the Day-of sheet.
- The Day-of sheet, as a boarding pass: organisation, role, date, format and a countdown in Singapore time, then Open with, up to three stories with their STAR outlines (gaps stay as gaps), Ask them, Know before you go and Last checks. Made for a phone on the day.
- Save as PDF prints the sheet on its own in ink-friendly black and white, through the browser's print dialog.

### Fixed
- The Sign-in security link in the Casebook sidebar is 44px tall on phones.

## 19 Nov 2026: Source Map, step 7

### Added
- "Draft with Claude" on each plotted stop in Town hall. It fills in a suggested title and "What to notice" from the stop's lines; nothing is saved until the owner edits it and presses Save the stop. The stop editor shows the month's draft spending against its cap (US$1 by default).

### Changed
- The stop editor grows with its content on wide screens instead of scrolling inside a fixed-height box.

### Fixed
- Every owner route, including the 404 others get, now sends `no-store` and `noindex`. Sign-in security and the owner tools list had been missing them.

## 19 Nov 2026: Source Map, step 6

### Added
- Town hall Tours: plot a Source Map tour on the same night map visitors walk. Choose a district, open a file, pick up to 40 lines, mark the key ones, write a title and what to notice, and press "Plot a stop". The lines are copied on the server at the commit the file list came from.
- Every excerpt is checked for secrets (key formats, tokens, passwords in code, .env lines, private addresses, emails, random-looking strings). A flagged stop blocks "Publish the map" until its lines change or the owner marks it as not a secret, which is logged.
- Reorder stops by dragging the route pins, with Move earlier and Move later, or with Shift and the arrow keys on a pin.
- Preview a tour exactly as visitors would see it, then "Publish the map". "Take the map down" removes it. Putting a repo in the drawer takes its tour down too.
- Private repos get district names the owner chooses ("Area A" until then), and no paths, file names, commits or links on the public tour.
- The daily collector run marks stops whose lines changed as "Needs a look". Visitors keep seeing the approved excerpt until the owner plots it again or keeps it as is.
- Commit City buildings link to their tour with "Take the tour".

## 19 Nov 2026: Source Map, step 5

### Added
- Source Map at `/map/<tour>`: a guided walk through a codebase drawn as a night map, with districts sized by code, numbered pins on a route, and "You are here". Each stop has a title, an explanation and a highlighted excerpt with the key lines marked. Next stop and Back a stop, or the arrow keys, move along the route, and each stop has its own address. On phones the map sits above the stop and code scrolls sideways.
- A clearly marked sample tour at `/map/sample` of an invented project, kept out of search results. Real tours come with step 6.
- Commit City opens a building's card when its address ends in `#` and the building's name, so a tour can link straight to it.

## 19 Nov 2026: Commit City, step 4

### Added
- Town hall: open any repo to give it a public name and description, link a project page, see exactly what would go public, preview the building, and choose "Approve for the skyline" or "Keep it in the drawer".
- "Publish latest stats" copies the newest approved stats to the public city.
- Approvals log in Town hall.
- The Projects panel links to Commit City, and the sitemap lists it, once at least one building is published.

### Fixed
- Approvals logged within the same second now keep their order.

## 19 Nov 2026: Commit City, step 3

### Added
- Commit City at `/city`: an isometric night city, one building per project, with a timeline you can scrub or play, a card per building, a table view, and keyboard use (arrow keys between buildings, Enter for the card). It shows a clearly marked sample city until real projects are approved, and isn't linked from the site or listed in the sitemap yet.

## 19 Nov 2026: Town hall, step 2

### Added
- Town hall at `/owner/townhall`, owner-only: lists every repo the GitHub token can see with Floors, Lights on, Built with and Last built, and whether it's public or private, on the skyline or in the drawer.
- The Town hall collector, run daily at 9:00 am Singapore time and from Refresh now. It's the only thing that can read the GitHub token.
- Tables `ctrlaltjay-town` (owner-side) and `ctrlaltjay-public-city` (published only, empty until step 4).

## 19 Nov 2026: Recovery code download, turning the authenticator off

### Added
- Recovery codes can be downloaded as a text file.
- "Turn off the authenticator" on the sign-in security page. It needs a session signed in with a code and a fresh code to confirm, and sign-in goes back to the passcode alone.

## 19 Nov 2026: Owner links

### Added
- Admin Tools lists Sign-in security and Casebook once you're signed in. The list comes from an owner-only endpoint, so their addresses never appear in the public page.

### Fixed
- The authenticator QR code was cropped on the setup page, cutting off a corner marker. It now scales as a whole.

## 19 Nov 2026: Authenticator app sign-in

### Added
- Sign-in security page at `/owner/security`: set up an authenticator app with a QR code, get eight one-time recovery codes, replace either later.
- Once set up, signing in asks for the passcode and then a 6-digit code. A recovery code works in place of the code, once each.

### Changed
- Sessions started with the passcode alone stop counting once an authenticator is set up.

## 19 Nov 2026: Casebook, step 5

### Added
- "Build the case": research on Claude Opus 5.5 with web search, run in the background with live progress. You can leave the page and come back.
- What research found: what the organisation says it values, the format, recent news, what couldn't be found and a short summary of the posting, each with source links and dates.
- Researched questions labelled Reported (with sources and dates), From the posting (quoting the requirement) or Usual for this kind of role. The labels are checked before anything is stored.
- Questions for them and topics to revise from research. Topics show in Loose ends.
- Caps: US$3 per run and US$10 per month by default, with the cost of each case and the month's total shown.

## 19 Nov 2026: Casebook, step 4

### Added
- Your evidence: each case has a list of what they look for (with defaults per occasion) and your portfolio items, resume rows and stories are matched and ranked against it. Every match shows the word and field that triggered it. Click a cell to correct it, or leave an item out of the case.
- Questions on the table: add the usual questions for the occasion, labelled "Usual for this kind of role", or your own, labelled "Added by you". Each gets its best one or two pieces of evidence, which you can change or replace with a story.
- STAR outlines filled only from stored fields. Results are never filled from an item; gaps show as `[your result here]`.
- Story bank: stories in your own words, linked to the items and skills they draw on, showing which cases use them. A question's outline can be turned into a story.
- Loose ends now lists questions with nothing to answer them, things nothing in your material shows, and stories with gaps.

## 19 Nov 2026: Sitemap

### Fixed
- The sitemap no longer lists drafts or deleted items.

## 19 Nov 2026: Casebook, step 3

### Added
- Casebook screens at `/owner/casebook`, owner-only: a case list, the "What's the case?" form, and a casebook view with Questions on the table, Your evidence (a coverage grid on laptops, a list on phones), Loose ends and Questions for them. Cost and the Day-of sheet button sit at the top right.
- A sample casebook, clearly marked, so the screens can be tried before research exists.
- The screen's script and styles are served from `/owner/casebook/` behind the owner check, not from the public `/static` folder.

## 19 Nov 2026: Casebook, step 2

### Added
- Owner-only Casebook API (`casebook.py`): casebooks and the story bank, behind the owner session, with an empty 404 for anyone else and `no-store` / `noindex` on every response.
- `ctrlaltjay-casebooks` and `ctrlaltjay-stories` tables, encrypted, with point-in-time recovery, retained if removed from the stack.
- `ctrlaltjay-casebook-research`, the research worker. For now it only confirms it can read its own key.
- `docs/STACK.md`, `docs/OPERATIONS.md`, `docs/ROADMAP.md`, `PORTFOLIO.md`.

### Changed
- README rewritten for how the site runs today.
- `docs/ARCHITECTURE.md`: infrastructure section brought up to date; account details removed.
- `robots.txt` disallows the owner paths.

## 19 Nov 2026: Skill tree

### Added
- The Stack panel opens on a Map view: each skill is wired to the projects and experience entries tagged with it. Picking a skill redraws the links; picking a project opens it. On phones the skills scroll sideways and the linked projects branch below.
- A Map / List switch keeps the original marketplace list, and remembers the choice.

## 19 Nov 2026: Owner sessions

### Changed
- Owner sign-ins now expire after `ADMIN_SESSION_HOURS` (default 12). Flask also rejects any session cookie older than that.
- Signing out ends the session on the server. A copy of the session cookie stops working at the same moment.
- Sessions signed in before this change are signed out once and need one fresh sign-in.

### Added
- `SECURITY.md`, covering the owner-only area.
- `docs/DECISIONS.md`, starting with the sign-in decision.

## QOL Batch 6 — UX Polish & Admin Productivity

### Added
- **Admin clone item** — Duplicate button (copy icon) in detail modal pre-fills the admin form for quick item cloning.
- **Keyboard shortcuts overlay** — Press `?` to view all shortcuts. Quick keys: `1`–`5` switch tabs, `T` toggles theme, `/` focuses search.
- **Staggered card entrance** — Cards cascade in with 50ms delay between each for a smoother visual reveal.
- **Search result highlighting** — Matching text in card titles is highlighted with amber `<mark>` tags during search.
- **Card date display** — Cards now show the date (month + year) when `date_value` is set.
- **Reading time & word count** — Detail modal shows estimated reading time and word count below the tag.
- **Smooth page load transition** — Body fades in on initial load for a polished first impression.
- **Auto-linkify bare URLs** — Plain `https://` URLs in modal text fields are automatically converted to clickable links.
- **Card summary tooltip** — Hovering over a card shows the summary text as a native browser tooltip.
- **Collapsible long modal sections** — Modal rows with 300+ characters get a "Show more/Show less" toggle to reduce scroll.
- **Pin favorites to top** — Favorited items are pinned to the top of their grid, preserving sort order within groups.
- **Admin JSON import** — New backend endpoint (`/api/admin/import`) and sidebar button to bulk-import items from exported JSON files.
- **Admin duplicate title warning** — Creating a new item with an existing title triggers a confirmation prompt.
- **Image crossfade in carousel** — Carousel image transitions now use a 250ms opacity fade instead of instant swap.
- **Enhanced tab transitions** — Tab content switches with a combined fade + slide-up animation.

### Changed
- Service worker cache version bumped to `v2`.

## QOL Batch 5 — Infrastructure & Polish

### Added
- **Multi-image carousel** — Items can now have multiple images. Detail modal shows prev/next arrows and dot navigation when additional images are present. New `additional_images` field in schema.
- **PWA support** — Added `manifest.json` and service worker (`sw.js`) for installability and offline caching (network-first strategy). Served from root via Flask routes.
- **Admin stats dashboard** — Collapsible sidebar panel showing total counts, category breakdowns, and top 10 skill usage across portfolio items.
- **Image optimization (Pillow)** — Uploaded images are automatically resized to max 1200px width and compressed (JPEG quality 85) using Pillow. SVG/ICO bypass optimization.
- **Animated counters** — "By the Numbers" section on the About tab with count-up animation (projects, experiences, skills) triggered by IntersectionObserver.
- **Social share buttons** — LinkedIn, X (Twitter), Telegram, and copy-link buttons in the detail modal with encoded deep links.
- **Custom 404 page** — Styled error page matching portfolio design for 404 and 500 errors.
- **Contact form honeypot** — Hidden `website` field that silently rejects bot submissions while appearing successful.
- **Visitor hit counter** — Server-side counter in DynamoDB incremented on each page load. Displayed in admin sidebar.
- **Project status badges** — New `status` field (Active/Completed/In Progress/Archived) shown as colored pills on cards.
- **Certificate verification links** — New `credential_url` field with a "Verify Credential" button in the detail modal.
- **Accessibility audit pass** — Skip-to-content link, `role="main"` landmark, ARIA live region for dynamic announcements, focus trapping in all modals via MutationObserver, screen-reader-only utility class.
- **Auto-backup to S3** — Admin button exports all 3 DynamoDB tables as JSON to S3 bucket (`ctrlaltjay-backups`).
- **CloudFront CDN preparation** — Static assets served with `Cache-Control: public, max-age=86400` headers for CDN compatibility.

### Changed
- CSP updated with `manifest-src 'self'` and `worker-src 'self'` for PWA.
- Modal image now wrapped in carousel container (`modal-carousel`).
- Admin item form expanded with Status, Credential URL, and Additional Images fields.

---

## QOL Batch 4 — Feature-Rich Update

### Added
- **Shareable deep links** — Every card now has a unique URL (`#item/<id>`) that can be shared. Opening the link auto-navigates to the correct tab and opens the detail modal.
- **Dark/light theme toggle** — Fixed button in the bottom-right corner. Preference saved to localStorage.
- **Recently viewed carousel** — Horizontal strip above the Projects tab showing the last 8 viewed items. Persisted in localStorage.
- **Related items in detail modal** — "Related" section at the bottom of each detail modal showing up to 4 items scored by shared skills and category.
- **Activity log (admin)** — Admin-only collapsible log in the sidebar tracking create, edit, delete, reorder, and batch skill operations with timestamps.
- **Markdown support** — Text fields in detail modals now render **bold**, *italic*, `inline code`, and [links](https://example.com). Input is sanitized to prevent XSS.
- **Card view toggle** — Switch between grid and list layouts using the fixed button. Preference saved to localStorage.
- **Favorites/bookmarks** — Heart icon on every card. Favorited items are saved in localStorage.
- **Drag-and-drop card reorder (admin)** — Admin users can drag cards to reorder them. Order saved locally.
- **Batch skill assignment** — Select multiple cards via bulk mode, then assign/remove/replace skills in bulk using a modal picker.
- **SEO sitemap** — `/sitemap.xml` route dynamically lists all pages and portfolio items. `/robots.txt` points crawlers to it.
- **SEO meta tags** — Open Graph, Twitter Card, canonical URL, and meta description added to `<head>`.
- **Documentation** — `docs/` folder with CHANGELOG, USAGE guide, and ARCHITECTURE overview.

## QOL Batch 3 + Skills System

### Added
- Skills tagging system with admin picker, card chips, and modal display
- Skills filter pills for projects and experiences
- Search field selector dropdown (search by title, summary, description, etc.)
- "All" filter option for experiences subsection nav
- Ionicons CSP fix (`connect-src` updated for `https://unpkg.com`)
- Back-to-top button moved to right side

## QOL Batch 2

### Added
- Resume key system (gated print with admin key management)
- Export JSON button (admin)
- Tab count badges
- Last-updated footer timestamp
- Double-click card to edit (admin)

## QOL Batch 1

### Added
- Toast notifications
- Confirm dialog for destructive actions
- Skeleton loading cards
- Image lightbox in detail modal
- Keyboard navigation (arrow keys + enter)
- Bulk admin actions (select + delete)
- Auto-save admin draft (localStorage)
- Card entrance animations (IntersectionObserver)
- Back-to-top button
- Scroll progress bar
- Sticky subsection navigation
- Smooth tab transitions

## Initial Release

### Added
- Flask backend with DynamoDB CRUD
- Admin authentication with rate limiting
- Projects and Experiences sections with category/subsection filters
- Resume timeline (education + work)
- Tech stack display with tier grouping
- Contact form with Flask-Mail
- Responsive design with Tailwind CSS
- Security headers (CSP, HSTS, X-Frame-Options, etc.)
