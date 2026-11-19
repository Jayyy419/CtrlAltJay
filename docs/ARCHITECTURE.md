# Architecture

## Overview

CtrlAltJay is a single-page portfolio application built with Flask (Python) on the backend and vanilla JavaScript on the frontend. It is deployed on AWS Elastic Beanstalk with DynamoDB for persistence.

## System Diagram

```
┌─────────────┐     HTTPS      ┌──────────────────┐
│   Browser    │ ─────────────► │  AWS Elastic      │
│  (Tailwind   │                │  Beanstalk        │
│   + Vanilla  │ ◄───────────── │  (Flask/Gunicorn) │
│   JS)        │   JSON API     │                   │
└─────────────┘                └────────┬─────────┘
                                        │
                               ┌────────▼─────────┐
                               │   DynamoDB        │
                               │  (3 tables)       │
                               └──────────────────┘
```

## Backend (Flask)

- **Entry point**: `app.py`
- **WSGI server**: Gunicorn (configured in `Procfile`)
- **Casebook** (`casebook.py`, owner-only): the page at `/owner/casebook` (template `templates/casebook.html`, script and styles in `casebook_ui/`, served by the blueprint rather than from `/static`) and the API under `/api/owner/`. A blueprint guard returns an empty 404 to anyone but the signed-in owner, and every response is `Cache-Control: no-store` and `X-Robots-Tag: noindex`. Data lives in `ctrlaltjay-casebooks` (one partition per casebook: `META`, plus `SRC#` and `Q#` rows) and `ctrlaltjay-stories`. Matching lives in `casebook_evidence.py`: a keyword list per competency, matched against the text fields of portfolio items, resume rows and stories, with the owner's corrections and left-out items stored on the case's `META` row. Evidence and outlines are worked out on each read rather than stored, so they follow edits to the portfolio. Research runs in its own Lambda function, which alone can read the Casebook API key. The public tables are only read, never written.
- **Skill tree**: the Stack panel's Map view is built in the browser from `/api/public-data` (skills, plus each item's `skills` tags). It has no endpoint or table of its own, so it only shows skills that at least one published item is tagged with.
- **Authentication**: Owner sign-in with a passcode, then a code from an authenticator app once one is set up (`owner_totp.py`, setup page at `/owner/security`), rate limited (5 attempts, 10-min lockout). Each sign-in creates a server-side session row; a session ends when it reaches `ADMIN_SESSION_HOURS` (default 12) or on sign-out, even if the cookie was copied. See `SECURITY.md`.
- **File uploads**: Saved to `static/uploads/` with timestamp prefix
- **Security**: 11 response headers including CSP, HSTS, X-Frame-Options
- **Mail**: Flask-Mail for contact form submissions

### Routes

| Route | Method | Auth | Description |
|---|---|---|---|
| `/` | GET | — | Renders index.html with profile data |
| `/api/public-data` | GET | — | Returns all projects, experiences, resume, skills |
| `/admin/auth` | POST | — | Admin login with rate limiting |
| `/admin/logout` | POST | — | Ends the owner session on the server and in the browser |
| `/api/admin/items` | GET, POST | Admin | List/create portfolio items |
| `/api/admin/items/<id>` | PUT, DELETE | Admin | Update/delete portfolio items |
| `/api/admin/resume` | GET, POST | Admin | List/create resume entries |
| `/api/admin/resume/<id>` | PUT, DELETE | Admin | Update/delete resume entries |
| `/api/admin/skills` | GET, POST | Admin | List/create skills |
| `/api/admin/skills/<id>` | PUT, DELETE | Admin | Update/delete skills |
| `/send_message` | POST | — | Contact form submission |
| `/api/resume-key/verify` | POST | — | Verify resume print key |
| `/api/admin/resume-key` | GET | Admin | Get current resume key |
| `/api/admin/resume-key/rotate` | POST | Admin | Generate new resume key |
| `/sitemap.xml` | GET | — | Dynamic XML sitemap |
| `/robots.txt` | GET | — | Robots file |

