"use strict";

const state = {
  projects: [],
  experiences: [],
  resume: [],
  skills: [],
  isAdmin: false,
  modalItem: null,
  controlsBound: false,
  rerenderProjects: null,
  rerenderExperiences: null,
  currentSection: null,
  dataLoaded: false,
  ideOpenTabs: ["about"],
  ideItemMeta: {},
};

const IDE_TAB_META = {
  about: { label: "bio.md", icon: "md" },
  projects: { label: "projects/", icon: "md" },
  experiences: { label: "experiences/", icon: "md" },
  resume: { label: "resume.pdf", icon: "md" },
  stack: { label: "stack.json", icon: "json" },
  contact: { label: "contact.md", icon: "md" },
};

const tabs = document.querySelectorAll(".tab-btn");
const panels = document.querySelectorAll(".tab-panel");

/* Escape untrusted strings (admin-authored content, search input) before
   interpolating into innerHTML template strings. */
function escapeHtml(value) {
  if (value === null || value === undefined) return "";
  return String(value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

/* ===== Toast notifications ===== */
function showToast(message, type = "info") {
  const container = document.getElementById("toast-container");
  if (!container) return;
  const toast = document.createElement("div");
  toast.className = `toast toast--${type}`;
  toast.textContent = message;
  container.appendChild(toast);
  setTimeout(() => toast.remove(), 3100);
}

/* ===== Confirm dialog ===== */
function showConfirm(title, message, options = {}) {
  return new Promise((resolve) => {
    const overlay = document.createElement("div");
    overlay.className = "confirm-overlay";
    const requireText = options.requireText || "";
    const confirmLabel = options.confirmLabel || "Delete";
    const inputHtml = requireText
      ? `<p class="confirm-hint">Type <strong>${requireText}</strong> to confirm</p>
         <input type="text" class="confirm-input" placeholder="Type here..." autocomplete="off" spellcheck="false">`
      : "";
    overlay.innerHTML = `
      <div class="confirm-box">
        <h4>${title}</h4>
        <p>${message}</p>
        ${inputHtml}
        <div class="confirm-actions">
          <button class="confirm-cancel" data-confirm="cancel">Cancel</button>
          <button class="confirm-danger" data-confirm="ok" ${requireText ? "disabled" : ""}>${confirmLabel}</button>
        </div>
      </div>`;
    document.body.appendChild(overlay);
    const okBtn = overlay.querySelector('[data-confirm="ok"]');
    if (requireText) {
      const input = overlay.querySelector(".confirm-input");
      input.addEventListener("input", () => {
        okBtn.disabled = input.value.trim().toLowerCase() !== requireText.toLowerCase();
      });
      input.focus();
    }
    overlay.addEventListener("click", (e) => {
      const btn = e.target.closest("[data-confirm]");
      if (!btn) return;
      if (btn.disabled) return;
      overlay.remove();
      resolve(btn.dataset.confirm === "ok");
    });
  });
}

/* ===== Skeleton loading ===== */
function showSkeletons(gridId, count = 6) {
  const grid = document.getElementById(gridId);
  if (!grid) return;
  grid.innerHTML = "";
  for (let i = 0; i < count; i++) {
    const skel = document.createElement("div");
    skel.className = "skeleton-card";
    skel.innerHTML = `<div class="skeleton-img"></div><div class="skeleton-line"></div><div class="skeleton-line"></div><div class="skeleton-line"></div>`;
    grid.appendChild(skel);
  }
}

function switchTab(tabName) {
  tabs.forEach((it) => {
    it.classList.remove("active");
    it.setAttribute("aria-selected", "false");
  });
  panels.forEach((panel) => panel.classList.remove("active"));
  const btn = document.querySelector(`.tab-btn[data-tab="${tabName}"]`);
  const panel = document.getElementById(tabName);
  if (btn) {
    btn.classList.add("active");
    btn.setAttribute("aria-selected", "true");
  }
  if (panel) panel.classList.add("active");
  syncIdeChrome(tabName);
}

function initTabs() {
  tabs.forEach((btn) => {
    btn.addEventListener("click", () => {
      switchTab(btn.dataset.tab);
      window.history.replaceState(null, "", `#${btn.dataset.tab}`);
      window.scrollTo({ top: 0, behavior: "smooth" });
    });
  });

  // Deep link: activate tab from URL hash (skip item/ deep links — handled after data loads)
  const hash = window.location.hash.replace("#", "");
  if (hash && !hash.startsWith("item/") && document.getElementById(hash)) {
    switchTab(hash);
  }
}

/* ===== IDE chrome: tab bar, file tree, status bar ===== */

function syncIdeChrome(tabName) {
  if (!IDE_TAB_META[tabName]) return;
  if (!state.ideOpenTabs.includes(tabName)) state.ideOpenTabs.push(tabName);
  renderIdeTabbar(tabName);
  showFileTreeSection(tabName);
  document.querySelectorAll(".file-tree-item[data-tab]").forEach((el) => {
    el.classList.toggle("active", el.dataset.tab === tabName);
  });
  const sectionEl = document.getElementById("ide-status-section");
  const label = IDE_TAB_META[tabName].label;
  if (sectionEl) sectionEl.textContent = label.endsWith("/") ? `${tabName}/` : label;
  updateIdeStatusCount(tabName);
  refreshMinimap();
}

function showFileTreeSection(sectionTab) {
  document.querySelectorAll(".file-tree-section").forEach((el) => {
    el.classList.toggle("active", el.dataset.treeSection === sectionTab);
  });
}

function renderIdeTabbar(activeTab) {
  const bar = document.getElementById("ide-tabbar");
  if (!bar) return;
  bar.innerHTML = state.ideOpenTabs.map((name) => {
    const meta = IDE_TAB_META[name] || state.ideItemMeta?.[name] || { label: name, icon: "md" };
    const isActive = name === activeTab;
    return `<div class="ide-tab ${isActive ? "active" : ""}" data-tab="${name}">
      <span class="fdot ${meta.icon}"></span> ${escapeHtml(meta.label)}
      <span class="close" data-close-tab="${name}" title="Close" aria-label="Close ${escapeHtml(meta.label)}">&times;</span>
    </div>`;
  }).join("");

  bar.querySelectorAll(".ide-tab").forEach((tabEl) => {
    tabEl.addEventListener("click", (e) => {
      if (e.target.dataset.closeTab) return;
      openIdeTabByName(tabEl.dataset.tab);
    });
  });
  bar.querySelectorAll("[data-close-tab]").forEach((btn) => {
    btn.addEventListener("click", (e) => {
      e.stopPropagation();
      closeIdeTab(btn.dataset.closeTab, activeTab);
    });
  });

  bar.querySelector(".ide-tab.active")?.scrollIntoView({ inline: "nearest", block: "nearest" });
  updateTabbarOverflow();
}

function updateTabbarOverflow() {
  const bar = document.getElementById("ide-tabbar");
  const wrap = document.getElementById("ide-tabbar-wrap");
  if (!bar || !wrap) return;
  wrap.classList.toggle("has-overflow-left", bar.scrollLeft > 2);
  wrap.classList.toggle("has-overflow-right", bar.scrollLeft + bar.clientWidth < bar.scrollWidth - 2);
}

function initTabbarScroll() {
  const bar = document.getElementById("ide-tabbar");
  if (!bar) return;
  bar.addEventListener("scroll", updateTabbarOverflow, { passive: true });
  bar.addEventListener("wheel", (e) => {
    if (e.deltaY === 0) return;
    bar.scrollLeft += e.deltaY;
    e.preventDefault();
  }, { passive: false });
  window.addEventListener("resize", updateTabbarOverflow);
  if (typeof ResizeObserver !== "undefined") {
    new ResizeObserver(updateTabbarOverflow).observe(bar);
  }
  updateTabbarOverflow();
}

function updateIdeStatusCount(tabName) {
  const el = document.getElementById("ide-status-count");
  if (!el) return;
  if (tabName === "projects") el.textContent = `${state.projects.length} file${state.projects.length !== 1 ? "s" : ""}`;
  else if (tabName === "experiences") el.textContent = `${state.experiences.length} file${state.experiences.length !== 1 ? "s" : ""}`;
  else if (tabName === "resume") el.textContent = `${state.resume.length} entries`;
  else if (tabName === "stack") el.textContent = `${state.skills.length} package${state.skills.length !== 1 ? "s" : ""}`;
  else el.textContent = "";
}

function initIdeStatusClock() {
  const el = document.getElementById("ide-status-clock");
  if (!el) return;
  const tick = () => {
    el.textContent = new Date().toLocaleTimeString("en-SG", { hour: "2-digit", minute: "2-digit" });
  };
  tick();
  setInterval(tick, 30000);
}

function initIdeFileTree() {
  document.querySelectorAll(".file-tree-section .file-tree-item[data-tab]").forEach((el) => {
    el.addEventListener("click", () => {
      const name = el.dataset.tab;
      switchTab(name);
      window.history.replaceState(null, "", `#${name}`);
    });
  });
}

function slugifyTitle(title) {
  return (title || "untitled").toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/(^-|-$)/g, "");
}

function renderCategoryGroupedTree(items, containerId, sectionTab, ext) {
  const target = document.getElementById(containerId);
  if (!target) return;

  const groups = {};
  items.forEach((item) => {
    const cat = item.category || "Uncategorised";
    if (!groups[cat]) groups[cat] = [];
    groups[cat].push(item);
  });
  const categories = Object.keys(groups).sort();

  target.innerHTML = categories.map((cat) => {
    const groupItems = groups[cat];
    const itemsHtml = groupItems.map((item) => {
      const filename = `${slugifyTitle(item.title)}.${ext}`;
      return `<div class="file-tree-item" data-id="${escapeHtml(item.id)}" title="${escapeHtml(filename)}"><span class="fdot ${ext}"></span><span class="ftext">${escapeHtml(filename)}</span></div>`;
    }).join("");
    const catId = slugifyTitle(cat);
    return `<div class="file-tree-subfolder" data-cat="${escapeHtml(catId)}"><span class="chev">▾</span> ${escapeHtml(cat)}<span class="fcount">${groupItems.length}</span></div>
      <div class="file-tree-subchildren" data-cat="${escapeHtml(catId)}">${itemsHtml}</div>`;
  }).join("");

  target.querySelectorAll(".file-tree-subfolder").forEach((folder) => {
    folder.addEventListener("click", () => {
      folder.classList.toggle("collapsed");
      target.querySelector(`.file-tree-subchildren[data-cat="${CSS.escape(folder.dataset.cat)}"]`)?.classList.toggle("collapsed");
    });
  });
  target.querySelectorAll(".file-tree-item").forEach((el) => {
    el.addEventListener("click", () => {
      const item = items.find((p) => String(p.id) === el.dataset.id);
      if (item) openItemTab(item, sectionTab);
    });
  });
}

function renderIdeFileTreeItems() {
  renderCategoryGroupedTree(state.projects, "tree-projects-items", "projects", "py");
  renderCategoryGroupedTree(state.experiences, "tree-experiences-items", "experiences", "md");
}

const SIDEBAR_WIDTH_KEY = "ctrlaltjay-filetree-width";

function initSidebarResize() {
  const sidebar = document.getElementById("file-tree");
  const resizer = document.getElementById("ide-sidebar-resizer");
  if (!sidebar || !resizer) return;

  const saved = parseInt(localStorage.getItem(SIDEBAR_WIDTH_KEY), 10);
  if (saved) sidebar.style.width = `${Math.min(500, Math.max(200, saved))}px`;

  let dragging = false;
  resizer.addEventListener("mousedown", (e) => {
    dragging = true;
    resizer.classList.add("dragging");
    document.body.style.userSelect = "none";
    e.preventDefault();
  });
  document.addEventListener("mousemove", (e) => {
    if (!dragging) return;
    const newWidth = Math.min(500, Math.max(200, e.clientX - sidebar.getBoundingClientRect().left));
    sidebar.style.width = `${newWidth}px`;
  });
  document.addEventListener("mouseup", () => {
    if (!dragging) return;
    dragging = false;
    resizer.classList.remove("dragging");
    document.body.style.userSelect = "";
    localStorage.setItem(SIDEBAR_WIDTH_KEY, parseInt(sidebar.style.width, 10));
  });
}

/* ===== Decorative Minimap ===== */
const MINIMAP_BLOCK_SELECTOR = "h1, h2, h3, h4, p, li, td, th, .commit-node, .ext-card, .gh-activity-item, .related-card, .focus-card, .counter-card, .modal-row";

function computeMinimapLineSpecs(root) {
  if (!root) return [];
  const candidates = Array.from(root.querySelectorAll(MINIMAP_BLOCK_SELECTOR));
  const specs = [];
  for (const el of candidates) {
    if (specs.length >= 200) break;
    if (el.offsetParent === null) continue;
    let nested = false;
    for (let p = el.parentElement; p && p !== root; p = p.parentElement) {
      if (candidates.includes(p)) { nested = true; break; }
    }
    if (nested) continue;
    const text = (el.textContent || "").trim();
    if (!text) continue;
    const len = Math.min(text.length, 160);
    const width = Math.max(15, Math.min(95, Math.round((len / 160) * 85) + 12));
    const tag = el.tagName.toLowerCase();
    let color = "var(--ide-text-faint)";
    if (/^h[1-3]$/.test(tag)) color = "var(--ide-keyword)";
    else if (tag === "h4" || el.classList.contains("ext-name")) color = "var(--ide-function)";
    else if (el.closest(".bio-highlight")) color = "var(--ide-comment)";
    else if (el.classList.contains("commit-node")) color = "var(--ide-git-added)";
    else if (el.classList.contains("ext-card")) color = "var(--ide-type)";
    specs.push({ width, color });
  }
  return specs;
}

function renderMinimapNoise(container) {
  const colors = ["var(--ide-text-faint)", "var(--ide-comment)", "var(--ide-keyword)", "var(--ide-string)", "var(--ide-function)", "var(--ide-type)"];
  let seed = 42;
  const rand = () => { seed = (seed * 1103515245 + 12345) & 0x7fffffff; return seed / 0x7fffffff; };
  let html = "";
  for (let i = 0; i < 160; i++) {
    if (rand() < 0.08) { html += `<div class="mm-gap"></div>`; continue; }
    const width = 20 + Math.floor(rand() * 75);
    const color = colors[Math.floor(rand() * colors.length)];
    html += `<div class="mm-line" style="width:${width}%;background:${color}"></div>`;
  }
  container.innerHTML = html;
}

function renderMinimapLines(container, root) {
  const specs = computeMinimapLineSpecs(root);
  if (!specs.length) {
    renderMinimapNoise(container);
    return;
  }
  container.innerHTML = specs.map((s) => `<div class="mm-line" style="width:${s.width}%;background:${s.color}"></div>`).join("");
}

function refreshMinimap() {
  const linesEl = document.getElementById("ide-minimap-lines");
  if (!linesEl) return;
  renderMinimapLines(linesEl, document.querySelector(".tab-panel.active"));
}

function initMinimap() {
  const minimap = document.getElementById("ide-minimap");
  const linesEl = document.getElementById("ide-minimap-lines");
  const viewportEl = document.getElementById("ide-minimap-viewport");
  const scrollEl = document.getElementById("ide-panel-scroll");
  if (!minimap || !linesEl || !viewportEl || !scrollEl) return;

  renderMinimapLines(linesEl, document.querySelector(".tab-panel.active"));

  const updateViewport = () => {
    const ratio = scrollEl.scrollHeight ? scrollEl.clientHeight / scrollEl.scrollHeight : 1;
    const topRatio = scrollEl.scrollHeight ? scrollEl.scrollTop / scrollEl.scrollHeight : 0;
    viewportEl.style.height = `${Math.min(100, ratio * 100)}%`;
    viewportEl.style.top = `${topRatio * 100}%`;
  };

  updateViewport();
  scrollEl.addEventListener("scroll", updateViewport, { passive: true });
  window.addEventListener("resize", updateViewport);
  if (typeof ResizeObserver !== "undefined") {
    new ResizeObserver(updateViewport).observe(scrollEl);
  }

  minimap.addEventListener("click", (e) => {
    const rect = minimap.getBoundingClientRect();
    const clickRatio = (e.clientY - rect.top) / rect.height;
    scrollEl.scrollTo({ top: clickRatio * scrollEl.scrollHeight - scrollEl.clientHeight / 2, behavior: "smooth" });
  });
}

function openItemTab(item, sectionTab) {
  const tabId = `item:${item.id}`;
  const ext = sectionTab === "projects" ? "py" : "md";
  const filename = `${slugifyTitle(item.title)}.${ext}`;
  state.ideItemMeta = state.ideItemMeta || {};
  state.ideItemMeta[tabId] = { label: filename, icon: ext, sectionTab, itemId: item.id };
  if (!state.ideOpenTabs.includes(tabId)) state.ideOpenTabs.push(tabId);

  renderItemViewer(item);
  switchTab("item-viewer");
  renderIdeTabbar(tabId);

  showFileTreeSection(sectionTab);
  document.querySelectorAll(".file-tree-item.active").forEach((el) => el.classList.remove("active"));
  document.querySelectorAll(`.file-tree-item[data-id="${item.id}"]`).forEach((el) => el.classList.add("active"));
  const sectionEl = document.getElementById("ide-status-section");
  if (sectionEl) sectionEl.textContent = `${sectionTab}/${filename}`;
  updateIdeStatusCount(sectionTab);
  refreshMinimap();
}

function openIdeTabByName(name) {
  if (name.startsWith("item:")) {
    const meta = state.ideItemMeta?.[name];
    if (!meta) return;
    const item = findItemById(meta.itemId);
    if (item) openItemTab(item, meta.sectionTab);
    return;
  }
  switchTab(name);
  window.history.replaceState(null, "", `#${name}`);
}

function closeIdeTab(name, activeTab) {
  state.ideOpenTabs = state.ideOpenTabs.filter((t) => t !== name);
  if (state.ideItemMeta?.[name]) delete state.ideItemMeta[name];
  if (state.ideOpenTabs.length === 0) state.ideOpenTabs = ["about"];
  if (name === activeTab) {
    openIdeTabByName(state.ideOpenTabs[state.ideOpenTabs.length - 1]);
  } else {
    renderIdeTabbar(activeTab);
  }
}

function closeItemTabIfOpen(itemId) {
  const tabId = `item:${itemId}`;
  if (!state.ideOpenTabs.includes(tabId)) return;
  const activeTab = document.querySelector(".ide-tab.active")?.dataset.tab || tabId;
  closeIdeTab(tabId, activeTab);
}

function compareBySort(a, b, mode) {
  const titleA = (a.title || "").toLowerCase();
  const titleB = (b.title || "").toLowerCase();
  const createdA = new Date(a.created_at || 0).getTime();
  const createdB = new Date(b.created_at || 0).getTime();
  const updatedA = new Date(a.updated_at || 0).getTime();
  const updatedB = new Date(b.updated_at || 0).getTime();

  if (mode === "title_asc") return titleA.localeCompare(titleB);
  if (mode === "title_desc") return titleB.localeCompare(titleA);
  if (mode === "created_asc") return createdA - createdB;
  if (mode === "created_desc") return createdB - createdA;
  if (mode === "updated_asc") return updatedA - updatedB;
  return updatedB - updatedA;
}

function uniqueCategories(items) {
  const cats = [...new Set(items.map((item) => item.category).filter(Boolean))].sort();
  const result = ["All"];
  if (items.some((item) => !item.category)) result.push("Uncategorised");
  return result.concat(cats);
}

function uniqueSubsections(items) {
  const values = new Set();
  items.forEach((item) => {
    if (item.subsection) values.add(item.subsection);
    else if (item.category) values.add(item.category);
  });
  const subs = [...values].sort();
  const result = ["All"];
  if (items.some((item) => !item.subsection && !item.category)) result.push("Uncategorised");
  return result.concat(subs);
}

function highlightText(text, query) {
  const safeText = escapeHtml(text);
  if (!query || !text) return safeText;
  const escapedQuery = escapeHtml(query).replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  return safeText.replace(new RegExp(`(${escapedQuery})`, "gi"), '<mark class="search-highlight">$1</mark>');
}

function buildCard(item, highlightQuery = "") {
  const card = document.createElement("article");
  card.className = "card";
  card.tabIndex = 0;

  // Tooltip preview
  if (item.summary) card.title = item.summary;

  let img = null;
  if (item.image_path) {
    img = document.createElement("img");
    img.src = item.image_path;
    img.alt = item.title;
    img.loading = "lazy";
    img.style.opacity = "0";
    img.style.transition = "opacity 0.3s ease";
    img.addEventListener("load", () => { img.style.opacity = "1"; });
    img.addEventListener("error", () => { img.style.opacity = "1"; });
  }

  const content = document.createElement("div");
  content.className = "card-content";

  const title = document.createElement("h4");
  if (highlightQuery) {
    title.innerHTML = highlightText(item.title, highlightQuery);
  } else {
    title.textContent = item.title;
  }

  const tag = document.createElement("span");
  tag.className = "tag";
  tag.textContent = item.tag || item.category;

  content.appendChild(title);
  content.appendChild(tag);

  // Date display
  if (item.date_value) {
    const dateEl = document.createElement("span");
    dateEl.className = "card-date";
    const d = new Date(item.date_value);
    dateEl.textContent = d.toLocaleDateString("en-SG", { month: "short", year: "numeric" });
    content.appendChild(dateEl);
  }

  // Status badge
  if (item.status) {
    const badge = document.createElement("span");
    badge.className = "status-badge status-badge--" + item.status.toLowerCase().replace(/\s+/g, "-");
    badge.textContent = item.status;
    content.appendChild(badge);
  }

  // Skill tags
  const itemSkills = parseSkills(item.skills);
  if (itemSkills.length > 0) {
    const skillWrap = document.createElement("div");
    skillWrap.className = "card-skills";
    itemSkills.slice(0, 4).forEach((s) => {
      const chip = document.createElement("span");
      chip.className = "card-skill-chip";
      chip.textContent = s;
      skillWrap.appendChild(chip);
    });
    if (itemSkills.length > 4) {
      const more = document.createElement("span");
      more.className = "card-skill-chip card-skill-more";
      more.textContent = `+${itemSkills.length - 4}`;
      skillWrap.appendChild(more);
    }
    content.appendChild(skillWrap);
  }

  if (img) card.appendChild(img);
  card.appendChild(content);

  card.addEventListener("click", () => openItemTab(item, item.section === "experience" ? "experiences" : "projects"));

  return card;
}

/* ===== Skills helpers ===== */
function parseSkills(val) {
  if (!val) return [];
  if (Array.isArray(val)) return val.filter(Boolean);
  return val.split(",").map((s) => s.trim()).filter(Boolean);
}

function renderSkillsFilter(containerId, items, sectionPrefix) {
  const container = document.getElementById(containerId);
  if (!container) return;
  // Collect all unique skills used by items in this section
  const usedSkills = new Set();
  items.forEach((item) => {
    parseSkills(item.skills).forEach((s) => usedSkills.add(s));
  });
  const sorted = [...usedSkills].sort();
  container.innerHTML = "";
  if (sorted.length === 0) {
    container.style.display = "none";
    return;
  }
  container.style.display = "";
  // Label
  const label = document.createElement("span");
  label.className = "text-xs text-ink-muted font-semibold mr-1";
  label.innerHTML = '<ion-icon name="pricetag-outline" class="align-middle mr-0.5"></ion-icon> Skills:';
  container.appendChild(label);
  // "All" button
  const allBtn = document.createElement("button");
  allBtn.type = "button";
  allBtn.className = "skill-filter-btn active";
  allBtn.dataset.skill = "all";
  allBtn.textContent = "All";
  container.appendChild(allBtn);
  // One button per skill
  sorted.forEach((skill) => {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "skill-filter-btn";
    btn.dataset.skill = skill;
    btn.textContent = skill;
    container.appendChild(btn);
  });
}

function populateSkillsPicker(selectedSkills = []) {
  const picker = document.getElementById("admin-item-skills-picker");
  const hidden = document.getElementById("admin-item-skills");
  if (!picker || !hidden) return;
  picker.innerHTML = "";
  const selected = new Set(selectedSkills.map((s) => s.toLowerCase()));
  const allSkills = state.skills.map((s) => s.name).filter(Boolean).sort();
  if (allSkills.length === 0) {
    picker.innerHTML = '<span class="text-xs text-ink-muted">No skills defined yet.</span>';
    hidden.value = "";
    return;
  }
  function syncHidden() {
    const checked = [...picker.querySelectorAll("input:checked")].map((cb) => cb.value);
    hidden.value = checked.join(",");
  }
  allSkills.forEach((name) => {
    const label = document.createElement("label");
    label.className = "skill-picker-chip";
    const cb = document.createElement("input");
    cb.type = "checkbox";
    cb.value = name;
    cb.checked = selected.has(name.toLowerCase());
    cb.addEventListener("change", syncHidden);
    const span = document.createElement("span");
    span.textContent = name;
    label.appendChild(cb);
    label.appendChild(span);
    picker.appendChild(label);
  });
  syncHidden();
}

function renderCategorySelect(elementId, categories) {
  const select = document.getElementById(elementId);
  select.innerHTML = "";
  categories.forEach((category) => {
    const option = document.createElement("option");
    option.value = category;
    option.textContent = category;
    select.appendChild(option);
  });
}

function renderSubsectionNav(navId, categories, items) {
  const nav = document.getElementById(navId);
  if (!nav) return;
  
  nav.innerHTML = "";
  categories.forEach((category, index) => {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "subsection-btn shrink-0";
    if (index === 0) btn.classList.add("active");
    btn.dataset.subsection = category;

    // Count items for badge
    let count;
    if (category === "All") {
      count = items.length;
    } else if (category === "Uncategorised") {
      count = items.filter((it) => !it.category && !it.subsection).length;
    } else {
      count = items.filter((it) => it.category === category || it.subsection === category).length;
    }
    btn.textContent = `${category} (${count})`;
    nav.appendChild(btn);
  });

  // Favourites pill
  const favIds = getFavorites();
  const favCount = items.filter((i) => favIds.includes(i.id)).length;
  if (favCount > 0) {
    const favBtn = document.createElement("button");
    favBtn.type = "button";
    favBtn.className = "subsection-btn shrink-0 fav-pill";
    favBtn.dataset.subsection = "★ Favourites";
    favBtn.textContent = `★ Favourites (${favCount})`;
    nav.insertBefore(favBtn, nav.children[1]);
  }
}

const PAGE_SIZE = 12;
const shownCounts = {};  // track pagination per grid

function renderSection(items, categoryId, sortId, targetGridId, subsectionFilter = null, searchId = null, searchFieldId = null, skillFilter = null) {
  const selectedCategory = categoryId ? document.getElementById(categoryId).value : "All";
  const sortMode = document.getElementById(sortId).value;
  const target = document.getElementById(targetGridId);
  const searchQuery = searchId ? (document.getElementById(searchId)?.value || "").trim().toLowerCase() : "";
  const searchField = searchFieldId ? (document.getElementById(searchFieldId)?.value || "all") : "all";

  let filtered = items.filter(
    (item) => selectedCategory === "All" || item.category === selectedCategory
  );

  // Apply subsection filter (including favourites)
  if (subsectionFilter === "★ Favourites") {
    const favSet = new Set(getFavorites());
    filtered = filtered.filter((item) => favSet.has(item.id));
  } else if (subsectionFilter && subsectionFilter.toLowerCase() !== "all") {
    if (subsectionFilter === "Uncategorised") {
      filtered = filtered.filter((item) => !item.category && !item.subsection);
    } else {
      filtered = filtered.filter((item) => item.category === subsectionFilter || item.subsection === subsectionFilter);
    }
  }

  // Apply skill filter
  if (skillFilter && skillFilter !== "all") {
    filtered = filtered.filter((item) => {
      const itemSkills = parseSkills(item.skills);
      return itemSkills.some((s) => s.toLowerCase() === skillFilter.toLowerCase());
    });
  }

  // Apply text search (field-targeted)
  if (searchQuery) {
    filtered = filtered.filter((item) => {
      let haystack;
      if (searchField === "all") {
        haystack = [item.title, item.summary, item.description, item.category, item.tag, item.deliverables, item.challenges, item.extra_notes].filter(Boolean).join(" ").toLowerCase();
      } else {
        haystack = (item[searchField] || "").toLowerCase();
      }
      return haystack.includes(searchQuery);
    });
  }

  filtered = filtered.sort((a, b) => compareBySort(a, b, sortMode));

  target.innerHTML = "";
  if (filtered.length === 0) {
    target.innerHTML = `<div class="empty-state" style="grid-column:1/-1"><ion-icon name="search-outline"></ion-icon><p>${searchQuery ? "No results for \u201c" + escapeHtml(searchQuery) + "\u201d" : "No items in this category yet."}</p></div>`;
    shownCounts[targetGridId] = 0;
    return;
  }

  // Pin favorites to top
  const favIds = new Set(getFavorites());
  if (favIds.size > 0) {
    const pinned = filtered.filter((i) => favIds.has(i.id));
    const rest = filtered.filter((i) => !favIds.has(i.id));
    filtered = [...pinned, ...rest];
  }

  // Pagination: show only first PAGE_SIZE (or previously expanded count)
  const limit = shownCounts[targetGridId] || PAGE_SIZE;
  const visible = filtered.slice(0, limit);

  // Result count indicator
  const countEl = document.createElement("div");
  countEl.className = "result-count";
  if (searchQuery || (subsectionFilter && subsectionFilter.toLowerCase() !== "all")) {
    countEl.textContent = `Showing ${Math.min(limit, filtered.length)} of ${filtered.length} result${filtered.length !== 1 ? "s" : ""}`;
  } else {
    countEl.textContent = `${filtered.length} item${filtered.length !== 1 ? "s" : ""}`;
  }
  target.appendChild(countEl);

  visible.forEach((item) => {
    target.appendChild(buildCard(item, searchQuery));
  });

  // Observe cards for entrance animation
  observeCards(target);

  // Show More button
  if (filtered.length > limit) {
    appendShowMore(target, filtered, limit, searchQuery, targetGridId, countEl);
  }
}

function appendShowMore(target, filtered, currentLimit, searchQuery, targetGridId, countEl) {
  const remaining = filtered.length - currentLimit;
  const wrap = document.createElement("div");
  wrap.className = "show-more-wrap";
  wrap.innerHTML = `<button class="show-more-btn"><ion-icon name="chevron-down-outline"></ion-icon> Show ${Math.min(remaining, PAGE_SIZE)} more of ${remaining} remaining</button>`;
  wrap.querySelector("button").addEventListener("click", () => {
    wrap.remove();
    const newLimit = currentLimit + PAGE_SIZE;
    shownCounts[targetGridId] = newLimit;
    const nextBatch = filtered.slice(currentLimit, newLimit);
    nextBatch.forEach((item) => target.appendChild(buildCard(item, searchQuery)));
    observeCards(target);
    if (state.isAdmin) {
      addBulkCheckboxes(target);
      addFavoriteButtons();
    }
    if (countEl) {
      countEl.textContent = `Showing ${Math.min(newLimit, filtered.length)} of ${filtered.length} result${filtered.length !== 1 ? "s" : ""}`;
    }
    if (filtered.length > newLimit) {
      appendShowMore(target, filtered, newLimit, searchQuery, targetGridId, countEl);
    }
  });
  target.appendChild(wrap);
}

function rowToHTML(label, value) {
  if (!value) {
    return "";
  }
  return `<div class="modal-row"><strong>${escapeHtml(label)}:</strong> ${escapeHtml(value)}</div>`;
}

function renderItemViewer(item) {
  state.modalItem = item;
  const shell = document.getElementById("item-viewer");
  const image = document.getElementById("modal-image");
  const title = document.getElementById("modal-title");
  const tag = document.getElementById("modal-tag");
  const body = document.getElementById("modal-body");
  const link = document.getElementById("modal-link");

  if (item.image_path) {
    image.src = item.image_path;
    image.style.display = "";
  } else {
    image.src = "";
    image.style.display = "none";
  }
  image.alt = item.title;
  title.textContent = item.title;
  tag.textContent = item.tag || item.category;

  body.innerHTML = [
    rowToHTML("Summary", item.summary),
    rowToHTML("Description", item.description),
    rowToHTML(item.date_label || "Date", item.date_value),
    rowToHTML("Deliverables", item.deliverables),
    rowToHTML("Challenges", item.challenges),
    rowToHTML("Future Improvements", item.future_improvements),
    rowToHTML("Notes", item.extra_notes),
  ].join("");

  // Reading time & word count
  const readTimeEl = document.getElementById("modal-read-time");
  if (readTimeEl) {
    const allText = [item.summary, item.description, item.deliverables, item.challenges, item.future_improvements, item.extra_notes].filter(Boolean).join(" ");
    const wordCount = allText.split(/\s+/).filter(Boolean).length;
    const minutes = Math.max(1, Math.ceil(wordCount / 200));
    readTimeEl.textContent = `${wordCount} words · ${minutes} min read`;
    readTimeEl.style.display = wordCount > 0 ? "" : "none";
  }

  // Apply markdown rendering to modal rows
  body.querySelectorAll(".modal-row").forEach((row) => {
    const strong = row.querySelector("strong");
    if (!strong) return;
    const label = strong.outerHTML;
    const text = row.innerHTML.replace(label, "").trim();
    row.innerHTML = label + " " + renderMarkdown(text);
  });

  // Collapsible long sections
  body.querySelectorAll(".modal-row").forEach((row) => {
    if (row.textContent.length > 300) {
      row.classList.add("collapsible-row");
      row.dataset.expanded = "false";
      const toggle = document.createElement("button");
      toggle.type = "button";
      toggle.className = "collapse-toggle";
      toggle.textContent = "Show more";
      toggle.addEventListener("click", (e) => {
        e.stopPropagation();
        const expanded = row.dataset.expanded === "true";
        row.dataset.expanded = String(!expanded);
        toggle.textContent = expanded ? "Show more" : "Show less";
      });
      row.appendChild(toggle);
    }
  });

  // Skill tags in modal (click to filter)
  const existingSkillRow = shell.querySelector(".modal-skills-row");
  if (existingSkillRow) existingSkillRow.remove();
  const itemSkills = parseSkills(item.skills);
  if (itemSkills.length > 0) {
    const row = document.createElement("div");
    row.className = "modal-skills-row";
    itemSkills.forEach((s) => {
      const chip = document.createElement("span");
      chip.className = "modal-skill-chip";
      chip.textContent = s;
      chip.style.cursor = "pointer";
      chip.title = `Filter by \"${s}\"`;
      chip.addEventListener("click", (e) => {
        e.stopPropagation();
        const tab = item.section === "experience" ? "experiences" : "projects";
        switchTab(tab);
        const filterContainer = document.getElementById(`${tab}-skills-filter`);
        if (filterContainer) {
          filterContainer.querySelectorAll(".skill-filter-btn").forEach((b) => {
            b.classList.toggle("active", b.dataset.skill === s);
          });
        }
        const subNav = document.getElementById(`${tab}-subsection-nav`);
        if (subNav) {
          subNav.querySelectorAll(".subsection-btn").forEach((b) => b.classList.remove("active"));
          const allBtn = subNav.querySelector('.subsection-btn[data-subsection="All"]');
          if (allBtn) allBtn.classList.add("active");
        }
        if (tab === "projects") state.rerenderProjects();
        else state.rerenderExperiences();
        document.getElementById(`${tab}-grid`)?.scrollIntoView({ behavior: "smooth", block: "start" });
      });
      row.appendChild(chip);
    });
    body.parentNode.insertBefore(row, body.nextSibling);
  }

  // Related items
  renderRelatedItems(item);

  if (item.external_link) {
    link.href = item.external_link;
    link.style.display = "inline-block";
  } else {
    link.style.display = "none";
  }

  // Credential verification link
  const credLink = document.getElementById("modal-credential-link");
  if (credLink) {
    if (item.credential_url) {
      credLink.href = item.credential_url;
      credLink.style.display = "inline-flex";
    } else {
      credLink.style.display = "none";
    }
  }

  // Image carousel
  setupCarousel(item);

  // Update share buttons
  updateShareLinks(item);

  // Deep link: update URL hash
  if (item.id) {
    window.history.replaceState(null, "", `#item/${item.id}`);
  }

  // Track recently viewed
  trackRecentlyViewed(item.id);

  // Copy item ID (admin)
  const copyIdBtn = document.getElementById("modal-copy-id-btn");
  if (copyIdBtn) {
    copyIdBtn.onclick = (e) => {
      e.stopPropagation();
      navigator.clipboard.writeText(item.id).then(() => showToast("Item ID copied.", "success")).catch(() => showToast("Copy failed.", "error"));
    };
  }

  // Export single item as JSON
  const exportItemBtn = document.getElementById("modal-export-item-btn");
  if (exportItemBtn) {
    exportItemBtn.onclick = (e) => {
      e.stopPropagation();
      const blob = new Blob([JSON.stringify(item, null, 2)], { type: "application/json" });
      const dlUrl = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = dlUrl;
      a.download = `${(item.title || "item").replace(/[^a-z0-9]/gi, "_")}.json`;
      a.click();
      URL.revokeObjectURL(dlUrl);
      showToast("Item exported.", "success");
    };
  }
}

function renderResume() {
  const educationTarget = document.getElementById("resume-education");
  const workTarget = document.getElementById("resume-work");

  educationTarget.innerHTML = "";
  workTarget.innerHTML = "";

  const education = state.resume.filter((item) => item.lane === "education");
  const work = state.resume.filter((item) => item.lane === "work");

  education.forEach((item) => educationTarget.appendChild(buildCommitNode(item)));
  work.forEach((item) => workTarget.appendChild(buildCommitNode(item)));
}

function shortCommitHash(id) {
  return (id || "0000000").replace(/-/g, "").slice(0, 7).padEnd(7, "0");
}

function buildCommitNode(item) {
  const isHead = /present|current/i.test(item.period || "");

  const li = document.createElement("li");
  li.className = `commit-node${isHead ? " commit-node--head" : ""}`;

  const topRow = document.createElement("div");
  topRow.className = "commit-top-row";

  const hash = document.createElement("span");
  hash.className = "commit-hash";
  hash.textContent = shortCommitHash(item.id);
  topRow.appendChild(hash);

  const msg = document.createElement("span");
  msg.className = "commit-msg";
  msg.textContent = item.title;
  topRow.appendChild(msg);

  if (isHead) {
    const badge = document.createElement("span");
    badge.className = "commit-head-badge";
    badge.textContent = "HEAD";
    topRow.appendChild(badge);
  }

  li.appendChild(topRow);

  const metaText = [item.subtitle, item.period].filter(Boolean).join(" · ");
  if (metaText) {
    const meta = document.createElement("div");
    meta.className = "commit-meta";
    meta.textContent = metaText;
    li.appendChild(meta);
  }

  if (item.description) {
    const body = document.createElement("p");
    body.className = "commit-body";
    body.textContent = item.description;
    li.appendChild(body);
  }

  return li;
}

const EXT_TIER_COLOR = {
  "Primary Stack": "var(--ide-accent-strong)",
  "Experienced": "var(--ide-type)",
  "Familiar": "var(--ide-text-faint)",
};

function renderSkills() {
  const target = document.getElementById("skills-grid");
  target.innerHTML = "";

  const tierOrder = ["Primary Stack", "Experienced"];
  const grouped = {};
  state.skills.forEach((skill) => {
    let tier = skill.focus || "Other";
    if (tier === "Familiar") tier = "Experienced";
    if (!grouped[tier]) grouped[tier] = [];
    grouped[tier].push(skill);
  });

  tierOrder.forEach((tier) => {
    const skills = grouped[tier];
    if (!skills || skills.length === 0) return;

    const section = document.createElement("div");
    section.className = "ext-tier mb-6";

    const heading = document.createElement("h4");
    heading.className = "ext-tier-heading";
    heading.textContent = tier;
    section.appendChild(heading);

    const list = document.createElement("div");
    list.className = "ext-list";

    skills
      .sort((a, b) => (a.sort_order || 0) - (b.sort_order || 0))
      .forEach((skill) => list.appendChild(buildExtensionCard(skill, tier)));

    section.appendChild(list);
    target.appendChild(section);
  });
}

function buildExtensionCard(skill, tier) {
  const card = document.createElement("div");
  card.className = "ext-card";
  card.dataset.name = (skill.name || "").toLowerCase();

  const icon = document.createElement("div");
  icon.className = "ext-icon";
  icon.style.background = EXT_TIER_COLOR[tier] || "var(--ide-text-faint)";
  icon.textContent = (skill.name || "?").trim().charAt(0).toUpperCase();

  const info = document.createElement("div");
  info.className = "ext-info";

  const titleRow = document.createElement("div");
  titleRow.className = "ext-title-row";
  const name = document.createElement("span");
  name.className = "ext-name";
  name.textContent = skill.name;
  const badge = document.createElement("span");
  badge.className = "ext-badge";
  badge.textContent = "Installed";
  titleRow.appendChild(name);
  titleRow.appendChild(badge);

  const publisher = document.createElement("div");
  publisher.className = "ext-publisher";
  publisher.textContent = `ctrlaltjay.${slugifyTitle(tier)}`;

  const level = Math.max(0, Math.min(100, Number(skill.level) || 0));
  const barRow = document.createElement("div");
  barRow.className = "ext-bar-row";
  const bar = document.createElement("div");
  bar.className = "ext-bar";
  const fill = document.createElement("div");
  fill.className = "ext-bar-fill";
  fill.style.width = `${level}%`;
  bar.appendChild(fill);
  const pct = document.createElement("span");
  pct.className = "ext-bar-pct";
  pct.textContent = `${level}%`;
  barRow.appendChild(bar);
  barRow.appendChild(pct);

  info.appendChild(titleRow);
  info.appendChild(publisher);
  info.appendChild(barRow);

  card.appendChild(icon);
  card.appendChild(info);
  return card;
}

function initStackSearch() {
  const input = document.getElementById("stack-search");
  if (!input) return;
  input.addEventListener("input", () => {
    const q = input.value.trim().toLowerCase();
    document.querySelectorAll("#skills-grid .ext-tier").forEach((tierEl) => {
      let visibleCount = 0;
      tierEl.querySelectorAll(".ext-card").forEach((card) => {
        const match = !q || card.dataset.name.includes(q);
        card.style.display = match ? "" : "none";
        if (match) visibleCount++;
      });
      tierEl.style.display = visibleCount ? "" : "none";
    });
  });
}

async function fetchData() {
  try {
    const response = await fetch("/api/public-data");
    if (!response.ok) throw new Error(`public-data request failed: ${response.status}`);
    const payload = await response.json();
    state.projects = payload.projects || [];
    state.experiences = payload.experiences || [];
    state.resume = payload.resume || [];
    state.skills = payload.skills || [];
  } catch (err) {
    console.error("Failed to load portfolio data", err);
    state.projects = [];
    state.experiences = [];
    state.resume = [];
    state.skills = [];
    state.dataLoadFailed = true;
  }
}

function setAdminMode(enabled) {
  state.isAdmin = Boolean(enabled);
  document.querySelectorAll(".admin-only").forEach((element) => {
    element.hidden = !state.isAdmin;
  });
  const loginBtn = document.getElementById("open-admin-auth");
  const logoutBtn = document.getElementById("admin-logout-btn");
  if (loginBtn) loginBtn.hidden = state.isAdmin;
  if (logoutBtn) logoutBtn.hidden = !state.isAdmin;
  if (state.isAdmin) {
    loadResumeKey();
    renderDeletedItems();
  }
  updateDraftIndicator();
}

function findItemById(itemId) {
  return [...state.projects, ...state.experiences].find((item) => String(item.id) === String(itemId)) || null;
}

const CATEGORY_OPTIONS = {
  project: ["AI / ML", "Cloud & DevOps", "Community", "Innovation", "Operations", "Web Development"],
  experience: ["Achievements", "Career", "Certifications", "Events", "External Roles", "Testimonials", "Volunteering"],
};

function populateCategoryDropdown(section, selectedValue) {
  const select = document.getElementById("admin-item-category");
  select.innerHTML = '<option value="">Select a category</option>';
  const options = CATEGORY_OPTIONS[section] || [];
  options.forEach((cat) => {
    const opt = document.createElement("option");
    opt.value = cat;
    opt.textContent = cat;
    if (cat === selectedValue) opt.selected = true;
    select.appendChild(opt);
  });
}

function openAdminItemModal(item = null, section = "project") {
  const modal = document.getElementById("admin-item-modal");
  const form = document.getElementById("admin-item-form");
  const title = document.getElementById("admin-item-title");
  const submit = document.getElementById("admin-item-submit");
  const feedback = document.getElementById("admin-item-feedback");
  const sectionFieldGroup = document.getElementById("section-field-group");
  const sectionField = document.getElementById("admin-item-section");

  if (!modal || !form || !title || !submit || !feedback) {
    return;
  }

  form.reset();
  feedback.textContent = "";

  // Track the current section for this create/edit action
  state.currentSection = section;

  const effectiveSection = item?.section || section;

  document.getElementById("admin-item-id").value = item?.id || "";
  sectionField.value = effectiveSection;
  populateCategoryDropdown(effectiveSection, item?.category || item?.subsection || "");
  document.getElementById("admin-item-title-input").value = item?.title || "";
  document.getElementById("admin-item-summary").value = item?.summary || "";
  document.getElementById("admin-item-description").value = item?.description || "";
  document.getElementById("admin-item-date-label").value = item?.date_label || "";
  document.getElementById("admin-item-date-value").value = item?.date_value || "";
  document.getElementById("admin-item-deliverables").value = item?.deliverables || "";
  document.getElementById("admin-item-challenges").value = item?.challenges || "";
  document.getElementById("admin-item-future").value = item?.future_improvements || "";
  document.getElementById("admin-item-extra").value = item?.extra_notes || "";
  document.getElementById("admin-item-image-path").value = item?.image_path || "";
  const imageInfo = document.getElementById("admin-item-image-info");
  if (imageInfo) imageInfo.textContent = item?.image_path ? `Current: ${item.image_path.split('/').pop()}` : "";
  const imagePreview = document.getElementById("admin-item-image-preview");
  if (imagePreview) {
    if (item?.image_path) {
      imagePreview.src = item.image_path;
      imagePreview.classList.remove("hidden");
    } else {
      imagePreview.src = "";
      imagePreview.classList.add("hidden");
    }
  }
  document.getElementById("admin-item-link").value = item?.external_link || "";

  // New fields
  document.getElementById("admin-item-status").value = item?.status || "";
  document.getElementById("admin-item-credential-url").value = item?.credential_url || "";
  const addPreview = document.getElementById("admin-item-additional-preview");
  const addHidden = document.getElementById("admin-item-existing-additional");
  if (addPreview) addPreview.innerHTML = "";
  if (addHidden) addHidden.value = item?.additional_images || "";
  if (item?.additional_images && addPreview) {
    item.additional_images.split(",").filter(Boolean).forEach((src) => {
      const img = document.createElement("img");
      img.src = src.trim();
      img.className = "h-16 w-16 object-cover rounded-lg border border-white/[0.06]";
      addPreview.appendChild(img);
    });
  }

  // Populate skills picker
  populateSkillsPicker(parseSkills(item?.skills));

  // Show/hide section field and set modal title
  if (item) {
    sectionFieldGroup.style.display = "grid";
    title.textContent = "Edit Item";
    submit.textContent = "Save Changes";
  } else {
    sectionFieldGroup.style.display = "none";
    title.textContent = section === "experience" ? "Create New Experience" : "Create New Project";
    submit.textContent = "Create Item";

    // Restore draft if available
    const draft = restoreDraft();
    if (draft) {
      Object.entries(draft).forEach(([key, val]) => {
        const el = form.elements[key];
        if (el && val) el.value = val;
      });
      // Re-populate category dropdown with drafted values
      populateCategoryDropdown(sectionField.value || effectiveSection, draft.category || "");
      // Show draft indicator
      const badge = document.createElement("span");
      badge.className = "draft-badge";
      badge.textContent = "Draft restored";
      title.appendChild(badge);
      setTimeout(() => badge.remove(), 3000);
    }
  }

  modal.classList.add("active");
  modal.setAttribute("aria-hidden", "false");
}

function closeAdminItemModal() {
  const modal = document.getElementById("admin-item-modal");
  if (!modal) return;
  modal.classList.remove("active");
  modal.setAttribute("aria-hidden", "true");
}

async function saveAdminItem(formData, itemId) {
  const url = itemId ? `/api/admin/items/${itemId}` : "/api/admin/items";
  const method = itemId ? "PUT" : "POST";

  const response = await fetch(url, {
    method,
    body: formData,
  });

  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(payload.error || payload.message || "Failed to save item.");
  }
}

