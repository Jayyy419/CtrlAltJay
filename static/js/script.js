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
  currentSection: null, // Track which section is being created
};

const tabs = document.querySelectorAll(".tab-btn");
const panels = document.querySelectorAll(".tab-panel");

function initTabs() {
  tabs.forEach((btn) => {
    btn.addEventListener("click", () => {
      tabs.forEach((it) => it.classList.remove("active"));
      panels.forEach((panel) => panel.classList.remove("active"));
      btn.classList.add("active");
      document.getElementById(btn.dataset.tab).classList.add("active");
      window.scrollTo({ top: 0, behavior: "smooth" });
    });
  });
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

function buildCard(item) {
  const card = document.createElement("article");
  card.className = "card";

  const imagePath = item.image_path || "../static/images/Projects/WebDev_PortfolioV1.png";
  const img = document.createElement("img");
  img.src = imagePath;
  img.alt = item.title;

  const content = document.createElement("div");
  content.className = "card-content";

  const title = document.createElement("h4");
  title.textContent = item.title;

  const byline = document.createElement("p");
  byline.className = "byline";
  byline.textContent = item.byline ? `By ${item.byline}` : "By CtrlAltJay";

  const tag = document.createElement("span");
  tag.className = "tag";
  tag.textContent = item.tag || item.category;

  content.appendChild(title);
  content.appendChild(byline);
  content.appendChild(tag);

  card.appendChild(img);
  card.appendChild(content);

  card.addEventListener("click", () => openModal(item));

  return card;
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

function renderSubsectionNav(navId, categories) {
  const nav = document.getElementById(navId);
  if (!nav) return;
  
  nav.innerHTML = "";
  categories.forEach((category, index) => {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "subsection-btn shrink-0";
    if (index === 0) btn.classList.add("active"); // First item (All) is active by default
    btn.dataset.subsection = category;
    btn.textContent = category;
    nav.appendChild(btn);
  });
}

function renderSection(items, categoryId, sortId, targetGridId, subsectionFilter = null) {
  const selectedCategory = categoryId ? document.getElementById(categoryId).value : "All";
  const sortMode = document.getElementById(sortId).value;
  const target = document.getElementById(targetGridId);

  let filtered = items.filter(
    (item) => selectedCategory === "All" || item.category === selectedCategory
  );

  // Apply subsection filter if provided
  if (subsectionFilter && subsectionFilter.toLowerCase() !== "all") {
    if (subsectionFilter === "Uncategorised") {
      filtered = filtered.filter((item) => !item.category && !item.subsection);
    } else {
      filtered = filtered.filter((item) => item.category === subsectionFilter || item.subsection === subsectionFilter);
    }
  }

  // For experiences with no subsection filter specified but we have subsection buttons,
  // also allow items without a subsection to show if they match the category
  filtered = filtered.sort((a, b) => compareBySort(a, b, sortMode));

  target.innerHTML = "";
  filtered.forEach((item) => {
    target.appendChild(buildCard(item));
  });
}

function rowToHTML(label, value) {
  if (!value) {
    return "";
  }
  return `<div class="modal-row"><strong>${label}:</strong> ${value}</div>`;
}

function openModal(item) {
  state.modalItem = item;
  const shell = document.getElementById("detail-modal");
  const image = document.getElementById("modal-image");
  const title = document.getElementById("modal-title");
  const byline = document.getElementById("modal-byline");
  const tag = document.getElementById("modal-tag");
  const body = document.getElementById("modal-body");
  const link = document.getElementById("modal-link");

  image.src = item.image_path || "../static/images/Projects/WebDev_PortfolioV1.png";
  image.alt = item.title;
  title.textContent = item.title;
  byline.textContent = item.byline ? `By ${item.byline}` : "";
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

  if (item.external_link) {
    link.href = item.external_link;
    link.style.display = "inline-block";
  } else {
    link.style.display = "none";
  }

  shell.classList.add("active");
  shell.setAttribute("aria-hidden", "false");
}

function initModal() {
  const shell = document.getElementById("detail-modal");
  shell.querySelectorAll("[data-close-modal]").forEach((element) => {
    element.addEventListener("click", () => {
      state.modalItem = null;
      shell.classList.remove("active");
      shell.setAttribute("aria-hidden", "true");
    });
  });
}

function renderResume() {
  const educationTarget = document.getElementById("resume-education");
  const workTarget = document.getElementById("resume-work");

  educationTarget.innerHTML = "";
  workTarget.innerHTML = "";

  const education = state.resume.filter((item) => item.lane === "education");
  const work = state.resume.filter((item) => item.lane === "work");

  education.forEach((item) => educationTarget.appendChild(buildTimelineItem(item)));
  work.forEach((item) => workTarget.appendChild(buildTimelineItem(item)));
}

function buildTimelineItem(item) {
  const li = document.createElement("li");

  const title = document.createElement("h4");
  title.textContent = item.title;

  const subtitle = document.createElement("small");
  subtitle.textContent = item.subtitle || item.period;

  const period = document.createElement("small");
  period.textContent = item.subtitle ? item.period : "";

  const desc = document.createElement("p");
  desc.textContent = item.description || "";

  li.appendChild(title);
  li.appendChild(subtitle);
  li.appendChild(period);
  li.appendChild(desc);
  return li;
}

function renderSkills() {
  const target = document.getElementById("skills-grid");
  target.innerHTML = "";

  const tierOrder = ["Primary Stack", "Experienced", "Familiar"];
  const grouped = {};
  state.skills.forEach((skill) => {
    const tier = skill.focus || "Other";
    if (!grouped[tier]) grouped[tier] = [];
    grouped[tier].push(skill);
  });

  tierOrder.forEach((tier) => {
    const skills = grouped[tier];
    if (!skills || skills.length === 0) return;

    const section = document.createElement("div");
    section.className = "skill-tier mb-6";

    const heading = document.createElement("h4");
    heading.className = "skill-tier-heading text-sm font-semibold uppercase tracking-wider mb-3";
    heading.textContent = tier;
    section.appendChild(heading);

    const chipWrap = document.createElement("div");
    chipWrap.className = "flex flex-wrap gap-2";

    skills
      .sort((a, b) => (a.sort_order || 0) - (b.sort_order || 0))
      .forEach((skill) => {
        const chip = document.createElement("span");
        chip.className = "skill-chip skill-chip--" + tier.toLowerCase().replace(/\s+/g, "-");
        chip.textContent = skill.name;
        chipWrap.appendChild(chip);
      });

    section.appendChild(chipWrap);
    target.appendChild(section);
  });
}

async function fetchData() {
  const response = await fetch("/api/public-data");
  const payload = await response.json();
  state.projects = payload.projects || [];
  state.experiences = payload.experiences || [];
  state.resume = payload.resume || [];
  state.skills = payload.skills || [];
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
}

function findItemById(itemId) {
  return [...state.projects, ...state.experiences].find((item) => String(item.id) === String(itemId)) || null;
}

const CATEGORY_OPTIONS = {
  project: ["AI / ML", "Cloud & DevOps", "Community", "Innovation", "Operations", "Web Development"],
  experience: ["Achievements", "Career", "Certifications", "Events", "External Roles", "Testimonials", "Volunteers"],
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
  document.getElementById("admin-item-link").value = item?.external_link || "";

  // Show/hide section field and set modal title
  if (item) {
    sectionFieldGroup.style.display = "grid";
    title.textContent = "Edit Item";
    submit.textContent = "Save Changes";
  } else {
    sectionFieldGroup.style.display = "none";
    title.textContent = section === "experience" ? "Create New Experience" : "Create New Project";
    submit.textContent = "Create Item";
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
  const adminItemForm = document.getElementById("admin-item-form");
  const adminItemFeedback = document.getElementById("admin-item-feedback");

  if (!createProjectBtn || !createExperienceBtn || !editBtn || !adminItemForm || !adminItemFeedback) {
    return;
  }

  // Dynamic category options when section changes
  document.getElementById("admin-item-section").addEventListener("change", (e) => {
    populateCategoryDropdown(e.target.value, "");
  });

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
    const detailModal = document.getElementById("detail-modal");
    if (detailModal) {
      detailModal.classList.remove("active");
      detailModal.setAttribute("aria-hidden", "true");
    }
    openAdminItemModal(state.modalItem, state.modalItem.section || "project");
  });

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
    adminItemFeedback.textContent = "Saving...";

    try {
      await saveAdminItem(formData, itemId);
      await fetchData();
      wireProjectControls();
      adminItemFeedback.textContent = itemId ? "Item updated." : "Item created.";
      closeAdminItemModal();
      if (state.modalItem?.id && itemId) {
        const refreshedItem = findItemById(itemId);
        if (refreshedItem) {
          openModal(refreshedItem);
        }
      }
    } catch (error) {
      adminItemFeedback.textContent = error.message;
    }
  });
}

