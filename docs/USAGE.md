# Usage Guide

## Accessing the Portfolio

Visit [https://ctrlaltjay.dev](https://ctrlaltjay.dev) to view the public portfolio.

## Public Features

### Navigation
- Use the **tab bar** (About, Projects, Experiences, Resume, Contact) to navigate between sections.
- Click any **card** to open a detail modal with full information.
- Use **arrow keys** to navigate between cards, **Enter** to open.

### Filtering & Search
- **Subsection pills** — Filter by category (e.g., "Web Development", "Certifications").
- **Skills filter** — Blue pills below the controls row; click to filter by skill.
- **Search** — Type in the search box. Use the field selector dropdown to target specific fields.
- **Sort** — Choose sort order (newest, oldest, title A-Z, etc.).

### Theme
- Click the **sun/moon button** (bottom-right) to toggle between dark and light themes.

### View Mode
- Click the **grid/list button** (bottom-right) to switch between grid and list card layouts.

### Favorites
- Click the **heart icon** on any card to bookmark it. Favorites persist in your browser.

### Deep Links
- Every card has a unique URL. Copy the browser URL when a modal is open to share that specific item.
- Example: `https://ctrlaltjay.dev/#item/abc-123-def`

### Recently Viewed
- A carousel of your last 8 viewed items appears above the Projects tab.

### Resume
- Click **Print** on the Resume tab. Non-admin users must enter a **resume key** to unlock printing.

## Admin Features

### Logging In
- Navigate to `https://ctrlaltjay.dev/?admin=login` or double-click any card area.
- Enter the admin passcode. After 5 failed attempts, you're locked out for 10 minutes.

### Managing Items
- **Create** — Click "Create New Project" or "Create New Experience" in the respective tab header.
- **Edit** — Open a card's detail modal and click the pencil icon, or double-click the card.
- **Delete** — Open a card's detail modal and click the trash icon.
- **Bulk delete** — Check cards using the checkboxes (top-left of each card), then click "Delete Selected" in the bulk bar.
- **Batch skill assignment** — Select cards, click "Assign Skills" in the bulk bar, choose skills and mode (add/remove/replace).
- **Drag-and-drop** — Drag cards to reorder them (admin only). Order is saved locally.

### Managing Resume
- Use the Export JSON button to download all data.
- Use the Resume Key panel to copy or rotate the resume access key.

### Activity Log
- Click "Activity Log" in the sidebar (admin only) to view recent admin operations.
- Click "Clear Log" to reset.

## Environment Variables

| Variable | Description | Default |
|---|---|---|
| `SECRET_KEY` | Flask session secret | `change-this-secret` |
| `ADMIN_PASSCODE_HASH` | Werkzeug password hash for admin login | — |
| `ADMIN_PASSCODE` | Plain-text admin passcode (fallback) | — |
| `AWS_REGION` | DynamoDB region | `ap-southeast-1` |
| `MAIL_SERVER` | SMTP server | `default_server` |
| `MAIL_PORT` | SMTP port | `587` |
| `MAIL_USERNAME` | SMTP username | — |
| `MAIL_PASSWORD` | SMTP password | — |
| `MAIL_USE_TLS` | Enable TLS | `true` |
| `MAIL_USE_SSL` | Enable SSL | `false` |

## Deployment

The app is deployed on **AWS Elastic Beanstalk** (`ctrlaltjay-prod`).

1. Push to git: `git push origin dev && git push origin dev:main`
2. EB auto-deploys from the `main` branch, or manually: `eb deploy ctrlaltjay-prod --staged`