function initInlineAdminEditor() {
  const createProjectBtn = document.getElementById("create-project-btn");
  const createExperienceBtn = document.getElementById("create-experience-btn");
  const editBtn = document.getElementById("modal-edit-btn");
  const deleteBtn = document.getElementById("modal-delete-btn");
  const adminItemForm = document.getElementById("admin-item-form");
  const adminItemFeedback = document.getElementById("admin-item-feedback");

  if (!createProjectBtn || !createExperienceBtn || !editBtn || !adminItemForm || !adminItemFeedback) {
    return;
  }

  // Dynamic category options when section changes
  document.getElementById("admin-item-section").addEventListener("change", (e) => {
    populateCategoryDropdown(e.target.value, "");
  });

  // Image preview on file select
  const imageInput = document.getElementById("admin-item-image");
  const imagePreview = document.getElementById("admin-item-image-preview");
  if (imageInput && imagePreview) {
    imageInput.addEventListener("change", () => {
      const file = imageInput.files[0];
      if (file) {
        const reader = new FileReader();
        reader.onload = (e) => {
          imagePreview.src = e.target.result;
          imagePreview.classList.remove("hidden");
        };
        reader.readAsDataURL(file);
      } else {
        imagePreview.classList.add("hidden");
      }
    });
  }

  createProjectBtn.addEventListener("click", () => {
    if (!state.isAdmin) return;
    openAdminItemModal(null, "project");
  });

  createExperienceBtn.addEventListener("click", () => {
    if (!state.isAdmin) return;
    openAdminItemModal(null, "experience");
  });

  editBtn.addEventListener("click", () => {
    if (!state.isAdmin || !state.modalItem) {
      return;
    }
    openAdminItemModal(state.modalItem, state.modalItem.section || "project");
  });

  // Delete button
  if (deleteBtn) {
    deleteBtn.addEventListener("click", async () => {
      if (!state.isAdmin || !state.modalItem) return;
      const item = state.modalItem;
      const confirmed = await showConfirm("Delete Item", `This will move "${item.title}" to Recently Deleted.`, { requireText: item.title, confirmLabel: "Delete" });
      if (!confirmed) return;
      try {
        const res = await fetch(`/api/admin/items/${item.id}`, { method: "DELETE" });
        if (!res.ok) throw new Error("Delete failed");
        closeItemTabIfOpen(item.id);
        await fetchData();
        wireProjectControls();
        logActivity("Delete", item.title);
        showToast("Item moved to Recently Deleted.", "success");
        renderDeletedItems();
      } catch (err) {
        showToast("Failed to delete item.", "error");
      }
    });
  }

  // Clone button
  const cloneBtn = document.getElementById("modal-clone-btn");
  if (cloneBtn) {
    cloneBtn.addEventListener("click", () => {
      if (!state.isAdmin || !state.modalItem) return;
      const item = { ...state.modalItem };
      const section = item.section || "project";
      item.title = item.title + " (Copy)";
      openAdminItemModal(item, section);
      document.getElementById("admin-item-id").value = "";
      const titleEl = document.getElementById("admin-item-title");
      if (titleEl) titleEl.textContent = "Clone Item";
      const submitEl = document.getElementById("admin-item-submit");
      if (submitEl) submitEl.textContent = "Create Clone";
      showToast("Fields pre-filled from original. Edit and save.", "info");
    });
  }

  document.querySelectorAll("[data-close-admin-item]").forEach((element) => {
    element.addEventListener("click", closeAdminItemModal);
  });

  adminItemForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (!state.isAdmin) {
      return;
    }

    const itemId = document.getElementById("admin-item-id").value;
    
    // For new items, set section from state.currentSection
    if (!itemId && state.currentSection) {
      document.getElementById("admin-item-section").value = state.currentSection;
    }

    const formData = new FormData(adminItemForm);

    // Duplicate title warning for new items
    if (!itemId) {
      const newTitle = (formData.get("title") || "").trim().toLowerCase();
      if (newTitle) {
        const allItems = [...state.projects, ...state.experiences];
        const duplicate = allItems.find((i) => i.title.toLowerCase() === newTitle);
        if (duplicate) {
          const proceed = await showConfirm("Duplicate Title", `An item titled "${duplicate.title}" already exists. Create anyway?`);
          if (!proceed) {
            adminItemFeedback.textContent = "";
            return;
          }
        }
      }
    }

    adminItemFeedback.textContent = "Saving...";

    try {
      await saveAdminItem(formData, itemId);
      await fetchData();
      wireProjectControls();
      closeAdminItemModal();
      clearDraft();
      const itemTitle = formData.get("title") || "item";
      logActivity(itemId ? "Edit" : "Create", itemTitle);
      showToast(itemId ? "Item updated." : "Item created.", "success");
      if (state.modalItem?.id && itemId) {
        const refreshedItem = findItemById(itemId);
        if (refreshedItem) {
          renderItemViewer(refreshedItem);
          const tabId = `item:${refreshedItem.id}`;
          if (state.ideItemMeta[tabId]) {
            const sectionTab = state.ideItemMeta[tabId].sectionTab;
            const ext = sectionTab === "projects" ? "py" : "md";
            state.ideItemMeta[tabId].label = `${slugifyTitle(refreshedItem.title)}.${ext}`;
            renderIdeTabbar(document.querySelector(".ide-tab.active")?.dataset.tab || tabId);
          }
        }
      }
    } catch (error) {
      adminItemFeedback.textContent = error.message;
      showToast(error.message, "error");
    }
  });
}

