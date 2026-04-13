# Changelog

All notable changes to the CtrlAltJay portfolio are documented here.

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
