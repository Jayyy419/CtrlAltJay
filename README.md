# CtrlAltJay Portfolio

A Flask-powered personal portfolio with:

- custom UI/UX (non-template feel)
- dynamic cards for Projects and Experiences
- detail modals with rich context
- timeline-based Resume section
- skill visualization cards
- protected Admin CMS for create/edit/delete workflows

## Stack

- Flask
- Flask-Mail
- SQLite (built into Python)
- Vanilla JavaScript + custom CSS

## 1. Local Setup

Create virtual environment:

```bash
py -m venv venv
```

Activate virtual environment:

```bash
venv\Scripts\activate
```

Install dependencies:

```bash
pip install -r requirements.txt
```

## 2. Environment Variables

Create a `.env` file in the project root:

```env
SECRET_KEY=replace_with_a_long_random_secret

ADMIN_USERNAME=admin
ADMIN_PASSWORD=change_me

MAIL_SERVER=smtp.office365.com
MAIL_PORT=587
MAIL_USERNAME=your_email
MAIL_PASSWORD=your_password
MAIL_USE_TLS=true
MAIL_USE_SSL=false
```

Important:

- Change `ADMIN_PASSWORD` immediately.
- Change `SECRET_KEY` before deploying.
- If email is not configured, contact form still loads but sending can fail gracefully.

## 3. Run App

```bash
py app.py
```

Open:

- Portfolio: `http://127.0.0.1:5000/`
- Admin Login: `http://127.0.0.1:5000/admin/login`

## 4. Admin CMS Guide

After login, admin dashboard has 3 editors:

1. Projects & Experiences
2. Resume Timeline
3. Skills

### Projects & Experiences Editor

Supports:

- create card
- edit card
- delete card
- optional image upload
- optional external URL
- flexible modal fields (date label/value, deliverables, challenges, future improvements, notes)

Card preview on portfolio shows:

- title
- by field
- tag (example: `Events - Dialogue`)

### Resume Timeline Editor

Supports:

- add/edit/delete timeline item
- choose lane (`education` or `work`)
- set custom `sort_order`

This keeps timeline extensible without touching code.

### Skills Editor

Supports:

- add/edit/delete skill
- set level percentage
- set focus text
- control display order

## 5. Sorting and Filtering (Public Site)

Both Projects and Experiences include:

- category filter
- sort by title: A to Z / Z to A
- sort by created date: newest/oldest
- sort by updated date: newest/oldest

Default behavior prioritizes latest content first.

## 6. Uploaded Files

Uploaded images are stored in:

`static/uploads/`

Use `.gitignore` if you do not want uploads committed.

## 7. Deployment Notes

- `Procfile` already uses `gunicorn app:app`.
- SQLite is file-based; use persistent disk storage in production.
- For multi-admin scale, consider migration to PostgreSQL and role-based auth.