function wireProjectControls() {
  const projectCategories = uniqueCategories(state.projects);
  renderSubsectionNav("projects-subsection-nav", projectCategories, state.projects);

  const experienceSubsections = ["All", ...CATEGORY_OPTIONS.experience];
  renderSubsectionNav("experiences-subsection-nav", experienceSubsections, state.experiences);

  // Build skills filter pills
  renderSkillsFilter("projects-skills-filter", state.projects, "projects");
  renderSkillsFilter("experiences-skills-filter", state.experiences, "experiences");

  // Restore sort from localStorage
  const savedProjectSort = localStorage.getItem("ctrlaltjay-projects-sort");
  const savedExpSort = localStorage.getItem("ctrlaltjay-experiences-sort");
  if (savedProjectSort) document.getElementById("projects-sort").value = savedProjectSort;
  if (savedExpSort) document.getElementById("experiences-sort").value = savedExpSort;

  state.rerenderProjects = () => {
    const activeSubsection = document.querySelector("#projects-subsection-nav .subsection-btn.active")?.dataset.subsection || "all";
    const activeSkill = document.querySelector("#projects-skills-filter .skill-filter-btn.active")?.dataset.skill || "all";
    renderSection(state.projects, null, "projects-sort", "projects-grid", activeSubsection, "projects-search", "projects-search-field", activeSkill);
    addBulkCheckboxes(document.getElementById("projects-grid"));
    addFavoriteButtons();
    enableCardDragging(document.getElementById("projects-grid"));
  };
  
  state.rerenderExperiences = () => {
    const activeSubsection = document.querySelector("#experiences-subsection-nav .subsection-btn.active")?.dataset.subsection || "all";
    const activeSkill = document.querySelector("#experiences-skills-filter .skill-filter-btn.active")?.dataset.skill || "all";
    renderSection(state.experiences, null, "experiences-sort", "experiences-grid", activeSubsection, "experiences-search", "experiences-search-field", activeSkill);
    addBulkCheckboxes(document.getElementById("experiences-grid"));
    addFavoriteButtons();
    enableCardDragging(document.getElementById("experiences-grid"));
  };

  if (!state.controlsBound) {
    // Use event delegation so listeners survive nav regeneration
    document.getElementById("projects-subsection-nav").addEventListener("click", (e) => {
      const btn = e.target.closest(".subsection-btn");
      if (!btn) return;
      document.querySelectorAll("#projects-subsection-nav .subsection-btn").forEach((it) => it.classList.remove("active"));
      btn.classList.add("active");
      shownCounts["projects-grid"] = PAGE_SIZE;
      state.rerenderProjects();
      document.getElementById("projects-grid")?.scrollIntoView({ behavior: "smooth", block: "nearest" });
    });

    document.getElementById("experiences-subsection-nav").addEventListener("click", (e) => {
      const btn = e.target.closest(".subsection-btn");
      if (!btn) return;
      document.querySelectorAll("#experiences-subsection-nav .subsection-btn").forEach((it) => it.classList.remove("active"));
      btn.classList.add("active");
      shownCounts["experiences-grid"] = PAGE_SIZE;
      state.rerenderExperiences();
      document.getElementById("experiences-grid")?.scrollIntoView({ behavior: "smooth", block: "nearest" });
    });

    document.getElementById("projects-sort").addEventListener("change", (e) => {
      localStorage.setItem("ctrlaltjay-projects-sort", e.target.value);
      state.rerenderProjects();
    });
    document.getElementById("experiences-sort").addEventListener("change", (e) => {
      localStorage.setItem("ctrlaltjay-experiences-sort", e.target.value);
      state.rerenderExperiences();
    });

    // Search inputs
    let projectSearchTimer, expSearchTimer;
    document.getElementById("projects-search")?.addEventListener("input", () => {
      clearTimeout(projectSearchTimer);
      projectSearchTimer = setTimeout(() => state.rerenderProjects(), 250);
    });
    document.getElementById("experiences-search")?.addEventListener("input", () => {
      clearTimeout(expSearchTimer);
      expSearchTimer = setTimeout(() => state.rerenderExperiences(), 250);
    });

    // Search field selectors
    document.getElementById("projects-search-field")?.addEventListener("change", () => state.rerenderProjects());
    document.getElementById("experiences-search-field")?.addEventListener("change", () => state.rerenderExperiences());

    // Skills filter delegation
    document.getElementById("projects-skills-filter")?.addEventListener("click", (e) => {
      const btn = e.target.closest(".skill-filter-btn");
      if (!btn) return;
      document.querySelectorAll("#projects-skills-filter .skill-filter-btn").forEach((it) => it.classList.remove("active"));
      btn.classList.add("active");
      shownCounts["projects-grid"] = PAGE_SIZE;
      state.rerenderProjects();
      document.getElementById("projects-grid")?.scrollIntoView({ behavior: "smooth", block: "nearest" });
    });
    document.getElementById("experiences-skills-filter")?.addEventListener("click", (e) => {
      const btn = e.target.closest(".skill-filter-btn");
      if (!btn) return;
      document.querySelectorAll("#experiences-skills-filter .skill-filter-btn").forEach((it) => it.classList.remove("active"));
      btn.classList.add("active");
      shownCounts["experiences-grid"] = PAGE_SIZE;
      state.rerenderExperiences();
      document.getElementById("experiences-grid")?.scrollIntoView({ behavior: "smooth", block: "nearest" });
    });

    // Clear search buttons
    ["projects-search", "experiences-search"].forEach((id) => {
      const input = document.getElementById(id);
      if (!input || input.parentElement.querySelector(".search-clear-btn")) return;
      const clearBtn = document.createElement("button");
      clearBtn.type = "button";
      clearBtn.className = "search-clear-btn";
      clearBtn.innerHTML = '<ion-icon name="close-circle-outline"></ion-icon>';
      clearBtn.title = "Clear search";
      clearBtn.style.display = "none";
      input.parentElement.style.position = "relative";
      input.parentElement.appendChild(clearBtn);
      input.addEventListener("input", () => {
        clearBtn.style.display = input.value ? "" : "none";
      });
      clearBtn.addEventListener("click", () => {
        input.value = "";
        clearBtn.style.display = "none";
        if (id === "projects-search") state.rerenderProjects();
        else state.rerenderExperiences();
      });
    });

    state.controlsBound = true;
  }

  state.rerenderProjects();
  state.rerenderExperiences();
}