## Database (DynamoDB)

### Tables

| Table | Partition Key | Description |
|---|---|---|
| `ctrlaltjay-portfolio-items` | `id` (String) | Projects and experiences. Also stores `__settings` item for resume key. |
| `ctrlaltjay-resume-items` | `id` (String) | Education and work timeline entries. |
| `ctrlaltjay-skills` | `id` (String) | Tech stack skills with tier/level. |

### Portfolio Item Schema

```json
{
  "id": "uuid",
  "section": "project|experience",
  "category": "Web Development|Certifications|...",
  "subsection": "same as category for experiences",
  "title": "string",
  "summary": "string",
  "description": "string (supports markdown)",
  "date_label": "Released|Work in Progress|Completed|Ongoing",
  "date_value": "YYYY-MM-DD",
  "deliverables": "string",
  "challenges": "string",
  "future_improvements": "string",
  "extra_notes": "string",
  "image_path": "../static/uploads/...",
  "external_link": "https://...",
  "skills": "comma,separated,skill,names",
  "created_at": "ISO 8601",
  "updated_at": "ISO 8601"
}
```

## Frontend

### Technologies
- **Tailwind CSS** (CDN) + custom CSS (`static/css/style.css`)
- **Vanilla JavaScript** (`static/js/script.js`)
- **Ionicons 7.1.0** (with SRI hashes)

### State Management
A single `state` object holds all app data:
```js
const state = {
  projects: [],        // Portfolio items where section=project
  experiences: [],     // Portfolio items where section=experience
  resume: [],          // Timeline entries
  skills: [],          // Tech stack skills
  isAdmin: false,      // Admin authentication state
  modalItem: null,     // Currently open modal item
  dataLoaded: false,   // Whether API data has been fetched
};
```

### Key Systems
- **Tabs** — 5 tabs with URL hash-based routing
- **Card rendering** — `buildCard()` creates DOM elements with lazy images, skill chips, favorite buttons
- **Filtering** — Category/subsection pills, skills filter pills, field-targeted search
- **Pagination** — 12 cards per page with "Show More" button
- **Modals** — Detail view with markdown rendering, related items, deep linking
- **Admin** — Inline CRUD with image preview, skills picker, auto-save drafts
- **Theme** — CSS custom properties toggled via `.light-theme` class on `<html>`
- **Favorites** — localStorage array of item IDs
- **Recently viewed** — localStorage array of last 8 viewed item IDs
- **Activity log** — localStorage array of admin action entries

### CSS Architecture
- Custom CSS layered on top of Tailwind utility classes
- Responsive breakpoints: 1060px (tablet), 640px (mobile), 400px (small phone)
- Print styles hide non-essential UI and format resume for paper
- Light theme uses CSS custom properties overriding dark defaults

## Infrastructure

