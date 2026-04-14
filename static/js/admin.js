"use strict";

const tabButtons = document.querySelectorAll(".admin-tab");
const panels = {
  items: document.getElementById("items-panel"),
  resume: document.getElementById("resume-panel"),
  skills: document.getElementById("skills-panel"),
};

const toast = document.getElementById("toast");

function notify(message) {
  toast.textContent = message;
  toast.classList.add("show");
  setTimeout(() => toast.classList.remove("show"), 2400);
}

function setAdminTab(name) {
  tabButtons.forEach((btn) => btn.classList.toggle("active", btn.dataset.adminTab === name));
  Object.entries(panels).forEach(([key, panel]) => {
    panel.classList.toggle("active", key === name);
  });
}

tabButtons.forEach((btn) => {
  btn.addEventListener("click", () => setAdminTab(btn.dataset.adminTab));
});

function bindEditButton(button, fillForm) {
  button.addEventListener("click", () => fillForm());
}

async function sendForm(url, method, formData) {
  const response = await fetch(url, {
    method,
    body: formData,
  });

  if (!response.ok) {
    let message = "Request failed.";
    try {
      const payload = await response.json();
      message = payload.error || payload.message || message;
    } catch (_) {
      // no-op
    }
    throw new Error(message);
  }

  return response.json();
}

function collectFormData(formElement) {
  return new FormData(formElement);
}

const itemForm = document.getElementById("item-form");
const itemList = document.getElementById("item-list");
const itemFilterSection = document.getElementById("item-filter-section");

const clearPhotoFormBtn = document.getElementById("item-clear-photo");
const imagePathInput = document.getElementById("item-image-path");

function updateClearPhotoVisibility() {
  clearPhotoFormBtn.style.display = imagePathInput.value.trim() ? "inline-block" : "none";
}

imagePathInput.addEventListener("input", updateClearPhotoVisibility);

clearPhotoFormBtn.addEventListener("click", async () => {
  const itemId = document.getElementById("item-id").value;
  if (!confirm("Clear the photo for this item? This cannot be undone.")) return;

  if (itemId) {
    await fetch(`/api/admin/items/${itemId}/clear-image`, { method: "PATCH" });
    notify("Photo cleared");
    await loadItems();
  }

  imagePathInput.value = "";
  document.getElementById("item-image-file").value = "";
  updateClearPhotoVisibility();
});

function resetItemForm() {
  itemForm.reset();
  document.getElementById("item-id").value = "";
  updateClearPhotoVisibility();
}

document.getElementById("item-reset").addEventListener("click", resetItemForm);

async function loadItems() {
  const section = itemFilterSection.value;
  const query = section === "all" ? "" : `?section=${section}`;
  const response = await fetch(`/api/admin/items${query}`);
  const items = await response.json();

  itemList.innerHTML = "";
  items.forEach((item) => {
    const row = document.createElement("article");
    row.className = "list-item";

    const main = document.createElement("div");
    main.className = "list-main";
    main.innerHTML = `<h4>${item.title}</h4><p>${item.section} | ${item.category} | Updated ${item.updated_at}</p>`;

    const actions = document.createElement("div");
    actions.className = "list-actions";

    const editBtn = document.createElement("button");
    editBtn.textContent = "Edit";
    bindEditButton(editBtn, () => {
      document.getElementById("item-id").value = item.id;
      document.getElementById("item-section").value = item.section;
      document.getElementById("item-category").value = item.category || "";
      document.getElementById("item-title").value = item.title || "";
      document.getElementById("item-byline").value = item.byline || "";
      document.getElementById("item-tag").value = item.tag || "";
      document.getElementById("item-link").value = item.external_link || "";
      document.getElementById("item-summary").value = item.summary || "";
      document.getElementById("item-description").value = item.description || "";
      document.getElementById("item-date-label").value = item.date_label || "";
      document.getElementById("item-date-value").value = item.date_value || "";
      document.getElementById("item-deliverables").value = item.deliverables || "";
      document.getElementById("item-challenges").value = item.challenges || "";
      document.getElementById("item-future").value = item.future_improvements || "";
      document.getElementById("item-notes").value = item.extra_notes || "";
      document.getElementById("item-image-path").value = item.image_path || "";
      updateClearPhotoVisibility();
      window.scrollTo({ top: 0, behavior: "smooth" });
    });

    const deleteBtn = document.createElement("button");
    deleteBtn.className = "delete";
    deleteBtn.textContent = "Delete";
    deleteBtn.addEventListener("click", async () => {
      if (!confirm(`Delete ${item.title}?`)) {
        return;
      }
      await fetch(`/api/admin/items/${item.id}`, { method: "DELETE" });
      notify("Item deleted");
      await loadItems();
    });

    actions.appendChild(editBtn);
    if (item.image_path) {
      const clearPhotoBtn = document.createElement("button");
      clearPhotoBtn.className = "clear-photo";
      clearPhotoBtn.textContent = "Clear Photo";
      clearPhotoBtn.addEventListener("click", async () => {
        if (!confirm(`Clear the photo for "${item.title}"? This cannot be undone.`)) {
          return;
        }
        await fetch(`/api/admin/items/${item.id}/clear-image`, { method: "PATCH" });
        notify("Photo cleared");
        await loadItems();
      });
      actions.appendChild(clearPhotoBtn);
    }
    actions.appendChild(deleteBtn);
    row.appendChild(main);
    row.appendChild(actions);
    itemList.appendChild(row);
  });
}