async function bootstrap() {
  initTabs();
  initTabTransitions();
  initContactForm();
  initAdminAuth();
  initInlineAdminEditor();
  initEscapeKey();
  initBackToTop();
  initScrollProgress();
  initLightbox();
  initKeyboardNav();
  initAutoSaveDraft();
  initExportJSON();
  initResumeKey();
  initDblClickEdit();
  initThemeToggle();
  initDragAndDrop();
  initBatchSkills();
  initActivityLog();
  initImageCarousel();
  initAdminStats();
  initAdminBackup();
  initFocusTrap();
  initKeyboardShortcuts();
  initCommandPalette();
  initTerminalPanel();
  initJSONImport();
  initSurpriseMe();
  initMobileSwipe();
  initDeletedItems();
  initAdminToolsPopup();
  initProfileFlyout();
  initIdeFileTree();
  initSidebarResize();
  initMinimap();
  initStackSearch();
  initTabbarScroll();
  initIdeStatusClock();
  renderIdeTabbar("about");
  setAdminMode(false);

  // Show skeletons while data loads
  showSkeletons("projects-grid", 6);
  showSkeletons("experiences-grid", 6);

  await fetchData();
  state.dataLoaded = true;
  wireProjectControls();
  updateDraftIndicator();
  renderResume();
  renderSkills();
  renderIdeFileTreeItems();
  updateIdeStatusCount(state.currentSection || "about");
  updateTabBadges();
  updateFooterTimestamp();
  renderRecentlyViewed();
  handleDeepLink();
  initHitCounter();
  initAnimatedCounters();
  initGithubActivity();
  registerServiceWorker();

  // Smooth page load transition
  document.body.style.transition = "opacity 0.4s ease";
  document.body.style.opacity = "1";
}

/* ===== Escape key closes topmost modal ===== */
function initEscapeKey() {
  document.addEventListener("keydown", (e) => {
    if (e.key !== "Escape") return;
    // Close in order: command palette, shortcuts overlay, lightbox, confirm overlay, admin item modal, detail modal, admin login modal
    const cmdPalette = document.getElementById("command-palette-overlay");
    if (cmdPalette) { closeCommandPalette(); return; }
    const terminalPanel = document.getElementById("ide-terminal-panel");
    if (terminalPanel && terminalPanel.style.display !== "none") { closeTerminalPanel(); return; }
    const shortcuts = document.getElementById("shortcuts-overlay");
    if (shortcuts) { shortcuts.remove(); return; }
    const lightbox = document.querySelector(".lightbox-overlay");
    if (lightbox) { lightbox.remove(); return; }
    const confirm = document.querySelector(".confirm-overlay");
    if (confirm) { confirm.remove(); return; }
    const adminItem = document.getElementById("admin-item-modal");
    if (adminItem?.classList.contains("active")) { closeAdminItemModal(); return; }
    const activeItemTab = document.querySelector('.ide-tab.active[data-tab^="item:"]');
    if (activeItemTab) { activeItemTab.querySelector("[data-close-tab]")?.click(); return; }
    const loginModal = document.getElementById("admin-login-modal");
    if (loginModal?.classList.contains("active")) { closeAdminLoginModal(); return; }
    const resumeKeyModal = document.getElementById("resume-key-modal");
    if (resumeKeyModal?.classList.contains("active")) { closeResumeKeyModal(); return; }
    const profileFlyout = document.getElementById("profile-flyout");
    if (profileFlyout && profileFlyout.style.display === "flex") {
      profileFlyout.style.display = "none";
      document.getElementById("profile-flyout-toggle")?.classList.remove("active");
      return;
    }
  });
}

function initContactForm() {
  const form = document.getElementById("contact-form");
  if (!form) return;

  // Character counter for message textarea
  const msgField = form.querySelector('textarea[name="message"]');
  if (msgField) {
    const counter = document.createElement("div");
    counter.className = "char-counter";
    counter.textContent = "0 / 5,000";
    msgField.parentElement.style.position = "relative";
    msgField.insertAdjacentElement("afterend", counter);
    msgField.addEventListener("input", () => {
      const len = msgField.value.length;
      counter.textContent = `${len.toLocaleString()} / 5,000`;
      counter.classList.toggle("near-limit", len > 4500);
      counter.classList.toggle("at-limit", len >= 5000);
    });
  }

  // Real-time validation feedback
  const inputs = form.querySelectorAll("input, textarea, select");
  inputs.forEach((input) => {
    input.addEventListener("blur", () => validateField(input));
    input.addEventListener("input", () => {
      input.classList.remove("invalid");
    });
  });

  // AJAX form submission with cooldown
  let lastSentAt = 0;
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    if (!isFormValid(form)) {
      scrollToFirstError(form);
      return;
    }
    // 60s cooldown
    const elapsed = Date.now() - lastSentAt;
    if (lastSentAt && elapsed < 60000) {
      const wait = Math.ceil((60000 - elapsed) / 1000);
      showToast(`Please wait ${wait}s before sending again.`, "info");
      return;
    }
    const submitBtn = form.querySelector('button[type="submit"]');
    const origText = submitBtn.textContent;
    submitBtn.textContent = "Sending...";
    submitBtn.disabled = true;
    try {
      const res = await fetch("/send_message", {
        method: "POST",
        body: new FormData(form),
        headers: { "X-Requested-With": "XMLHttpRequest" },
      });
      const data = await res.json().catch(() => ({}));
      if (res.ok) {
        lastSentAt = Date.now();
        showToast(data.message || "Message sent!", "success");
        form.reset();
        if (msgField) {
          const counter = form.querySelector(".char-counter");
          if (counter) counter.textContent = "0 / 5,000";
        }
      } else {
        showToast(data.error || "Could not send message.", "error");
      }
    } catch {
      showToast("Network error. Please try again.", "error");
    } finally {
      submitBtn.textContent = origText;
      submitBtn.disabled = false;
    }
  });
}

function validateField(field) {
  const value = field.value.trim();
  const name = field.name;
  let isValid = true;

  if (field.hasAttribute("required") && !value) {
    isValid = false;
  } else if (name === "fullname" && value) {
    isValid = /^[a-zA-Z\s'-]{2,100}$/.test(value) && value.length >= 2;
  } else if (name === "email" && value) {
    isValid = /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value);
  } else if (name === "subject" && value) {
    isValid = value.length >= 5 && value.length <= 100;
  } else if (name === "message" && value) {
    isValid = value.length >= 10 && value.length <= 5000;
  }

  if (!isValid) {
    field.classList.add("invalid");
  } else {
    field.classList.remove("invalid");
  }

  return isValid;
}

function isFormValid(form) {
  const inputs = form.querySelectorAll("input[required], textarea[required]");
  let isValid = true;

  inputs.forEach((input) => {
    if (!validateField(input)) {
      isValid = false;
    }
  });

  return isValid;
}

function scrollToFirstError(form) {
  const firstInvalid = form.querySelector(".invalid");
  if (firstInvalid) {
    firstInvalid.scrollIntoView({ behavior: "smooth", block: "center" });
    firstInvalid.focus();
  }
}

function initAdminAuth() {
  // Check if already authenticated
  fetch("/api/admin/auth-status", { method: "GET" })
    .then((response) => (response.ok ? response.json() : null))
    .then((payload) => {
      if (payload?.is_admin) {
        setAdminMode(true);
      } else {
        // Show login modal if ?admin=login
        const params = new URLSearchParams(window.location.search);
        if (params.get("admin") === "login") {
          openAdminLoginModal();
          // Clean URL without reload
          window.history.replaceState({}, "", window.location.pathname);
        }
      }
    })
    .catch(() => {
      // no-op
    });

  const logoutBtn = document.getElementById("admin-logout-btn");
  if (logoutBtn) {
    logoutBtn.addEventListener("click", async () => {
      try {
        await fetch("/admin/logout", { method: "POST" });
      } catch (_) {
        // no-op
      }
      setAdminMode(false);
      wireProjectControls();
      showToast("Logged out.", "info");
    });
  }

  // Login modal
  const loginModal = document.getElementById("admin-login-modal");
  if (loginModal) {
    loginModal.querySelectorAll("[data-close-admin-login]").forEach((el) => {
      el.addEventListener("click", closeAdminLoginModal);
    });

    document.getElementById("admin-login-form").addEventListener("submit", async (e) => {
      e.preventDefault();
      const feedback = document.getElementById("admin-login-feedback");
      const passcode = document.getElementById("admin-login-passcode").value.trim();
      if (!passcode) { feedback.textContent = "Passcode is required."; return; }
      feedback.textContent = "Verifying...";
      feedback.style.color = "#94a3b8";
      try {
        const res = await fetch("/admin/auth", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ passcode }),
        });
        const data = await res.json();
        if (res.ok) {
          closeAdminLoginModal();
          setAdminMode(true);
          wireProjectControls();
          showToast("Admin mode active", "success");
        } else {
          feedback.style.color = "#f87171";
          feedback.textContent = data.error || "Authentication failed.";
        }
      } catch (_) {
        feedback.style.color = "#f87171";
        feedback.textContent = "Could not verify. Please try again.";
      }
    });
  }
}