function wireProjectControls() {
  const projectCategories = uniqueCategories(state.projects);
  renderSubsectionNav("projects-subsection-nav", projectCategories);

  const experienceSubsections = uniqueSubsections(state.experiences);
  renderSubsectionNav("experiences-subsection-nav", experienceSubsections);

  state.rerenderProjects = () => {
    const activeSubsection = document.querySelector("#projects-subsection-nav .subsection-btn.active")?.dataset.subsection || "all";
    renderSection(state.projects, null, "projects-sort", "projects-grid", activeSubsection);
  };
  
  state.rerenderExperiences = () => {
    const activeSubsection = document.querySelector("#experiences-subsection-nav .subsection-btn.active")?.dataset.subsection || "all";
    renderSection(state.experiences, null, "experiences-sort", "experiences-grid", activeSubsection);
  };

  if (!state.controlsBound) {
    // Use event delegation so listeners survive nav regeneration
    document.getElementById("projects-subsection-nav").addEventListener("click", (e) => {
      const btn = e.target.closest(".subsection-btn");
      if (!btn) return;
      document.querySelectorAll("#projects-subsection-nav .subsection-btn").forEach((it) => it.classList.remove("active"));
      btn.classList.add("active");
      state.rerenderProjects();
    });

    document.getElementById("experiences-subsection-nav").addEventListener("click", (e) => {
      const btn = e.target.closest(".subsection-btn");
      if (!btn) return;
      document.querySelectorAll("#experiences-subsection-nav .subsection-btn").forEach((it) => it.classList.remove("active"));
      btn.classList.add("active");
      state.rerenderExperiences();
    });

    document.getElementById("projects-sort").addEventListener("change", () => state.rerenderProjects());
    document.getElementById("experiences-sort").addEventListener("change", () => state.rerenderExperiences());
    state.controlsBound = true;
  }

  state.rerenderProjects();
  state.rerenderExperiences();
}

async function bootstrap() {
  initTabs();
  initModal();
  initContactForm();
  initAdminAuth();
  initInlineAdminEditor();
  setAdminMode(false);
  await fetchData();
  wireProjectControls();
  renderResume();
  renderSkills();
}

function initContactForm() {
  const form = document.getElementById("contact-form");
  if (!form) return;

  // Real-time validation feedback
  const inputs = form.querySelectorAll("input, textarea");
  inputs.forEach((input) => {
    input.addEventListener("blur", () => validateField(input));
    input.addEventListener("input", () => {
      // Remove error state while typing
      input.classList.remove("invalid");
    });
  });

  // Form submission
  form.addEventListener("submit", (e) => {
    if (!isFormValid(form)) {
      e.preventDefault();
      scrollToFirstError(form);
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

bootstrap();
