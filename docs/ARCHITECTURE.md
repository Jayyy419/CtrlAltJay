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
- **Casebook** (`casebook.py`, owner-only): routes under `/api/owner/`. A blueprint guard returns an empty 404 to anyone but the signed-in owner, and every response is `Cache-Control: no-store` and `X-Robots-Tag: noindex`. Data lives in `ctrlaltjay-casebooks` (one partition per casebook: `META`, plus `SRC#`, `Q#` and `EV#` rows) and `ctrlaltjay-stories`. Research runs in its own Lambda function, which alone can read the Casebook API key. The public tables are only read, never written.
- **Skill tree**: the Stack panel's Map view is built in the browser from `/api/public-data` (skills, plus each item's `skills` tags). It has no endpoint or table of its own, so it only shows skills that at least one published item is tagged with.
- **Authentication**: Owner sign-in with a passcode, rate limited (5 attempts, 10-min lockout). Each sign-in creates a server-side session row; a session ends when it reaches `ADMIN_SESSION_HOURS` (default 12) or on sign-out, even if the cookie was copied. See `SECURITY.md`.
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
- **Casebook research**: a separate Lambda function (`ctrlaltjay-casebook-research`, up to 15 minutes per run) that the app starts asynchronously.
- **Deploys**: GitHub Actions with OIDC; see `OPERATIONS.md`.