function openAdminLoginModal() {
  const modal = document.getElementById("admin-login-modal");
  if (!modal) return;
  document.getElementById("admin-login-form").reset();
  document.getElementById("admin-login-feedback").textContent = "";
  modal.classList.add("active");
  modal.setAttribute("aria-hidden", "false");
  document.getElementById("admin-login-passcode").focus();
}

function closeAdminLoginModal() {
  const modal = document.getElementById("admin-login-modal");
  if (!modal) return;
  modal.classList.remove("active");
  modal.setAttribute("aria-hidden", "true");
}

/* ===== Card entrance animations (IntersectionObserver) ===== */
const cardObserver = new IntersectionObserver(
  (entries) => {
    entries.forEach((entry) => {
      if (entry.isIntersecting) {
        entry.target.classList.add("card-visible");
        cardObserver.unobserve(entry.target);
      }
    });
  },
  { threshold: 0.05 }
);

function observeCards(container) {
  const cards = container.querySelectorAll(".card:not(.card-visible)");
  cards.forEach((card, i) => {
    card.style.transitionDelay = `${i * 50}ms`;
    cardObserver.observe(card);
  });
}

/* ===== Back-to-top button ===== */
function initBackToTop() {
  const btn = document.getElementById("back-to-top");
  if (!btn) return;
  window.addEventListener("scroll", () => {
    btn.classList.toggle("visible", window.scrollY > 400);
  }, { passive: true });
  btn.addEventListener("click", () => {
    window.scrollTo({ top: 0, behavior: "smooth" });
  });
}

/* ===== Scroll progress bar ===== */
function initScrollProgress() {
  const bar = document.getElementById("scroll-progress");
  if (!bar) return;
  window.addEventListener("scroll", () => {
    const scrollTop = window.scrollY;
    const docHeight = document.documentElement.scrollHeight - window.innerHeight;
    const progress = docHeight > 0 ? (scrollTop / docHeight) * 100 : 0;
    bar.style.width = progress + "%";
  }, { passive: true });
}

/* ===== Image lightbox ===== */
function initLightbox() {
  document.addEventListener("click", (e) => {
    const img = e.target.closest("#modal-image");
    if (!img || !img.src) return;
    const overlay = document.createElement("div");
    overlay.className = "lightbox-overlay";
    overlay.innerHTML = `<img src="${img.src}" alt="${escapeHtml(img.alt || "")}">`;
    overlay.addEventListener("click", () => overlay.remove());
    document.body.appendChild(overlay);
  });
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") {
      const lb = document.querySelector(".lightbox-overlay");
      if (lb) lb.remove();
    }
  });
}

/* ===== Keyboard navigation ===== */
function initKeyboardNav() {
  document.addEventListener("keydown", (e) => {
    // Only if a card grid is visible and no modal is open
    if (document.querySelector(".modal-shell.active") || document.querySelector(".lightbox-overlay") || document.querySelector(".confirm-overlay")) return;
    if (e.key !== "ArrowRight" && e.key !== "ArrowLeft" && e.key !== "Enter") return;

    const activePanel = document.querySelector(".tab-panel.active");
    if (!activePanel) return;
    const grid = activePanel.querySelector(".card-grid");
    if (!grid) return;

    const cards = [...grid.querySelectorAll(".card")];
    if (cards.length === 0) return;

    const focusedCard = document.activeElement?.closest(".card");
    let idx = focusedCard ? cards.indexOf(focusedCard) : -1;

    if (e.key === "ArrowRight") {
      e.preventDefault();
      idx = Math.min(idx + 1, cards.length - 1);
      cards[idx].focus();
    } else if (e.key === "ArrowLeft") {
      e.preventDefault();
      idx = Math.max(idx - 1, 0);
      cards[idx].focus();
    } else if (e.key === "Enter" && focusedCard) {
      e.preventDefault();
      focusedCard.click();
    }
  });
}

/* ===== Bulk admin actions ===== */
const bulkSelected = new Set();

function updateBulkBar() {
  let bar = document.getElementById("bulk-action-bar");
  if (bulkSelected.size === 0) {
    if (bar) bar.remove();
    return;
  }
  if (!bar) {
    bar = document.createElement("div");
    bar.id = "bulk-action-bar";
    bar.className = "bulk-bar";
    bar.innerHTML = `
      <span id="bulk-count"></span>
      <button class="bulk-delete" id="bulk-delete-btn">Delete Selected</button>
      <button class="bulk-cancel" id="bulk-cancel-btn">Cancel</button>`;
    document.body.appendChild(bar);
    document.getElementById("bulk-delete-btn").addEventListener("click", bulkDelete);
    document.getElementById("bulk-cancel-btn").addEventListener("click", bulkCancel);
  }
  document.getElementById("bulk-count").textContent = `${bulkSelected.size} selected`;
}

async function bulkDelete() {
  if (bulkSelected.size === 0) return;
  const count = bulkSelected.size;
  const confirmed = await showConfirm("Bulk Delete", `This will move ${count} item(s) to Recently Deleted.`, { requireText: `DELETE ${count}`, confirmLabel: "Delete All" });
  if (!confirmed) return;
  let ok = 0, fail = 0;
  for (const id of bulkSelected) {
    try {
      const res = await fetch(`/api/admin/items/${id}`, { method: "DELETE" });
      if (res.ok) ok++; else fail++;
    } catch { fail++; }
  }
  bulkSelected.clear();
  updateBulkBar();
  await fetchData();
  wireProjectControls();
  renderDeletedItems();
  showToast(`Moved ${ok} item(s) to Recently Deleted${fail ? `, ${fail} failed` : ""}.`, fail ? "error" : "success");
}

function bulkCancel() {
  bulkSelected.clear();
  document.querySelectorAll(".card-checkbox").forEach((cb) => (cb.checked = false));
  updateBulkBar();
}

function addBulkCheckboxes(container) {
  if (!state.isAdmin) return;
  container.querySelectorAll(".card").forEach((card) => {
    if (card.querySelector(".card-checkbox")) return;
    const item = [...state.projects, ...state.experiences].find(
      (it) => it.title === card.querySelector("h4")?.textContent
    );
    if (!item) return;
    const cb = document.createElement("input");
    cb.type = "checkbox";
    cb.className = "card-checkbox";
    cb.checked = bulkSelected.has(item.id);
    cb.addEventListener("click", (e) => {
      e.stopPropagation();
      if (cb.checked) bulkSelected.add(item.id);
      else bulkSelected.delete(item.id);
      updateBulkBar();
    });
    card.appendChild(cb);
  });
}

/* ===== Recently Deleted panel (admin) ===== */
async function fetchDeletedItems() {
  try {
    const res = await fetch("/api/admin/deleted-items");
    if (!res.ok) return [];
    return await res.json();
  } catch { return []; }
}

async function renderDeletedItems() {
  const panel = document.getElementById("deleted-items-panel");
  const list = document.getElementById("deleted-items-list");
  const badge = document.getElementById("deleted-count-badge");
  if (!panel || !list) return;
  if (!state.isAdmin) { panel.style.display = "none"; return; }
  const items = await fetchDeletedItems();
  badge.textContent = items.length;
  badge.style.display = items.length > 0 ? "" : "none";
  if (items.length === 0) {
    list.innerHTML = '<p class="text-xs text-ink-muted" style="text-align:center;padding:12px 0">No deleted items</p>';
    return;
  }
  list.innerHTML = items.map((item) => {
    const deletedDate = item.deleted_at ? new Date(item.deleted_at).toLocaleDateString() : "";
    return `<div class="deleted-item" data-id="${escapeHtml(item.id)}">
      <div class="deleted-item-info">
        <span class="deleted-item-title">${escapeHtml(item.title)}</span>
        <span class="deleted-item-meta">${escapeHtml(item.section || "")} · ${escapeHtml(item.category || "")} · Deleted ${escapeHtml(deletedDate)}</span>
      </div>
      <div class="deleted-item-actions">
        <button class="deleted-restore-btn" data-id="${escapeHtml(item.id)}" title="Restore"><ion-icon name="arrow-undo-outline"></ion-icon></button>
        <button class="deleted-perm-btn" data-id="${escapeHtml(item.id)}" data-title="${escapeHtml(item.title)}" title="Permanently delete"><ion-icon name="trash-outline"></ion-icon></button>
      </div>
    </div>`;
  }).join("");
  // Wire restore buttons
  list.querySelectorAll(".deleted-restore-btn").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const id = btn.dataset.id;
      try {
        const res = await fetch(`/api/admin/items/${id}/restore`, { method: "POST" });
        if (!res.ok) throw new Error();
        showToast("Item restored.", "success");
        await fetchData();
        wireProjectControls();
        renderDeletedItems();
        logActivity("Restore", "Restored deleted item");
      } catch { showToast("Failed to restore item.", "error"); }
    });
  });
  // Wire permanent delete buttons
  list.querySelectorAll(".deleted-perm-btn").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const id = btn.dataset.id;
      const title = btn.dataset.title;
      const confirmed = await showConfirm("Permanent Delete", `This will permanently erase "${title}" from the database. This CANNOT be undone.`, { requireText: title, confirmLabel: "Erase Forever" });
      if (!confirmed) return;
      try {
        const res = await fetch(`/api/admin/items/${id}/permanent`, { method: "DELETE" });
        if (!res.ok) throw new Error();
        showToast("Item permanently deleted.", "success");
        renderDeletedItems();
        logActivity("Permanent Delete", title);
      } catch { showToast("Failed to permanently delete item.", "error"); }
    });
  });
}

/* ===== Admin Tools Popup ===== */
function initAdminToolsPopup() {
  const toggle = document.getElementById("admin-tools-toggle");
  const popup = document.getElementById("admin-tools-popup");
  const closeBtn = document.getElementById("admin-tools-close");
  const backdrop = popup?.querySelector(".admin-tools-popup-backdrop");
  if (!toggle || !popup) return;
  toggle.addEventListener("click", () => { popup.style.display = "flex"; });
  closeBtn?.addEventListener("click", () => { popup.style.display = "none"; });
  backdrop?.addEventListener("click", () => { popup.style.display = "none"; });
}

function initProfileFlyout() {
  const toggle = document.getElementById("profile-flyout-toggle");
  const popup = document.getElementById("profile-flyout");
  const closeBtn = document.getElementById("profile-flyout-close");
  const backdrop = document.getElementById("profile-flyout-backdrop");
  if (!toggle || !popup) return;
  const open = () => { popup.style.display = "flex"; toggle.classList.add("active"); toggle.setAttribute("aria-expanded", "true"); };
  const close = () => { popup.style.display = "none"; toggle.classList.remove("active"); toggle.setAttribute("aria-expanded", "false"); };
  toggle.addEventListener("click", open);
  closeBtn?.addEventListener("click", close);
  backdrop?.addEventListener("click", close);
}

function initDeletedItems() {
  const toggle = document.getElementById("deleted-items-toggle");
  const panel = document.getElementById("deleted-items-panel");
  if (!toggle || !panel) return;
  toggle.addEventListener("click", () => {
    panel.style.display = panel.style.display === "none" ? "" : "none";
    renderDeletedItems();
  });
}

/* ===== Auto-save admin draft (localStorage) ===== */
const DRAFT_KEY = "ctrlaltjay-admin-draft";

function initAutoSaveDraft() {
  const form = document.getElementById("admin-item-form");
  if (!form) return;

  // Save draft on input
  form.addEventListener("input", () => {
    const data = {};
    new FormData(form).forEach((val, key) => {
      if (key !== "image" && key !== "id") data[key] = val;
    });
    localStorage.setItem(DRAFT_KEY, JSON.stringify(data));
  });
}

function restoreDraft() {
  const raw = localStorage.getItem(DRAFT_KEY);
  if (!raw) return false;
  try {
    const data = JSON.parse(raw);
    if (!data.title) return false;
    return data;
  } catch { return false; }
}

function clearDraft() {
  localStorage.removeItem(DRAFT_KEY);
}

/* ===== Export as JSON ===== */
function initExportJSON() {
  const btn = document.getElementById("export-json-btn");
  if (!btn) return;
  btn.addEventListener("click", async () => {
    try {
      const res = await fetch("/api/public-data");
      const data = await res.json();
      const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `ctrlaltjay-export-${new Date().toISOString().slice(0, 10)}.json`;
      a.click();
      URL.revokeObjectURL(url);
      showToast("Data exported.", "success");
    } catch {
      showToast("Export failed.", "error");
    }
  });
}

/* ===== Resume key gated print ===== */
let resumeKeyUnlocked = false;

function initResumeKey() {
  const printBtn = document.getElementById("print-resume-btn");
  if (!printBtn) return;

  printBtn.addEventListener("click", () => {
    // Admin always gets direct print
    if (state.isAdmin || resumeKeyUnlocked) {
      window.print();
      return;
    }
    openResumeKeyModal();
  });

  // Resume key modal close handlers
  const modal = document.getElementById("resume-key-modal");
  if (!modal) return;
  modal.querySelectorAll("[data-close-resume-key]").forEach((el) => {
    el.addEventListener("click", closeResumeKeyModal);
  });

  // Verify form
  document.getElementById("resume-key-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const feedback = document.getElementById("resume-key-feedback");
    const input = document.getElementById("resume-key-input");
    const key = input.value.trim();
    if (!key) { feedback.textContent = "Key is required."; return; }
    feedback.textContent = "Verifying...";
    feedback.style.color = "#94a3b8";
    try {
      const res = await fetch("/api/resume-key/verify", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ key }),
      });
      if (res.ok) {
        resumeKeyUnlocked = true;
        closeResumeKeyModal();
        showToast("Resume unlocked. Printing...", "success");
        setTimeout(() => window.print(), 400);
      } else {
        const data = await res.json();
        feedback.style.color = "#f87171";
        feedback.textContent = data.error || "Invalid key.";
      }
    } catch {
      feedback.style.color = "#f87171";
      feedback.textContent = "Verification failed. Try again.";
    }
  });

  // Admin panel: copy & rotate
  const copyBtn = document.getElementById("resume-key-copy");
  const rotateBtn = document.getElementById("resume-key-rotate");
  if (copyBtn) {
    copyBtn.addEventListener("click", async () => {
      const display = document.getElementById("resume-key-display");
      try {
        await navigator.clipboard.writeText(display.textContent);
        showToast("Key copied to clipboard.", "success");
      } catch {
        showToast("Copy failed.", "error");
      }
    });
  }
  if (rotateBtn) {
    rotateBtn.addEventListener("click", async () => {
      const confirmed = await showConfirm("Rotate Resume Key", "Generate a new key? Anyone with the old key will lose access.");
      if (!confirmed) return;
      try {
        const res = await fetch("/api/admin/resume-key/rotate", { method: "POST" });
        const data = await res.json();
        if (res.ok) {
          document.getElementById("resume-key-display").textContent = data.resume_key;
          showToast("Key rotated.", "success");
        } else {
          showToast(data.error || "Rotate failed.", "error");
        }
      } catch {
        showToast("Rotate failed.", "error");
      }
    });
  }
}

async function loadResumeKey() {
  if (!state.isAdmin) return;
  try {
    const res = await fetch("/api/admin/resume-key");
    const data = await res.json();
    const display = document.getElementById("resume-key-display");
    if (display) display.textContent = data.resume_key || "—";
  } catch { /* no-op */ }
}

function openResumeKeyModal() {
  const modal = document.getElementById("resume-key-modal");
  if (!modal) return;
  document.getElementById("resume-key-form").reset();
  document.getElementById("resume-key-feedback").textContent = "";
  modal.classList.add("active");
  modal.setAttribute("aria-hidden", "false");
  document.getElementById("resume-key-input").focus();
}

function closeResumeKeyModal() {
  const modal = document.getElementById("resume-key-modal");
  if (!modal) return;
  modal.classList.remove("active");
  modal.setAttribute("aria-hidden", "true");
}

/* ===== Smooth tab transitions ===== */
function initTabTransitions() {
  tabs.forEach((btn) => {
    btn.addEventListener("click", () => {
      const panel = document.getElementById(btn.dataset.tab);
      if (panel) {
        panel.style.opacity = "0";
        panel.style.transform = "translateY(8px)";
        requestAnimationFrame(() => {
          panel.style.transition = "opacity 0.3s ease, transform 0.3s ease";
          panel.style.opacity = "1";
          panel.style.transform = "translateY(0)";
        });
      }
    });
  });
}

/* ===== Card count badges on tab buttons ===== */
function updateTabBadges() {
  const projBadge = document.getElementById("tab-count-projects");
  const expBadge = document.getElementById("tab-count-experiences");
  if (projBadge) projBadge.textContent = state.projects.length || "";
  if (expBadge) expBadge.textContent = state.experiences.length || "";
}

/* ===== Last updated footer timestamp ===== */
function updateFooterTimestamp() {
  const allItems = [...state.projects, ...state.experiences];
  if (allItems.length === 0) return;
  const latest = allItems.reduce((a, b) => {
    const da = new Date(a.updated_at || 0);
    const db = new Date(b.updated_at || 0);
    return da > db ? a : b;
  });
  const ts = document.getElementById("last-updated-ts");
  if (ts && latest.updated_at) {
    const d = new Date(latest.updated_at);
    const now = new Date();
    const diffMs = now - d;
    const diffDays = Math.floor(diffMs / 86400000);
    let ago;
    if (diffDays === 0) ago = "today";
    else if (diffDays === 1) ago = "yesterday";
    else if (diffDays < 30) ago = `${diffDays}d ago`;
    else ago = d.toLocaleDateString("en-SG", { day: "numeric", month: "short", year: "numeric" });
    ts.textContent = `Last updated ${ago}`;
  }
}

