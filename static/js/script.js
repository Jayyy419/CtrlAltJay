'use strict';

// Element toggle function
const elementToggleFunc = function (elem) {
  elem.classList.toggle("active");
}

// Sidebar variables
const sidebar = document.querySelector("[data-sidebar]");
const sidebarBtn = document.querySelector("[data-sidebar-btn]");

// Sidebar toggle functionality for mobile
sidebarBtn.addEventListener("click", function () {
  elementToggleFunc(sidebar);
});

// Overlay and modal close functionality
const overlays = document.querySelectorAll("[data-overlay]");

// Add click event to overlay to close modals
overlays.forEach(overlay => {
  overlay.addEventListener("click", function () {
    document.querySelectorAll(".modal-container").forEach(modal => modal.classList.remove("active"));
    overlays.forEach(o => o.classList.remove("active")); // Ensure all overlays are closed
  });
});

// Testimonials variables
const testimonialsItem = document.querySelectorAll("[data-testimonials-item]");
const testimonialsModalContainer = document.querySelector("[data-modal-container]");
const testimonialsModalCloseBtn = document.querySelector("[data-modal-close-btn]");

// Modal variables for testimonials
const modalImg = document.querySelector("[data-modal-img]");
const modalTitle = document.querySelector("[data-modal-title]");
const modalText = document.querySelector("[data-modal-text]");

// Modal toggle function for testimonials
const testimonialsModalFunc = function () {
  elementToggleFunc(testimonialsModalContainer);
  document.querySelector("[data-overlay]").classList.toggle("active");
}

// Add click event to all testimonials items
testimonialsItem.forEach(item => {
  item.addEventListener("click", function () {
    modalImg.src = this.querySelector("[data-testimonials-avatar]").src;
    modalImg.alt = this.querySelector("[data-testimonials-avatar]").alt;
    modalTitle.innerHTML = this.querySelector("[data-testimonials-title]").innerHTML;
    modalText.innerHTML = this.querySelector("[data-testimonials-text]").innerHTML;
    testimonialsModalFunc();
  });
});

// Add click event to modal close button for testimonials
testimonialsModalCloseBtn.addEventListener("click", testimonialsModalFunc);

// Projects and Experiences modals
const projectsItem = document.querySelectorAll("[data-projects-item]");
const experiencesItem = document.querySelectorAll("[data-experiences-item]");

const projectModalContainer = document.querySelector("[data-project-modal-container]");
const experienceModalContainer = document.querySelector("[data-experience-modal-container]");

const projectModalCloseBtn = document.querySelector("[data-project-modal-close-btn]");
const experienceModalCloseBtn = document.querySelector("[data-experience-modal-close-btn]");

const projectModalImg = document.querySelector("[data-project-modal-img]");
const projectModalTitle = document.querySelector("[data-project-modal-title]");
const projectModalText = document.querySelector("[data-project-modal-text]");

const experienceModalImg = document.querySelector("[data-experience-modal-img]");
const experienceModalTitle = document.querySelector("[data-experience-modal-title]");
const experienceModalText = document.querySelector("[data-experience-modal-text]");

// Modal toggle function for projects
const projectModalFunc = function () {
  elementToggleFunc(projectModalContainer);
  projectModalContainer.querySelector("[data-overlay]").classList.toggle("active");
}

// Modal toggle function for experiences
const experienceModalFunc = function () {
  elementToggleFunc(experienceModalContainer);
  experienceModalContainer.querySelector("[data-overlay]").classList.toggle("active");
}

// Add click event to all projects items
projectsItem.forEach(item => {
  item.addEventListener("click", function () {
    projectModalImg.src = this.querySelector("img").src;
    projectModalImg.alt = this.querySelector("img").alt;
    projectModalTitle.innerHTML = this.querySelector(".project-title").innerHTML;
    projectModalText.innerHTML = this.querySelector(".project-description").innerHTML;
    projectModalFunc();
  });
});

// Add click event to all experiences items
experiencesItem.forEach(item => {
  item.addEventListener("click", function () {
    experienceModalImg.src = this.querySelector("img").src;
    experienceModalImg.alt = this.querySelector("img").alt;
    experienceModalTitle.innerHTML = this.querySelector(".project-title").innerHTML;
    experienceModalText.innerHTML = this.querySelector(".project-description").innerHTML;
    experienceModalFunc();
  });
});

// Add click event to modal close buttons for projects and experiences
projectModalCloseBtn.addEventListener("click", function() {
  elementToggleFunc(projectModalContainer);
  projectModalContainer.querySelector("[data-overlay]").classList.toggle("active");
});
experienceModalCloseBtn.addEventListener("click", function() {
  elementToggleFunc(experienceModalContainer);
  experienceModalContainer.querySelector("[data-overlay]").classList.toggle("active");
});

// Custom select variables
const select = document.querySelector("[data-select]");
const selectItems = document.querySelectorAll("[data-select-item]");
const selectValue = document.querySelector("[data-select-value]");
const filterBtn = document.querySelectorAll("[data-filter-btn]");

select.addEventListener("click", function () {
  elementToggleFunc(this);
});

// Add event in all select items
selectItems.forEach(item => {
  item.addEventListener("click", function () {
    let selectedValue = this.innerText.toLowerCase();
    selectValue.innerText = this.innerText;
    elementToggleFunc(select);
    filterFunc(selectedValue);
  });
});

// Filter variables
const filterItems = document.querySelectorAll("[data-filter-item]");

const filterFunc = function (selectedValue) {
  filterItems.forEach(item => {
    if (selectedValue === "all" || selectedValue === item.dataset.category) {
      item.classList.add("show");
      item.classList.remove("hide");
      item.classList.add("active");
    } else {
      item.classList.add("hide");
      item.classList.remove("show");
      item.addEventListener('animationend', () => {
        if (item.classList.contains('hide')) {
          item.classList.remove("active");
        }
      }, { once: true });
    }
  });
}

// Add event in all filter button items for large screen
let lastClickedBtn = filterBtn[0];

filterBtn.forEach(btn => {
  btn.addEventListener("click", function () {
    let selectedValue = this.innerText.toLowerCase();
    selectValue.innerText = this.innerText;
    filterFunc(selectedValue);
    lastClickedBtn.classList.remove("active");
    this.classList.add("active");
    lastClickedBtn = this;
  });
});

// Contact form variables
const form = document.querySelector("[data-form]");
const formInputs = document.querySelectorAll("[data-form-input]");
const formBtn = document.querySelector("[data-form-btn]");

// Add event to all form input field
formInputs.forEach(input => {
  input.addEventListener("input", function () {
    if (form.checkValidity()) {
      formBtn.removeAttribute("disabled");
    } else {
      formBtn.setAttribute("disabled", "");
    }
  });
});

// Page navigation variables
const navigationLinks = document.querySelectorAll("[data-nav-link]");
const pages = document.querySelectorAll("[data-page]");

// Add event to all nav link
navigationLinks.forEach(link => {
  link.addEventListener("click", function () {
    pages.forEach(page => {
      if (this.innerHTML.toLowerCase() === page.dataset.page) {
        page.classList.add("active");
        navigationLinks.forEach(nav => nav.classList.remove("active"));
        this.classList.add("active");
        window.scrollTo(0, 0);
      } else {
        page.classList.remove("active");
      }
    });
  });
});