- **Region**: ap-southeast-1 (Singapore); the certificate is in us-east-1, as CloudFront requires.
- **App**: one Lambda function running Flask through apig-wsgi, reached only through CloudFront. The function URL rejects requests without CloudFront's origin header.
- **Static files**: S3, served by CloudFront under `/static/*`.
- **Edge**: a CloudFront Function serves the holding page while the site is off; a KeyValueStore holds the owner preview secret.
- **Domain**: ctrlaltjay.dev in Route 53, aliased to CloudFront.
- **Data**: DynamoDB, on-demand.
- **Town hall** (`townhall.py`, owner-only): the page at `/owner/townhall` (template `templates/townhall.html`, script and styles in `townhall_ui/`) and the API under `/api/owner/townhall/`. Same guard and headers as Casebook. It reads and writes `ctrlaltjay-town`; publishing (step 4) will be the only path into `ctrlaltjay-public-city`.
- **Commit City** (`commit_city.py`, public): `/city` (template `templates/city.html`, `static/js/city.js`, `static/css/city.css`) and `/api/city`. The API returns the published snapshot from `ctrlaltjay-public-city`, or an invented sample city when nothing is published. It never reads `ctrlaltjay-town` and never calls GitHub. The page draws an isometric SVG city: height from commits, width from bytes of code, lit windows from the share of weeks with activity, window colour from the main language, scaffolding and a crane when the last push is under 7 days old, boards when archived. The sky follows the hour in Singapore, with dusk if the time can't be read. The timeline replays the weekly series; reduced motion skips the rise and stops the crane.
- **Source Map** (`source_map.py`, public): `/map/<slug>` and `/map/<slug>/<stop>` (template `templates/map.html`, `static/js/map.js`, `static/css/map.css`) and `/api/map/<slug>`. A tour is read only from its `TOUR#<slug>`/`CURRENT` row in `ctrlaltjay-public-city`; `sample` is a built-in invented tour, marked as a sample and `noindex`. Unknown slugs and stop numbers out of range return 404. The page lays districts out as a treemap from their stored sizes, draws the route through the stops, highlights Python, JavaScript and TypeScript excerpts in the browser, and moves between stops with `history.pushState`.
- **Publishing** (Town hall): approving a repo, moving it to the drawer, editing an approved building's words or pressing "Publish latest stats" rebuilds the single `CITY`/`CURRENT` row in `ctrlaltjay-public-city` from every approved repo's latest stats, through `public_building()`. The main site shows its Commit City link, and the sitemap lists `/city`, only while that snapshot has at least one building.
- **Town hall collector** (`town_collector/collector.py`, Lambda `ctrlaltjay-town-collector`): the only code that holds the GitHub token. Each run lists the repos the token can see and records them (new ones hidden), then writes a dated stats snapshot per repo. GitHub endpoints used, checked against GitHub's published OpenAPI description (API version 2022-11-28):
  - `GET /user/repos` (paged, 100 at a time): the repos, with `pushed_at`, `archived`, `private` and `default_branch`.
  - `GET /repos/{owner}/{repo}/stats/contributors`: weekly commit counts per contributor over the repo's whole history, summed into one weekly series. It answers 202 while GitHub computes it; the collector asks again up to five times, 12 seconds apart.
  - `GET /repos/{owner}/{repo}/commits?sha={default branch}` (paged, up to 5,000 commits): the fallback when the stats never finish, bucketing commit dates into the same Sunday-start weeks. `/stats/commit_activity` was set aside because it only covers the last year.
  - `GET /repos/{owner}/{repo}/languages`: bytes of code per language.
  - Rate limits: a 403 or 429 with `x-ratelimit-remaining: 0` stops the run and records the reset time; other 403/429s wait for `retry-after` (up to two minutes) and try again; 5xx is retried twice.
- **Casebook research**: a separate Lambda function (`ctrlaltjay-casebook-research`, up to 15 minutes per run) that the app starts asynchronously. `POST /api/owner/casebooks/<id>/research` checks the month's budget, marks the case `queued` with a run ID and invokes the function. The run:
  1. Claims the run (`queued` to `running`, conditional on the run ID), so a retried invocation never runs or charges twice.
  2. Searches with the Claude API and the `web_search_20260318` tool (plus `web_fetch_20260318` when the case has a posting link), continuing paused turns until it finishes or spends three quarters of its budget. Progress is written to the case after each request; the page polls it.
  3. Numbers every source it saw, then makes a second call with a JSON schema that turns the notes into findings, questions, questions for them and topics to revise.
  4. Checks provenance in code: "Reported" needs a real cited source, "From the posting" needs its phrase to appear in the posting, otherwise both become "Usual". Only cited sources are kept, as title, link, date and a short note.
  5. Replaces the last run's research questions and sources, keeps the owner's own questions, and adds the run's cost to the case and to the month's `SPEND` row, even when the run fails.
- **Deploys**: GitHub Actions with OIDC; see `OPERATIONS.md`.