/* ===== Double-click card to edit (admin) ===== */
function initDblClickEdit() {
  document.addEventListener("dblclick", (e) => {
    if (!state.isAdmin) return;
    const card = e.target.closest(".card");
    if (!card) return;
    const title = card.querySelector("h4")?.textContent;
    const item = [...state.projects, ...state.experiences].find((it) => it.title === title);
    if (!item) return;
    e.preventDefault();
    openAdminItemModal(item, item.section || "project");
  });
}

/* ===== Card focus ring for keyboard nav ===== */
// Handled via CSS below — .card:focus-visible

/* ===== Deep link handler ===== */
function handleDeepLink() {
  const hash = window.location.hash.replace("#", "");
  if (!hash.startsWith("item/")) return;
  const itemId = hash.replace("item/", "");
  const item = findItemById(itemId);
  if (item) {
    const tab = item.section === "experience" ? "experiences" : "projects";
    openItemTab(item, tab);
  }
}

/* ===== Dark/Light Theme Toggle ===== */
const THEME_KEY = "ctrlaltjay-theme";

function initThemeToggle() {
  const saved = localStorage.getItem(THEME_KEY);
  if (saved === "light") document.documentElement.classList.add("light-theme");

  const btn = document.getElementById("theme-toggle");
  if (!btn) return;
  updateThemeIcon(btn);

  btn.addEventListener("click", () => {
    document.documentElement.classList.toggle("light-theme");
    const isLight = document.documentElement.classList.contains("light-theme");
    localStorage.setItem(THEME_KEY, isLight ? "light" : "dark");
    updateThemeIcon(btn);
  });
}

function updateThemeIcon(btn) {
  const isLight = document.documentElement.classList.contains("light-theme");
  btn.innerHTML = isLight
    ? '<ion-icon name="moon-outline"></ion-icon>'
    : '<ion-icon name="sunny-outline"></ion-icon>';
  btn.title = isLight ? "Switch to dark mode" : "Switch to light mode";
}

/* ===== Recently Viewed Carousel ===== */
const RECENT_KEY = "ctrlaltjay-recent";
const MAX_RECENT = 8;

function trackRecentlyViewed(itemId) {
  if (!itemId) return;
  let recent = JSON.parse(localStorage.getItem(RECENT_KEY) || "[]");
  recent = recent.filter((id) => id !== itemId);
  recent.unshift(itemId);
  if (recent.length > MAX_RECENT) recent = recent.slice(0, MAX_RECENT);
  localStorage.setItem(RECENT_KEY, JSON.stringify(recent));
  renderRecentlyViewed();
}

function renderRecentlyViewed() {
  const recentIds = JSON.parse(localStorage.getItem(RECENT_KEY) || "[]");
  const allItems = [...state.projects, ...state.experiences];
  const items = recentIds.map((id) => allItems.find((it) => it.id === id)).filter(Boolean);

  const projectItems = items.filter((it) => it.section === "project");
  const experienceItems = items.filter((it) => it.section === "experience");

  renderRecentStrip("recently-viewed-projects", projectItems);
  renderRecentStrip("recently-viewed-experiences", experienceItems);
}

function renderRecentStrip(containerId, items) {
  const container = document.getElementById(containerId);
  if (!container) return;

  if (items.length === 0) {
    container.style.display = "none";
    return;
  }
  container.style.display = "";
  const strip = container.querySelector(".recent-strip");
  if (!strip) return;
  strip.innerHTML = "";
  items.forEach((item) => {
    const card = document.createElement("div");
    card.className = "recent-card";
    card.tabIndex = 0;
    const imgHtml = item.image_path ? `<img src="${item.image_path}" alt="${escapeHtml(item.title)}" loading="lazy">` : "";
    card.innerHTML = `${imgHtml}<span>${escapeHtml(item.title)}</span>`;
    card.addEventListener("click", () => openItemTab(item, item.section === "experience" ? "experiences" : "projects"));
    strip.appendChild(card);
  });
}

/* ===== Related Items in Detail Modal ===== */
function renderRelatedItems(item) {
  const container = document.getElementById("related-items");
  if (!container) return;
  const allItems = [...state.projects, ...state.experiences].filter((it) => it.id !== item.id);
  const itemSkills = parseSkills(item.skills);

  // Score by shared skills + same category
  const scored = allItems.map((other) => {
    let score = 0;
    if (other.category === item.category) score += 1;
    const otherSkills = parseSkills(other.skills);
    itemSkills.forEach((s) => {
      if (otherSkills.some((os) => os.toLowerCase() === s.toLowerCase())) score += 2;
    });
    return { item: other, score };
  }).filter((s) => s.score > 0).sort((a, b) => b.score - a.score).slice(0, 4);

  if (scored.length === 0) {
    container.style.display = "none";
    return;
  }
  container.style.display = "";
  const strip = container.querySelector(".related-strip");
  if (!strip) return;
  strip.innerHTML = "";
  scored.forEach(({ item: rel }) => {
    const card = document.createElement("div");
    card.className = "related-card";
    card.tabIndex = 0;
    const imgHtml = rel.image_path ? `<img src="${rel.image_path}" alt="${escapeHtml(rel.title)}" loading="lazy">` : "";
    card.innerHTML = `${imgHtml}<span>${escapeHtml(rel.title)}</span>`;
    card.addEventListener("click", () => openItemTab(rel, rel.section === "experience" ? "experiences" : "projects"));
    strip.appendChild(card);
  });
}

/* ===== Activity Log (Admin) ===== */
const ACTIVITY_LOG_KEY = "ctrlaltjay-activity-log";
const MAX_LOG_ENTRIES = 50;

function logActivity(action, detail) {
  if (!state.isAdmin) return;
  const log = JSON.parse(localStorage.getItem(ACTIVITY_LOG_KEY) || "[]");
  log.unshift({ action, detail, timestamp: new Date().toISOString() });
  if (log.length > MAX_LOG_ENTRIES) log.length = MAX_LOG_ENTRIES;
  localStorage.setItem(ACTIVITY_LOG_KEY, JSON.stringify(log));
}