itemFilterSection.addEventListener("change", loadItems);

itemForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const itemId = document.getElementById("item-id").value;
  const formData = collectFormData(itemForm);

  try {
    if (itemId) {
      await sendForm(`/api/admin/items/${itemId}`, "PUT", formData);
      notify("Item updated");
    } else {
      await sendForm("/api/admin/items", "POST", formData);
      notify("Item created");
    }

    resetItemForm();
    await loadItems();
  } catch (error) {
    notify(error.message);
  }
});

const resumeForm = document.getElementById("resume-form");
const resumeList = document.getElementById("resume-list");

function resetResumeForm() {
  resumeForm.reset();
  document.getElementById("resume-id").value = "";
  document.getElementById("resume-sort").value = "0";
}

document.getElementById("resume-reset").addEventListener("click", resetResumeForm);

async function loadResume() {
  const response = await fetch("/api/admin/resume");
  const rows = await response.json();

  resumeList.innerHTML = "";
  rows.forEach((row) => {
    const item = document.createElement("article");
    item.className = "list-item";

    const main = document.createElement("div");
    main.className = "list-main";
    main.innerHTML = `<h4>${row.title}</h4><p>${row.lane} | ${row.period} | order ${row.sort_order}</p>`;

    const actions = document.createElement("div");
    actions.className = "list-actions";

    const editBtn = document.createElement("button");
    editBtn.textContent = "Edit";
    bindEditButton(editBtn, () => {
      document.getElementById("resume-id").value = row.id;
      document.getElementById("resume-lane").value = row.lane;
      document.getElementById("resume-title").value = row.title || "";
      document.getElementById("resume-subtitle").value = row.subtitle || "";
      document.getElementById("resume-period").value = row.period || "";
      document.getElementById("resume-description").value = row.description || "";
      document.getElementById("resume-sort").value = row.sort_order || 0;
      window.scrollTo({ top: 0, behavior: "smooth" });
    });

    const deleteBtn = document.createElement("button");
    deleteBtn.className = "delete";
    deleteBtn.textContent = "Delete";
    deleteBtn.addEventListener("click", async () => {
      if (!confirm(`Delete ${row.title}?`)) {
        return;
      }
      await fetch(`/api/admin/resume/${row.id}`, { method: "DELETE" });
      notify("Resume item deleted");
      await loadResume();
    });

    actions.appendChild(editBtn);
    actions.appendChild(deleteBtn);
    item.appendChild(main);
    item.appendChild(actions);
    resumeList.appendChild(item);
  });
}

resumeForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const itemId = document.getElementById("resume-id").value;
  const formData = collectFormData(resumeForm);

  try {
    if (itemId) {
      await sendForm(`/api/admin/resume/${itemId}`, "PUT", formData);
      notify("Resume item updated");
    } else {
      await sendForm("/api/admin/resume", "POST", formData);
      notify("Resume item created");
    }
    resetResumeForm();
    await loadResume();
  } catch (error) {
    notify(error.message);
  }
});

const skillForm = document.getElementById("skill-form");
const skillList = document.getElementById("skill-list");

function resetSkillForm() {
  skillForm.reset();
  document.getElementById("skill-id").value = "";
  document.getElementById("skill-sort").value = "0";
}

document.getElementById("skill-reset").addEventListener("click", resetSkillForm);

async function loadSkills() {
  const response = await fetch("/api/admin/skills");
  const rows = await response.json();

  skillList.innerHTML = "";
  rows.forEach((row) => {
    const item = document.createElement("article");
    item.className = "list-item";

    const main = document.createElement("div");
    main.className = "list-main";
    main.innerHTML = `<h4>${row.name} (${row.level}%)</h4><p>${row.focus || "No focus"} | order ${row.sort_order}</p>`;

    const actions = document.createElement("div");
    actions.className = "list-actions";

    const editBtn = document.createElement("button");
    editBtn.textContent = "Edit";
    bindEditButton(editBtn, () => {
      document.getElementById("skill-id").value = row.id;
      document.getElementById("skill-name").value = row.name || "";
      document.getElementById("skill-level").value = row.level || 0;
      document.getElementById("skill-focus").value = row.focus || "";
      document.getElementById("skill-sort").value = row.sort_order || 0;
      window.scrollTo({ top: 0, behavior: "smooth" });
    });

    const deleteBtn = document.createElement("button");
    deleteBtn.className = "delete";
    deleteBtn.textContent = "Delete";
    deleteBtn.addEventListener("click", async () => {
      if (!confirm(`Delete ${row.name}?`)) {
        return;
      }
      await fetch(`/api/admin/skills/${row.id}`, { method: "DELETE" });
      notify("Skill deleted");
      await loadSkills();
    });

    actions.appendChild(editBtn);
    actions.appendChild(deleteBtn);
    item.appendChild(main);
    item.appendChild(actions);
    skillList.appendChild(item);
  });
}

skillForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const itemId = document.getElementById("skill-id").value;
  const formData = collectFormData(skillForm);

  try {
    if (itemId) {
      await sendForm(`/api/admin/skills/${itemId}`, "PUT", formData);
      notify("Skill updated");
    } else {
      await sendForm("/api/admin/skills", "POST", formData);
      notify("Skill created");
    }
    resetSkillForm();
    await loadSkills();
  } catch (error) {
    notify(error.message);
  }
});

async function bootstrap() {
  await loadItems();
  await loadResume();
  await loadSkills();
}

bootstrap();
