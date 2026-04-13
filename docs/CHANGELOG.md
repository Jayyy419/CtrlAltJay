# Changelog

All notable changes to the CtrlAltJay portfolio are documented here.

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