function renderActivityLog() {
  const container = document.getElementById("activity-log-list");
  if (!container) return;
  const log = JSON.parse(localStorage.getItem(ACTIVITY_LOG_KEY) || "[]");
  if (log.length === 0) {
    container.innerHTML = '<p class="text-ink-muted text-sm">No activity recorded yet.</p>';
    return;
  }
  container.innerHTML = log.map((entry) => {
    const d = new Date(entry.timestamp);
    const time = d.toLocaleDateString("en-SG", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
    return `<div class="activity-entry"><span class="activity-action">${escapeHtml(entry.action)}</span><span class="activity-detail">${escapeHtml(entry.detail)}</span><span class="activity-time">${escapeHtml(time)}</span></div>`;
  }).join("");
}

function initActivityLog() {
  const btn = document.getElementById("activity-log-toggle");
  const panel = document.getElementById("activity-log-panel");
  if (!btn || !panel) return;
  btn.addEventListener("click", () => {
    const visible = panel.style.display !== "none";
    panel.style.display = visible ? "none" : "block";
    if (!visible) renderActivityLog();
  });
  const clearBtn = document.getElementById("activity-log-clear");
  if (clearBtn) {
    clearBtn.addEventListener("click", () => {
      localStorage.removeItem(ACTIVITY_LOG_KEY);
      renderActivityLog();
      showToast("Activity log cleared.", "info");
    });
  }
}

/* ===== Markdown Support ===== */
function renderMarkdown(text) {
  if (!text) return "";
  // Sanitize HTML entities first to prevent XSS
  let s = text
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
  // Bold: **text**
  s = s.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
  // Italic: *text*
  s = s.replace(/\*(.+?)\*/g, "<em>$1</em>");
  // Inline code: `code`
  s = s.replace(/`(.+?)`/g, '<code class="md-code">$1</code>');
  // Links: [text](url) — only allow http/https
  s = s.replace(/\[(.+?)\]\((https?:\/\/[^\s)]+)\)/g, '<a href="$2" target="_blank" rel="noopener noreferrer" class="md-link">$1</a>');
  // Auto-linkify bare URLs not already inside href or tag content
  s = s.replace(/(^|[^">=\/])(https?:\/\/[^\s<"')\]]+)/g, '$1<a href="$2" target="_blank" rel="noopener noreferrer" class="md-link">$2</a>');
  // Line breaks
  s = s.replace(/\n/g, "<br>");
  return s;
}

/* ===== Favorites / Bookmarks ===== */
const FAVORITES_KEY = "ctrlaltjay-favorites";

function getFavorites() {
  return JSON.parse(localStorage.getItem(FAVORITES_KEY) || "[]");
}

function toggleFavorite(itemId) {
  let favs = getFavorites();
  if (favs.includes(itemId)) {
    favs = favs.filter((id) => id !== itemId);
  } else {
    favs.push(itemId);
  }
  localStorage.setItem(FAVORITES_KEY, JSON.stringify(favs));
  return favs.includes(itemId);
}

function addFavoriteButtons() {
  document.querySelectorAll(".card").forEach((card) => {
    if (card.querySelector(".fav-btn")) return;
    const title = card.querySelector("h4")?.textContent;
    const item = [...state.projects, ...state.experiences].find((it) => it.title === title);
    if (!item) return;
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "fav-btn";
    btn.setAttribute("aria-label", "Toggle favorite");
    const favs = getFavorites();
    btn.innerHTML = favs.includes(item.id)
      ? '<ion-icon name="heart"></ion-icon>'
      : '<ion-icon name="heart-outline"></ion-icon>';
    if (favs.includes(item.id)) btn.classList.add("fav-active");
    btn.addEventListener("click", (e) => {
      e.stopPropagation();
      const isNow = toggleFavorite(item.id);
      btn.innerHTML = isNow ? '<ion-icon name="heart"></ion-icon>' : '<ion-icon name="heart-outline"></ion-icon>';
      btn.classList.toggle("fav-active", isNow);
      showToast(isNow ? "Added to favorites" : "Removed from favorites", "info");
    });
    card.appendChild(btn);
  });
}

/* ===== Drag-and-Drop Reorder (Admin) ===== */
function initDragAndDrop() {
  document.addEventListener("dragstart", (e) => {
    if (!state.isAdmin) return;
    const card = e.target.closest(".card");
    if (!card) return;
    card.classList.add("dragging");
    e.dataTransfer.effectAllowed = "move";
    e.dataTransfer.setData("text/plain", card.querySelector("h4")?.textContent || "");
  });

  document.addEventListener("dragend", (e) => {
    const card = e.target.closest(".card");
    if (card) card.classList.remove("dragging");
  });

  document.addEventListener("dragover", (e) => {
    if (!state.isAdmin) return;
    e.preventDefault();
    const grid = e.target.closest(".card-grid");
    if (!grid) return;
    const dragging = grid.querySelector(".dragging");
    if (!dragging) return;
    const afterElement = getDragAfterElement(grid, e.clientY);
    if (afterElement) {
      grid.insertBefore(dragging, afterElement);
    } else {
      // Before show-more-wrap if it exists
      const showMore = grid.querySelector(".show-more-wrap");
      if (showMore) grid.insertBefore(dragging, showMore);
      else grid.appendChild(dragging);
    }
  });

  document.addEventListener("drop", (e) => {
    if (!state.isAdmin) return;
    e.preventDefault();
    const grid = e.target.closest(".card-grid");
    if (!grid) return;
    saveSortOrder(grid);
  });
}

function getDragAfterElement(grid, y) {
  const siblings = [...grid.querySelectorAll(".card:not(.dragging)")];
  let closest = null;
  let closestOffset = Number.NEGATIVE_INFINITY;
  siblings.forEach((child) => {
    const box = child.getBoundingClientRect();
    const offset = y - box.top - box.height / 2;
    if (offset < 0 && offset > closestOffset) {
      closestOffset = offset;
      closest = child;
    }
  });
  return closest;
}

function saveSortOrder(grid) {
  const cards = [...grid.querySelectorAll(".card")];
  const allItems = [...state.projects, ...state.experiences];
  const order = cards.map((c) => {
    const title = c.querySelector("h4")?.textContent;
    return allItems.find((it) => it.title === title)?.id;
  }).filter(Boolean);

  // Save to localStorage as custom sort
  const gridId = grid.id;
  const orderKey = `ctrlaltjay-sort-order-${gridId}`;
  localStorage.setItem(orderKey, JSON.stringify(order));
  showToast("Card order saved.", "success");
  logActivity("Reorder", `Reordered cards in ${gridId}`);
}

function enableCardDragging(container) {
  if (!state.isAdmin) return;
  container.querySelectorAll(".card").forEach((card) => {
    card.draggable = true;
  });
}

/* ===== Batch Skill Assignment ===== */
function initBatchSkills() {
  // Add button to bulk bar when it exists
  const observer = new MutationObserver(() => {
    const bar = document.getElementById("bulk-action-bar");
    if (bar && !bar.querySelector(".bulk-skills")) {
      const btn = document.createElement("button");
      btn.className = "bulk-skills";
      btn.textContent = "Assign Skills";
      btn.style.cssText = "padding:8px 18px;border-radius:10px;font-size:0.82rem;font-weight:600;cursor:pointer;border:1.5px solid rgba(56,189,248,0.3);background:rgba(56,189,248,0.15);color:#38bdf8;transition:all 0.2s ease";
      btn.addEventListener("click", openBatchSkillModal);
      bar.insertBefore(btn, bar.querySelector(".bulk-cancel"));
    }
  });
  observer.observe(document.body, { childList: true, subtree: true });
}

function openBatchSkillModal() {
  if (bulkSelected.size === 0) return;
  const shell = document.getElementById("batch-skill-modal");
  if (!shell) return;
  // Populate picker
  const picker = document.getElementById("batch-skills-picker");
  picker.innerHTML = "";
  const allSkills = state.skills.map((s) => s.name).filter(Boolean).sort();
  if (allSkills.length === 0) {
    picker.innerHTML = '<span class="text-xs text-ink-muted">No skills defined yet.</span>';
    return;
  }
  allSkills.forEach((name) => {
    const label = document.createElement("label");
    label.className = "skill-picker-chip";
    const cb = document.createElement("input");
    cb.type = "checkbox";
    cb.value = name;
    const span = document.createElement("span");
    span.textContent = name;
    label.appendChild(cb);
    label.appendChild(span);
    picker.appendChild(label);
  });
  shell.classList.add("active");
  shell.setAttribute("aria-hidden", "false");
}

function closeBatchSkillModal() {
  const shell = document.getElementById("batch-skill-modal");
  if (!shell) return;
  shell.classList.remove("active");
  shell.setAttribute("aria-hidden", "true");
}

async function applyBatchSkills() {
  const picker = document.getElementById("batch-skills-picker");
  const checked = [...picker.querySelectorAll("input:checked")].map((cb) => cb.value);
  if (checked.length === 0) { showToast("Select at least one skill.", "error"); return; }
  const modeEl = document.querySelector('input[name="batch-skill-mode"]:checked');
  const mode = modeEl ? modeEl.value : "add";
  let ok = 0, fail = 0;
  for (const id of bulkSelected) {
    const item = findItemById(id);
    if (!item) { fail++; continue; }
    let current = parseSkills(item.skills);
    if (mode === "add") {
      checked.forEach((s) => { if (!current.some((c) => c.toLowerCase() === s.toLowerCase())) current.push(s); });
    } else if (mode === "remove") {
      current = current.filter((s) => !checked.some((c) => c.toLowerCase() === s.toLowerCase()));
    } else {
      current = [...checked];
    }
    const fd = new FormData();
    fd.append("skills", current.join(","));
    fd.append("title", item.title);
    fd.append("section", item.section);
    fd.append("category", item.category);
    try {
      const res = await fetch(`/api/admin/items/${id}`, { method: "PUT", body: fd });
      if (res.ok) ok++; else fail++;
    } catch { fail++; }
  }
  closeBatchSkillModal();
  bulkSelected.clear();
  updateBulkBar();
  await fetchData();
  wireProjectControls();
  showToast(`Skills updated on ${ok} item(s)${fail ? `, ${fail} failed` : ""}.`, fail ? "error" : "success");
  logActivity("Batch Skills", `Updated skills on ${ok} items`);
}

/* ===== Image Carousel ===== */
let carouselImages = [];
let carouselIndex = 0;

function setupCarousel(item) {
  const mainImg = document.getElementById("modal-image");
  const prevBtn = document.getElementById("carousel-prev");
  const nextBtn = document.getElementById("carousel-next");
  const dots = document.getElementById("carousel-dots");

  carouselImages = item.image_path ? [item.image_path] : [];
  if (item.additional_images) {
    const extras = item.additional_images.split(",").map((s) => s.trim()).filter(Boolean);
    carouselImages = carouselImages.concat(extras);
  }
  carouselIndex = 0;

  if (carouselImages.length <= 1) {
    if (prevBtn) prevBtn.style.display = "none";
    if (nextBtn) nextBtn.style.display = "none";
    if (dots) dots.innerHTML = "";
    return;
  }
  if (prevBtn) prevBtn.style.display = "";
  if (nextBtn) nextBtn.style.display = "";
  renderCarouselDots();
}

function navigateCarousel(dir) {
  carouselIndex = (carouselIndex + dir + carouselImages.length) % carouselImages.length;
  const img = document.getElementById("modal-image");
  if (img) {
    img.style.opacity = "0";
    img.style.transition = "opacity 0.25s ease";
    setTimeout(() => {
      img.src = carouselImages[carouselIndex];
      img.style.opacity = "1";
    }, 250);
  }
  renderCarouselDots();
}

function renderCarouselDots() {
  const dots = document.getElementById("carousel-dots");
  if (!dots) return;
  dots.innerHTML = carouselImages.map((_, i) =>
    `<span class="carousel-dot${i === carouselIndex ? " active" : ""}" data-idx="${i}"></span>`
  ).join("");
}

function initImageCarousel() {
  const prevBtn = document.getElementById("carousel-prev");
  const nextBtn = document.getElementById("carousel-next");
  if (prevBtn) prevBtn.addEventListener("click", (e) => { e.stopPropagation(); navigateCarousel(-1); });
  if (nextBtn) nextBtn.addEventListener("click", (e) => { e.stopPropagation(); navigateCarousel(1); });
  document.getElementById("carousel-dots")?.addEventListener("click", (e) => {
    const dot = e.target.closest(".carousel-dot");
    if (!dot) return;
    const newIdx = parseInt(dot.dataset.idx, 10);
    if (newIdx === carouselIndex) return;
    carouselIndex = newIdx;
    const img = document.getElementById("modal-image");
    if (img) {
      img.style.opacity = "0";
      img.style.transition = "opacity 0.25s ease";
      setTimeout(() => {
        img.src = carouselImages[carouselIndex];
        img.style.opacity = "1";
      }, 250);
    }
    renderCarouselDots();
  });
}

/* ===== Social Share Buttons ===== */
function updateShareLinks(item) {
  const base = "https://ctrlaltjay.dev";
  const url = encodeURIComponent(`${base}/#item/${item.id}`);
  const title = encodeURIComponent(item.title || "");
  const shareDiv = document.getElementById("modal-share");
  if (!shareDiv) return;
  shareDiv.querySelectorAll(".share-btn").forEach((btn) => {
    const clone = btn.cloneNode(true);
    btn.parentNode.replaceChild(clone, btn);
    const platform = clone.dataset.platform;
    clone.addEventListener("click", (e) => {
      e.stopPropagation();
      let shareUrl;
      if (platform === "linkedin") shareUrl = `https://www.linkedin.com/sharing/share-offsite/?url=${url}`;
      else if (platform === "twitter") shareUrl = `https://twitter.com/intent/tweet?text=${title}&url=${url}`;
      else if (platform === "telegram") shareUrl = `https://t.me/share/url?url=${url}&text=${title}`;
      else if (platform === "copy") {
        navigator.clipboard.writeText(decodeURIComponent(url)).then(() => showToast("Link copied!", "success")).catch(() => showToast("Copy failed.", "error"));
        return;
      }
      if (shareUrl) window.open(shareUrl, "_blank", "noopener,noreferrer,width=600,height=400");
    });
  });
}

/* ===== Animated Counters ===== */
function initAnimatedCounters() {
  const section = document.getElementById("stats-counters");
  if (!section) return;
  let animated = false;
  const observer = new IntersectionObserver((entries) => {
    if (entries[0].isIntersecting && !animated && state.dataLoaded) {
      animated = true;
      animateCounter("counter-projects", state.projects.length);
      animateCounter("counter-experiences", state.experiences.length);
      animateCounter("counter-skills", state.skills.length);
      observer.disconnect();
    }
  }, { threshold: 0.3 });
  observer.observe(section);
}

function animateCounter(id, target) {
  const el = document.getElementById(id);
  if (!el) return;
  const duration = 1200;
  const start = performance.now();
  function step(now) {
    const progress = Math.min((now - start) / duration, 1);
    const eased = 1 - Math.pow(1 - progress, 3);
    el.textContent = Math.round(eased * target);
    if (progress < 1) requestAnimationFrame(step);
  }
  requestAnimationFrame(step);
}

/* ===== Live GitHub Activity Strip ===== */
async function initGithubActivity() {
  const container = document.getElementById("github-activity-strip");
  if (!container) return;
  const link = document.querySelector('a[href*="github.com"]');
  const match = link?.href.match(/github\.com\/([^/?#]+)/i);
  const username = match?.[1];
  if (!username) {
    document.getElementById("github-activity-section")?.remove();
    return;
  }

  try {
    const res = await fetch(`https://api.github.com/users/${encodeURIComponent(username)}/events/public?per_page=6`);
    if (!res.ok) throw new Error(`GitHub API ${res.status}`);
    const events = await res.json();
    renderGithubActivity(container, Array.isArray(events) ? events.slice(0, 6) : []);
  } catch (err) {
    container.innerHTML = `<div class="gh-activity-error">// couldn't load GitHub activity right now</div>`;
  }
}

function describeGithubEvent(event) {
  const repo = event.repo?.name || "unknown/repo";
  switch (event.type) {
    case "PushEvent": {
      const n = event.payload?.commits?.length || 0;
      return { icon: "arrow-up-circle-outline", text: `pushed ${n} commit${n === 1 ? "" : "s"} to` , repo };
    }
    case "CreateEvent":
      return { icon: "add-circle-outline", text: `created a ${event.payload?.ref_type || "ref"} in`, repo };
    case "PullRequestEvent":
      return { icon: "git-pull-request-outline", text: `${event.payload?.action || "updated"} a pull request in`, repo };
    case "IssuesEvent":
      return { icon: "alert-circle-outline", text: `${event.payload?.action || "updated"} an issue in`, repo };
    case "IssueCommentEvent":
      return { icon: "chatbubble-outline", text: "commented on an issue in", repo };
    case "WatchEvent":
      return { icon: "star-outline", text: "starred", repo };
    case "ForkEvent":
      return { icon: "git-branch-outline", text: "forked", repo };
    default:
      return { icon: "git-commit-outline", text: `${(event.type || "activity").replace("Event", "").toLowerCase()} in`, repo };
  }
}

function timeAgo(dateStr) {
  const diffMs = Date.now() - new Date(dateStr).getTime();
  const mins = Math.floor(diffMs / 60000);
  if (mins < 60) return `${Math.max(mins, 0)}m ago`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  if (days < 30) return `${days}d ago`;
  return `${Math.floor(days / 30)}mo ago`;
}

function renderGithubActivity(container, events) {
  if (!events.length) {
    container.innerHTML = `<div class="gh-activity-empty">// no recent public activity</div>`;
    return;
  }
  container.innerHTML = events.map((event) => {
    const { icon, text, repo } = describeGithubEvent(event);
    return `<div class="gh-activity-item">
      <ion-icon name="${escapeHtml(icon)}" aria-hidden="true"></ion-icon>
      <span class="gh-activity-text">${escapeHtml(text)} <strong>${escapeHtml(repo)}</strong></span>
      <span class="gh-activity-time">${escapeHtml(timeAgo(event.created_at))}</span>
    </div>`;
  }).join("");
}

/* ===== Visitor Hit Counter ===== */
function initHitCounter() {
  fetch("/api/hit-count", { method: "POST" }).catch(() => {});
  loadHitCount();
}

async function loadHitCount() {
  try {
    const res = await fetch("/api/hit-count");
    const data = await res.json();
    const el = document.getElementById("hit-counter-display");
    if (el) el.textContent = data.count?.toLocaleString() || "0";
  } catch { /* no-op */ }
}

/* ===== Admin Stats Dashboard ===== */
function initAdminStats() {
  const btn = document.getElementById("admin-stats-toggle");
  const panel = document.getElementById("admin-stats-panel");
  if (!btn || !panel) return;
  btn.addEventListener("click", () => {
    const visible = panel.style.display !== "none";
    panel.style.display = visible ? "none" : "block";
    if (!visible) renderAdminStats();
  });
}

function renderAdminStats() {
  const container = document.getElementById("admin-stats-content");
  if (!container) return;
  const projCats = {};
  state.projects.forEach((p) => { const c = p.category || "Uncategorised"; projCats[c] = (projCats[c] || 0) + 1; });
  const expCats = {};
  state.experiences.forEach((e) => { const c = e.category || "Uncategorised"; expCats[c] = (expCats[c] || 0) + 1; });
  const skillUsage = {};
  [...state.projects, ...state.experiences].forEach((item) => {
    parseSkills(item.skills).forEach((s) => { skillUsage[s] = (skillUsage[s] || 0) + 1; });
  });
  const topSkills = Object.entries(skillUsage).sort((a, b) => b[1] - a[1]).slice(0, 10);

  let html = `<div class="stats-section">
    <div class="stat-row"><span class="stat-label">Total Projects</span><span class="stat-value">${state.projects.length}</span></div>
    <div class="stat-row"><span class="stat-label">Total Experiences</span><span class="stat-value">${state.experiences.length}</span></div>
    <div class="stat-row"><span class="stat-label">Resume Items</span><span class="stat-value">${state.resume.length}</span></div>
    <div class="stat-row"><span class="stat-label">Skills Defined</span><span class="stat-value">${state.skills.length}</span></div>
  </div>`;

  html += `<h5 class="text-xs font-semibold text-ink-muted mt-3 mb-1">Projects by Category</h5>`;
  html += Object.entries(projCats).sort().map(([c, n]) => `<div class="stat-row"><span class="stat-label">${c}</span><span class="stat-value">${n}</span></div>`).join("");

  html += `<h5 class="text-xs font-semibold text-ink-muted mt-3 mb-1">Experiences by Category</h5>`;
  html += Object.entries(expCats).sort().map(([c, n]) => `<div class="stat-row"><span class="stat-label">${c}</span><span class="stat-value">${n}</span></div>`).join("");

  if (topSkills.length > 0) {
    html += `<h5 class="text-xs font-semibold text-ink-muted mt-3 mb-1">Top Skills</h5>`;
    html += topSkills.map(([s, n]) => `<div class="stat-row"><span class="stat-label">${s}</span><span class="stat-value">${n}</span></div>`).join("");
  }
  container.innerHTML = html;
}

/* ===== Admin Backup ===== */
function initAdminBackup() {
  const btn = document.getElementById("admin-backup-btn");
  if (!btn) return;
  btn.addEventListener("click", async () => {
    if (!state.isAdmin) return;
    btn.textContent = "Backing up...";
    btn.disabled = true;
    try {
      const res = await fetch("/api/admin/backup", { method: "POST" });
      const data = await res.json();
      if (res.ok) {
        showToast(data.message || "Backup complete.", "success");
        logActivity("Backup", "Exported all tables to S3");
      } else {
        showToast(data.error || "Backup failed.", "error");
      }
    } catch {
      showToast("Backup failed.", "error");
    }
    btn.innerHTML = '<ion-icon name="cloud-upload-outline" class="align-middle mr-1"></ion-icon>Backup to S3';
    btn.disabled = false;
  });
}

/* ===== Service Worker Registration ===== */
function registerServiceWorker() {
  if ("serviceWorker" in navigator) {
    navigator.serviceWorker.register("/sw.js", { scope: "/" }).catch(() => {});
  }
}

/* ===== Focus Trap for Modals ===== */
function trapFocus(container) {
  const getFocusable = () => [...container.querySelectorAll('button:not([hidden]):not([disabled]), [href]:not([hidden]), input:not([hidden]):not([type="hidden"]):not([tabindex="-1"]), select:not([hidden]), textarea:not([hidden])')].filter((el) => el.offsetParent !== null);
  container._focusTrap = (e) => {
    if (e.key !== "Tab") return;
    const focusable = getFocusable();
    if (focusable.length === 0) return;
    const first = focusable[0];
    const last = focusable[focusable.length - 1];
    if (e.shiftKey) {
      if (document.activeElement === first) { e.preventDefault(); last.focus(); }
    } else {
      if (document.activeElement === last) { e.preventDefault(); first.focus(); }
    }
  };
  container.addEventListener("keydown", container._focusTrap);
  const focusable = getFocusable();
  if (focusable.length > 0) setTimeout(() => focusable[0].focus(), 50);
}

function releaseFocusTrap(container) {
  if (container._focusTrap) {
    container.removeEventListener("keydown", container._focusTrap);
    delete container._focusTrap;
  }
}

function initFocusTrap() {
  const observer = new MutationObserver((mutations) => {
    mutations.forEach((m) => {
      if (m.type !== "attributes" || m.attributeName !== "class") return;
      const modal = m.target;
      if (!modal.classList.contains("modal-shell")) return;
      if (modal.classList.contains("active")) {
        trapFocus(modal.querySelector(".modal-card") || modal);
      } else {
        releaseFocusTrap(modal.querySelector(".modal-card") || modal);
      }
    });
  });
  document.querySelectorAll(".modal-shell").forEach((modal) => {
    observer.observe(modal, { attributes: true, attributeFilter: ["class"] });
  });
}

/* ===== ARIA Live Announcements ===== */
function announce(message) {
  const el = document.getElementById("aria-live");
  if (el) { el.textContent = ""; requestAnimationFrame(() => { el.textContent = message; }); }
}

/* ===== Keyboard Shortcuts Overlay ===== */
function initKeyboardShortcuts() {
  document.addEventListener("keydown", (e) => {
    const tag = e.target.tagName;
    if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") return;
    if (document.querySelector(".confirm-overlay") || document.querySelector(".lightbox-overlay")) return;
    // Don't intercept if any modal is active (except for ? and Esc)
    const modalActive = document.querySelector(".modal-shell.active");

    switch (e.key) {
      case "?":
        e.preventDefault();
        toggleShortcutsOverlay();
        break;
      case "1": case "2": case "3": case "4": case "5": case "6": {
        if (modalActive) return;
        const tabNames = ["about", "projects", "experiences", "resume", "stack", "contact"];
        const idx = parseInt(e.key) - 1;
        if (tabNames[idx]) { switchTab(tabNames[idx]); e.preventDefault(); }
        break;
      }
      case "t":
      case "T":
        if (!e.ctrlKey && !e.metaKey && !modalActive) {
          document.getElementById("theme-toggle")?.click();
          e.preventDefault();
        }
        break;
      case "/":
        if (modalActive) return;
        e.preventDefault();
        const activePanel = document.querySelector(".tab-panel.active");
        const searchInput = activePanel?.querySelector("input[type=\"text\"]");
        if (searchInput) searchInput.focus();
        break;
      case "[":
      case "]":
        if (modalActive) return;
        cycleIdeTab(e.key === "]" ? 1 : -1);
        e.preventDefault();
        break;
      case "w":
        if (!e.ctrlKey && !e.metaKey && !modalActive) {
          const activeTab = document.querySelector(".ide-tab.active")?.dataset.tab;
          if (activeTab) { closeIdeTab(activeTab, activeTab); e.preventDefault(); }
        }
        break;
    }
  });
}

function cycleIdeTab(dir) {
  const tabs = state.ideOpenTabs;
  if (tabs.length < 2) return;
  const activeTab = document.querySelector(".ide-tab.active")?.dataset.tab;
  const idx = tabs.indexOf(activeTab);
  const nextIdx = (idx + dir + tabs.length) % tabs.length;
  openIdeTabByName(tabs[nextIdx]);
}

function toggleShortcutsOverlay() {
  let overlay = document.getElementById("shortcuts-overlay");
  if (overlay) { overlay.remove(); return; }

  overlay = document.createElement("div");
  overlay.id = "shortcuts-overlay";
  overlay.className = "shortcuts-overlay";
  overlay.innerHTML = `
    <div class="shortcuts-card">
      <button class="modal-close" id="shortcuts-close" aria-label="Close shortcuts"><ion-icon name="close-outline"></ion-icon></button>
      <h3 class="text-xl font-bold text-white mb-4"><ion-icon name="keypad-outline" class="align-middle mr-2 text-accent"></ion-icon>Keyboard Shortcuts</h3>
      <div class="shortcuts-grid">
        <div class="shortcut-item"><kbd>\u2318</kbd>/<kbd>Ctrl</kbd>+<kbd>K</kbd><span>Command palette</span></div>
        <div class="shortcut-item"><kbd>\`</kbd><span>Toggle terminal</span></div>
        <div class="shortcut-item"><kbd>?</kbd><span>Toggle this guide</span></div>
        <div class="shortcut-item"><kbd>\u2190</kbd> <kbd>\u2192</kbd><span>Navigate cards</span></div>
        <div class="shortcut-item"><kbd>Enter</kbd><span>Open focused card</span></div>
        <div class="shortcut-item"><kbd>Esc</kbd><span>Close modal / overlay</span></div>
        <div class="shortcut-item"><kbd>T</kbd><span>Toggle dark / light theme</span></div>
        <div class="shortcut-item"><kbd>1</kbd>\u2013<kbd>6</kbd><span>Switch tabs</span></div>
        <div class="shortcut-item"><kbd>/</kbd><span>Focus search field</span></div>
        <div class="shortcut-item"><kbd>[</kbd> <kbd>]</kbd><span>Previous / next open tab</span></div>
        <div class="shortcut-item"><kbd>W</kbd><span>Close current tab</span></div>
        <div class="shortcut-item"><kbd>Dbl-click</kbd><span>Edit card (admin)</span></div>
      </div>
    </div>`;
  document.body.appendChild(overlay);
  overlay.querySelector("#shortcuts-close").addEventListener("click", () => overlay.remove());
  overlay.addEventListener("click", (e) => { if (e.target === overlay) overlay.remove(); });
}

/* ===== Command Palette ===== */
const cmdPaletteState = { items: [], filtered: [], activeIndex: 0 };

function fuzzyScore(query, target) {
  query = query.toLowerCase();
  target = target.toLowerCase();
  if (!query) return 0;
  const idx = target.indexOf(query);
  if (idx !== -1) return 1000 - idx;
  let qi = 0;
  let score = 0;
  for (let ti = 0; ti < target.length && qi < query.length; ti++) {
    if (target[ti] === query[qi]) { qi++; score++; }
  }
  return qi === query.length ? score : null;
}

function getCommandPaletteItems() {
  const items = [
    { icon: "person-outline", label: "About Me", hint: "bio.md", action: () => openIdeTabByName("about") },
    { icon: "folder-outline", label: "Projects", hint: "projects/", action: () => openIdeTabByName("projects") },
    { icon: "briefcase-outline", label: "Experiences", hint: "experiences/", action: () => openIdeTabByName("experiences") },
    { icon: "document-text-outline", label: "Resume", hint: "resume.pdf", action: () => openIdeTabByName("resume") },
    { icon: "extension-puzzle-outline", label: "Stack", hint: "stack.json", action: () => openIdeTabByName("stack") },
    { icon: "mail-outline", label: "Contact", hint: "contact.md", action: () => openIdeTabByName("contact") },
    { icon: "contrast-outline", label: "Toggle Theme", hint: "dark / light", action: () => document.getElementById("theme-toggle")?.click() },
    { icon: "keypad-outline", label: "Keyboard Shortcuts", hint: "?", action: () => toggleShortcutsOverlay() },
  ];
  if (typeof toggleTerminalPanel === "function") {
    items.push({ icon: "terminal-outline", label: "Open Terminal", hint: "`", action: () => toggleTerminalPanel() });
  }
  state.projects.forEach((p) => {
    items.push({ icon: "logo-python", label: p.title, hint: `projects/${p.category || ""}`, action: () => openItemTab(p, "projects") });
  });
  state.experiences.forEach((p) => {
    items.push({ icon: "document-outline", label: p.title, hint: `experiences/${p.category || ""}`, action: () => openItemTab(p, "experiences") });
  });
  const github = document.querySelector('a[href*="github.com"]');
  if (github?.href) items.push({ icon: "logo-github", label: "Open GitHub Profile", hint: "external", action: () => window.open(github.href, "_blank", "noopener") });
  const linkedin = document.querySelector('a[href*="linkedin.com"]');
  if (linkedin?.href) items.push({ icon: "logo-linkedin", label: "Open LinkedIn Profile", hint: "external", action: () => window.open(linkedin.href, "_blank", "noopener") });
  const mailLink = document.querySelector('a[href^="mailto:"]');
  if (mailLink?.href) {
    const email = mailLink.href.replace(/^mailto:/, "");
    items.push({ icon: "clipboard-outline", label: "Copy Email Address", hint: email, action: () => {
      navigator.clipboard?.writeText(email);
      showToast("Email copied to clipboard", "success");
    } });
  }
  return items;
}

function openCommandPalette() {
  if (document.getElementById("command-palette-overlay")) return;
  cmdPaletteState.items = getCommandPaletteItems();
  cmdPaletteState.filtered = cmdPaletteState.items;
  cmdPaletteState.activeIndex = 0;

  const overlay = document.createElement("div");
  overlay.id = "command-palette-overlay";
  overlay.className = "command-palette-overlay";
  overlay.innerHTML = `
    <div class="command-palette">
      <div class="command-palette-input-row">
        <span class="command-palette-prompt">&gt;</span>
        <input type="text" id="command-palette-input" class="command-palette-input" placeholder="Type a command or search..." autocomplete="off" spellcheck="false">
      </div>
      <div class="command-palette-results" id="command-palette-results"></div>
    </div>`;
  document.body.appendChild(overlay);
  renderCommandPaletteResults();

  const input = document.getElementById("command-palette-input");
  input.focus();
  input.addEventListener("input", () => {
    const q = input.value.trim();
    if (!q) {
      cmdPaletteState.filtered = cmdPaletteState.items;
    } else {
      cmdPaletteState.filtered = cmdPaletteState.items
        .map((item) => ({ item, score: fuzzyScore(q, item.label) }))
        .filter((r) => r.score !== null)
        .sort((a, b) => b.score - a.score)
        .map((r) => r.item);
    }
    cmdPaletteState.activeIndex = 0;
    renderCommandPaletteResults();
  });
  input.addEventListener("keydown", (e) => {
    if (e.key === "ArrowDown") { e.preventDefault(); moveCommandPaletteSelection(1); }
    else if (e.key === "ArrowUp") { e.preventDefault(); moveCommandPaletteSelection(-1); }
    else if (e.key === "Enter") { e.preventDefault(); activateCommandPaletteSelection(); }
    else if (e.key === "Escape") { e.preventDefault(); closeCommandPalette(); }
  });
  overlay.addEventListener("click", (e) => { if (e.target === overlay) closeCommandPalette(); });
}

function closeCommandPalette() {
  document.getElementById("command-palette-overlay")?.remove();
}

function renderCommandPaletteResults() {
  const results = document.getElementById("command-palette-results");
  if (!results) return;
  if (cmdPaletteState.filtered.length === 0) {
    results.innerHTML = `<div class="command-palette-empty">No matching commands</div>`;
    return;
  }
  results.innerHTML = cmdPaletteState.filtered.slice(0, 50).map((item, i) => `
    <div class="command-palette-item${i === cmdPaletteState.activeIndex ? " active" : ""}" data-idx="${i}">
      <ion-icon name="${item.icon}" aria-hidden="true"></ion-icon>
      <span class="command-palette-label">${escapeHtml(item.label)}</span>
      ${item.hint ? `<span class="command-palette-hint">${escapeHtml(item.hint)}</span>` : ""}
    </div>`).join("");
  results.querySelectorAll(".command-palette-item").forEach((el) => {
    el.addEventListener("click", () => {
      cmdPaletteState.activeIndex = parseInt(el.dataset.idx, 10);
      activateCommandPaletteSelection();
    });
    el.addEventListener("mouseenter", () => {
      cmdPaletteState.activeIndex = parseInt(el.dataset.idx, 10);
      results.querySelectorAll(".command-palette-item").forEach((it) => it.classList.remove("active"));
      el.classList.add("active");
    });
  });
  results.querySelector(".command-palette-item.active")?.scrollIntoView({ block: "nearest" });
}

function moveCommandPaletteSelection(dir) {
  const len = cmdPaletteState.filtered.length;
  if (!len) return;
  cmdPaletteState.activeIndex = (cmdPaletteState.activeIndex + dir + len) % len;
  renderCommandPaletteResults();
}

function activateCommandPaletteSelection() {
  const item = cmdPaletteState.filtered[cmdPaletteState.activeIndex];
  if (!item) return;
  closeCommandPalette();
  item.action();
}

function initCommandPalette() {
  document.addEventListener("keydown", (e) => {
    if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
      e.preventDefault();
      if (document.getElementById("command-palette-overlay")) closeCommandPalette();
      else openCommandPalette();
    }
  });
}

/* ===== Integrated Terminal Panel ===== */
const termState = { history: [], historyIndex: -1 };

function getAllTerminalFiles() {
  const files = [];
  state.projects.forEach((p) => files.push({ filename: `${slugifyTitle(p.title)}.py`, item: p, sectionTab: "projects" }));
  state.experiences.forEach((p) => files.push({ filename: `${slugifyTitle(p.title)}.md`, item: p, sectionTab: "experiences" }));
  return files;
}

function printTermLine(text, cls) {
  const body = document.getElementById("ide-terminal-body");
  if (!body) return;
  const line = document.createElement("div");
  line.className = `term-line${cls ? ` ${cls}` : ""}`;
  line.textContent = text;
  body.appendChild(line);
  body.scrollTop = body.scrollHeight;
}

function toggleTerminalPanel() {
  const panel = document.getElementById("ide-terminal-panel");
  if (!panel) return;
  if (panel.style.display === "none") openTerminalPanel();
  else closeTerminalPanel();
}

function openTerminalPanel() {
  const panel = document.getElementById("ide-terminal-panel");
  if (!panel) return;
  panel.style.display = "flex";
  if (!panel.dataset.welcomed) {
    printTermLine("CtrlAltJay portfolio shell. Type 'help' to see available commands.", "term-line--accent");
    panel.dataset.welcomed = "1";
  }
  document.getElementById("ide-terminal-input")?.focus();
}

function closeTerminalPanel() {
  const panel = document.getElementById("ide-terminal-panel");
  if (panel) panel.style.display = "none";
}

function runTerminalCommand(raw) {
  const trimmed = raw.trim();
  printTermLine(trimmed, "term-line--cmd");
  if (!trimmed) return;
  termState.history.push(trimmed);
  termState.historyIndex = termState.history.length;

  const [cmd, ...rest] = trimmed.split(/\s+/);
  const arg = rest.join(" ").replace(/\/$/, "");

  switch (cmd.toLowerCase()) {
    case "help":
      printTermLine("Available commands:");
      printTermLine("  help                 show this list");
      printTermLine("  whoami               about the site owner");
      printTermLine("  ls [projects|experiences]   list files");
      printTermLine("  cat <file>           open a file (e.g. cat about.md)");
      printTermLine("  open <github|linkedin>       open a social profile");
      printTermLine("  theme <dark|light>   switch theme");
      printTermLine("  resume | stack | contact    jump to a section");
      printTermLine("  banner               print an intro banner");
      printTermLine("  clear                clear the terminal");
      printTermLine("  exit                 close the terminal");
      break;
    case "whoami": {
      const name = document.querySelector(".profile-flyout-head h1")?.textContent.trim() || "visitor";
      const headline = document.querySelector(".profile-flyout-head .headline")?.textContent.trim() || "";
      printTermLine(name, "term-line--accent");
      if (headline) printTermLine(headline);
      break;
    }
    case "banner": {
      const name = document.querySelector(".profile-flyout-head h1")?.textContent.trim() || "CtrlAltJay";
      printTermLine(`> ${name}`, "term-line--accent");
      printTermLine("> Building practical systems that blend software, cloud, and AI.");
      printTermLine("> Type 'help' to explore this shell.");
      break;
    }
    case "ls": {
      if (!arg) {
        printTermLine("about/  projects/  experiences/  resume.pdf  contact.md");
      } else if (arg === "projects" || arg === "experiences") {
        const files = getAllTerminalFiles().filter((f) => f.sectionTab === arg);
        if (!files.length) printTermLine(`ls: ${arg}/: no entries yet`);
        else files.forEach((f) => printTermLine(`  ${f.filename}`));
      } else {
        printTermLine(`ls: cannot access '${arg}': no such directory`, "term-line--error");
      }
      break;
    }
    case "cat": {
      if (!arg) { printTermLine("usage: cat <file>", "term-line--error"); break; }
      if (arg === "about.md" || arg === "bio.md") { openIdeTabByName("about"); closeTerminalPanel(); break; }
      const files = getAllTerminalFiles();
      const match = files.find((f) => f.filename === arg || f.filename === `${arg}.py` || f.filename === `${arg}.md`);
      if (match) {
        openItemTab(match.item, match.sectionTab);
        closeTerminalPanel();
      } else {
        printTermLine(`cat: ${arg}: No such file or directory`, "term-line--error");
      }
      break;
    }
    case "open": {
      const target = arg.toLowerCase();
      if (target === "github" || target === "linkedin") {
        const link = document.querySelector(`a[href*="${target}.com"]`);
        if (link?.href) { window.open(link.href, "_blank", "noopener"); printTermLine(`Opening ${target}...`); }
        else printTermLine(`open: ${target} link not found`, "term-line--error");
      } else {
        printTermLine(`open: unknown target '${arg}'. Try 'open github' or 'open linkedin'.`, "term-line--error");
      }
      break;
    }
    case "theme": {
      const target = arg.toLowerCase();
      const isLight = document.documentElement.classList.contains("light-theme") || document.documentElement.dataset.theme === "light";
      if ((target === "dark" && isLight) || (target === "light" && !isLight)) {
        document.getElementById("theme-toggle")?.click();
        printTermLine(`Theme switched to ${target}.`);
      } else if (target === "dark" || target === "light") {
        printTermLine(`Already in ${target} theme.`);
      } else {
        printTermLine("usage: theme <dark|light>", "term-line--error");
      }
      break;
    }
    case "resume":
      openIdeTabByName("resume");
      closeTerminalPanel();
      break;
    case "stack":
      openIdeTabByName("stack");
      closeTerminalPanel();
      break;
    case "contact":
      openIdeTabByName("contact");
      closeTerminalPanel();
      break;
    case "clear":
      document.getElementById("ide-terminal-body").innerHTML = "";
      break;
    case "exit":
      closeTerminalPanel();
      break;
    default:
      printTermLine(`command not found: ${cmd}. Type 'help' for a list of commands.`, "term-line--error");
  }
}

function initTerminalPanel() {
  const closeBtn = document.getElementById("ide-terminal-close");
  const input = document.getElementById("ide-terminal-input");
  if (!closeBtn || !input) return;

  closeBtn.addEventListener("click", () => closeTerminalPanel());

  input.addEventListener("keydown", (e) => {
    if (e.key === "Enter") {
      e.preventDefault();
      const value = input.value;
      input.value = "";
      runTerminalCommand(value);
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      if (!termState.history.length) return;
      termState.historyIndex = Math.max(0, termState.historyIndex - 1);
      input.value = termState.history[termState.historyIndex] || "";
    } else if (e.key === "ArrowDown") {
      e.preventDefault();
      if (!termState.history.length) return;
      termState.historyIndex = Math.min(termState.history.length, termState.historyIndex + 1);
      input.value = termState.history[termState.historyIndex] || "";
    } else if (e.key === "Escape") {
      closeTerminalPanel();
    }
  });

  document.addEventListener("keydown", (e) => {
    if (e.key !== "`") return;
    const tag = e.target.tagName;
    if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") return;
    e.preventDefault();
    toggleTerminalPanel();
  });
}

/* ===== Admin JSON Import ===== */
function initJSONImport() {
  const btn = document.getElementById("admin-import-btn");
  if (!btn) return;
  btn.addEventListener("click", () => {
    if (!state.isAdmin) return;
    const input = document.createElement("input");
    input.type = "file";
    input.accept = ".json";
    input.addEventListener("change", async () => {
      const file = input.files[0];
      if (!file) return;
      try {
        const text = await file.text();
        const data = JSON.parse(text);
        const res = await fetch("/api/admin/import", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(data),
        });
        const result = await res.json();
        if (res.ok) {
          showToast(result.message, "success");
          logActivity("Import", result.message);
          await fetchData();
          wireProjectControls();
          updateTabBadges();
        } else {
          showToast(result.error || "Import failed.", "error");
        }
      } catch (err) {
        showToast("Invalid JSON file.", "error");
      }
    });
    input.click();
  });
}

/* ===== Surprise Me — random item button ===== */
function initSurpriseMe() {
  const btn = document.getElementById("surprise-me-btn");
  if (!btn) return;
  btn.addEventListener("click", () => {
    const allItems = [...state.projects, ...state.experiences];
    if (allItems.length === 0) { showToast("No items loaded yet.", "info"); return; }
    const random = allItems[Math.floor(Math.random() * allItems.length)];
    const tab = random.section === "experience" ? "experiences" : "projects";
    openItemTab(random, tab);
  });
}

/* ===== Mobile tab swipe gestures ===== */
function initMobileSwipe() {
  let touchStartX = 0;
  let touchStartY = 0;
  const content = document.querySelector(".content");
  if (!content) return;
  const tabOrder = ["about", "projects", "experiences", "resume", "stack", "contact"];
  content.addEventListener("touchstart", (e) => {
    touchStartX = e.changedTouches[0].screenX;
    touchStartY = e.changedTouches[0].screenY;
  }, { passive: true });
  content.addEventListener("touchend", (e) => {
    const dx = e.changedTouches[0].screenX - touchStartX;
    const dy = e.changedTouches[0].screenY - touchStartY;
    if (Math.abs(dx) < 60 || Math.abs(dy) > Math.abs(dx)) return;
    if (e.target.closest(".modal-shell, .recent-strip, .related-strip, .subsection-nav, .skills-filter-row, .modal-carousel")) return;
    const active = document.querySelector(".tab-btn.active");
    const currentIdx = tabOrder.indexOf(active?.dataset.tab);
    if (currentIdx === -1) return;
    const newIdx = dx < 0 ? currentIdx + 1 : currentIdx - 1;
    if (newIdx >= 0 && newIdx < tabOrder.length) {
      switchTab(tabOrder[newIdx]);
      window.history.replaceState(null, "", `#${tabOrder[newIdx]}`);
    }
  }, { passive: true });
}

/* ===== Unsaved draft pulsing indicator ===== */
function updateDraftIndicator() {
  const hasDraft = !!localStorage.getItem(DRAFT_KEY);
  document.querySelectorAll(".admin-inline-btn").forEach((btn) => {
    let dot = btn.querySelector(".draft-dot");
    if (hasDraft && state.isAdmin) {
      if (!dot) {
        dot = document.createElement("span");
        dot.className = "draft-dot";
        btn.style.position = "relative";
        btn.appendChild(dot);
      }
    } else if (dot) {
      dot.remove();
    }
  });
}

bootstrap();
