(function () {
  "use strict";

  var main = document.getElementById("cb-main");
  var listEl = document.getElementById("cb-list");
  var statusEl = document.getElementById("cb-status");
  var state = { cases: [], options: null, view: null, data: null, tab: "questions", q: 0 };

  var TABS = [
    ["questions", "Questions on the table"],
    ["evidence", "Your evidence"],
    ["loose", "Loose ends"],
    ["theirs", "Questions for them"],
  ];
  var PROVENANCE = {
    reported: "Reported",
    posting: "From the posting",
    usual: "Usual for this kind of role",
  };
  var LOOSE_KINDS = { question: "Unprepared question", skill: "Missing skill", revise: "To revise" };
  var MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

  function esc(value) {
    return String(value == null ? "" : value)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
  }

  function say(text) {
    statusEl.textContent = text || "";
  }

  function api(method, url, body) {
    var opts = { method: method, credentials: "same-origin", headers: {} };
    if (body !== undefined) {
      opts.headers["Content-Type"] = "application/json";
      opts.body = JSON.stringify(body);
    }
    return fetch(url, opts).then(function (res) {
      if (res.status === 404) {
        var err = new Error("gone");
        err.status = 404;
        throw err;
      }
      return res.json().then(function (data) {
        if (!res.ok) {
          var e = new Error(data.error || "Request failed");
          e.fields = data.fields || [];
          throw e;
        }
        return data;
      });
    });
  }

  function niceDate(iso) {
    if (!iso) return "";
    var p = iso.split("-");
    return parseInt(p[2], 10) + " " + MONTHS[parseInt(p[1], 10) - 1] + " " + p[0];
  }

  function stamp(iso) {
    var d = new Date(iso);
    if (isNaN(d)) return "";
    var h = d.getHours();
    var m = String(d.getMinutes()).padStart(2, "0");
    var ampm = h >= 12 ? "pm" : "am";
    h = h % 12 || 12;
    return d.getDate() + " " + MONTHS[d.getMonth()] + " " + d.getFullYear() + ", " + h + ":" + m + " " + ampm;
  }

  function caseTitle(c) {
    return c.role ? c.organisation + ": " + c.role : c.organisation;
  }

  /* ---------- sidebar ---------- */

  function renderList() {
    var html = '<div class="cb-list-label">Your cases</div>';
    if (!state.cases.length) {
      html += '<div class="cb-list-label" style="text-transform:none;letter-spacing:0">Nothing open yet.</div>';
    }
    state.cases.forEach(function (c) {
      html += '<button type="button" class="cb-file" data-open="case/' + esc(c.id) + '"' +
        (state.view === "case/" + c.id ? ' aria-current="true"' : "") + ">" + esc(caseTitle(c)) + "</button>";
    });
    html += '<div class="cb-list-label">Try it out</div>';
    html += '<button type="button" class="cb-file" data-open="sample"' +
      (state.view === "sample" ? ' aria-current="true"' : "") + ">Sample: Accenture</button>";
    listEl.innerHTML = html;
  }

  /* ---------- casebook view ---------- */

  function normalise(raw, sample) {
    var c = raw.casebook;
    return {
      sample: !!sample,
      casebook: c,
      competencies: raw.competencies || [],
      questions: raw.questions || [],
      evidence: raw.evidence || [],
      loose: raw.loose_ends || [],
      theirs: raw.questions_for_them || [],
    };
  }

  function costLine(c) {
    var cost = Number(c.cost_usd || 0).toFixed(2);
    if (c.research_status !== "done") return "<strong>US$" + cost + "</strong> · not researched yet";
    var n = c.searches || 0;
    return "<strong>US$" + cost + "</strong> · " + n + (n === 1 ? " search" : " searches");
  }

  function renderCase() {
    var d = state.data;
    var c = d.casebook;
    var fmt = state.options && state.options.formats[c.format];
    var meta = [];
    if (fmt && c.format !== "unknown") meta.push(fmt);
    if (c.date) meta.push(niceDate(c.date));
    meta.push(c.researched_at ? "Researched " + stamp(c.researched_at) : "Not researched yet");

    var html = '<div class="cb-head"><div>' +
      '<h1 class="cb-title">' + esc(caseTitle(c)) + (d.sample ? '<span class="sample">SAMPLE</span>' : "") + "</h1>" +
      '<div class="cb-meta">' + esc(meta.join(" · ")) + "</div></div>" +
      '<div class="cb-side-actions"><div class="cb-cost">' + costLine(c) + "</div>" +
      '<div class="cb-row">' +
      '<button type="button" class="btn primary" data-act="sheet">Day-of sheet</button>' +
      (d.sample ? "" : '<button type="button" class="btn" data-act="edit">Edit details</button>') +
      "</div></div></div>";

    if (d.sample) {
      html += '<p class="sample-note">Made-up research so you can try the screens. The organisation details and sources are invented; the evidence uses your real portfolio items.</p>';
    } else if (c.research_status !== "done") {
      html += '<p class="sample-note">Research isn\'t switched on yet. Once it is, this case fills with likely questions, where they came from, and which of your work answers them.</p>';
    }

    html += '<div class="cb-tabs" role="tablist" aria-label="Casebook sections">';
    TABS.forEach(function (t) {
      var count = { questions: d.questions.length, evidence: d.evidence.length, loose: d.loose.length, theirs: d.theirs.length }[t[0]];
      var on = state.tab === t[0];
      html += '<button type="button" role="tab" class="cb-tab" id="tab-' + t[0] + '" aria-controls="panel" aria-selected="' + on + '" tabindex="' + (on ? 0 : -1) + '" data-tab="' + t[0] + '">' +
        esc(t[1]) + '<span class="count">' + count + "</span></button>";
    });
    html += '</div><div id="panel" role="tabpanel" aria-labelledby="tab-' + state.tab + '">' + renderTab() + "</div>";

    if (!d.sample) {
      html += '<div class="actions" style="margin-top:40px"><button type="button" class="btn danger" data-act="close">Close the case</button></div>';
    }
    main.innerHTML = html;
  }

  function renderTab() {
    var d = state.data;
    if (state.tab === "questions") return renderQuestions(d);
    if (state.tab === "evidence") return renderEvidence(d);
    if (state.tab === "loose") return renderLoose(d);
    return renderTheirs(d);
  }

  function badge(kind) {
    return '<span class="pv ' + esc(kind) + '">' + esc(PROVENANCE[kind] || kind) + "</span>";
  }

  function renderQuestions(d) {
    if (!d.questions.length) {
      return '<div class="empty">No questions on the table yet. They come from research: what people report being asked, what the posting points to, and what\'s usual for this kind of role.</div>';
    }
    var q = d.questions[Math.min(state.q, d.questions.length - 1)];
    var html = '<div class="bench"><div class="qlist" aria-label="Questions">';
    d.questions.forEach(function (item, i) {
      html += '<button type="button" class="qitem" data-q="' + i + '"' + (item === q ? ' aria-current="true"' : "") + ">" +
        '<span class="kind">' + esc(item.kind) + "</span>" +
        '<div class="qt">' + esc(item.text) + "</div>" +
        '<div class="qm">' + badge(item.provenance) +
        "<span>" + (item.evidence && item.evidence.length ? item.evidence.length + " linked" : '<span class="gap">nothing linked</span>') + "</span>" +
        "</div></button>";
    });
    html += '</div><div class="detail" id="q-detail" tabindex="-1">';
    html += '<span class="kind">' + esc(q.kind) + "</span><h2>" + esc(q.text) + "</h2>";
    html += '<div class="src-line">' + badge(q.provenance) + sourceText(q) + "</div>";
    if (q.why) html += '<p class="why" style="margin-top:12px">' + esc(q.why) + "</p>";

    html += '<h3 class="h3">Your evidence</h3>';
    if (q.evidence && q.evidence.length) {
      html += '<div class="evc">';
      q.evidence.forEach(function (ev) {
        html += '<div class="card"><span class="rank">' + (ev.role === "lead" ? "Lead with" : "Back-up") + "</span><b>" + esc(ev.title) + "</b></div>";
      });
      html += "</div>";
    } else {
      html += '<p class="gap" style="margin:0 0 20px">Nothing in your portfolio answers this yet. It\'s on the loose ends.</p>';
    }

    if (q.star) {
      html += '<h3 class="h3">Outline</h3><dl class="star">';
      [["situation", "Situation"], ["task", "Task"], ["action", "Action"], ["result", "Result"]].forEach(function (f) {
        var v = q.star[f[0]];
        html += "<div><dt>" + f[1] + "</dt><dd>" + (v ? esc(v) : '<span class="gap">[your ' + f[0] + " here]</span>") + "</dd></div>";
      });
      html += "</dl>";
    }
    return html + "</div></div>";
  }

  function sourceText(q) {
    if (q.provenance === "reported" && q.sources && q.sources.length) {
      return q.sources.map(function (s) {
        var label = esc(s.title) + (s.date ? ", " + esc(niceDate(s.date)) : "");
        return s.url ? '<a href="' + esc(s.url) + '" rel="noopener noreferrer" target="_blank">' + label + "</a>" : "<span>" + label + "</span>";
      }).join("");
    }
    if (q.provenance === "posting" && q.requirement) {
      return "<span>Posting asks to &ldquo;" + esc(q.requirement) + "&rdquo;</span>";
    }
    return "";
  }

  function renderEvidence(d) {
    if (!d.evidence.length) {
      return '<div class="empty">No evidence lined up yet. Once the case knows what they\'re looking for, your portfolio items get matched to it here.</div>';
    }
    var comps = d.competencies;
    var html = '<div class="grid-wrap"><table class="cov"><caption class="sr">Which of your work covers each thing they look for</caption><thead><tr><th scope="col"><span class="sr">Item</span></th>';
    comps.forEach(function (k) { html += '<th scope="col">' + esc(k) + "</th>"; });
    html += "</tr></thead><tbody>";
    d.evidence.forEach(function (ev, i) {
      html += '<tr><th scope="row"><span class="rk">' + String(i + 1).padStart(2, "0") + "</span>" + esc(ev.title) + "</th>";
      comps.forEach(function (k) {
        var hit = (ev.covers || []).indexOf(k) !== -1;
        html += "<td>" + (hit ? '<span class="dot" role="img" aria-label="Covers ' + esc(k) + '"></span>' : '<span class="sr">No</span>') + "</td>";
      });
      html += "</tr>";
    });
    html += '</tbody><tfoot><tr><th scope="row">Items covering it</th>';
    comps.forEach(function (k) {
      var n = d.evidence.filter(function (ev) { return (ev.covers || []).indexOf(k) !== -1; }).length;
      html += "<td" + (n ? "" : ' class="none"') + ">" + n + "</td>";
    });
    html += "</tr></tfoot></table></div>";

    html += '<div class="cov-list">';
    d.evidence.forEach(function (ev) {
      html += '<div class="card" style="margin-bottom:8px"><b>' + esc(ev.title) + '</b><div class="chips">' +
        (ev.covers || []).map(function (k) { return '<span class="chip">' + esc(k) + "</span>"; }).join("") + "</div></div>";
    });
    var missing = comps.filter(function (k) {
      return !d.evidence.some(function (ev) { return (ev.covers || []).indexOf(k) !== -1; });
    });
    if (missing.length) html += '<p class="gap">Nothing covers: ' + esc(missing.join(", ")) + "</p>";
    return html + "</div>";
  }

  function renderLoose(d) {
    if (!d.loose.length) return '<div class="empty">No loose ends. Either you\'re ready or research hasn\'t run yet.</div>';
    return d.loose.map(function (l) {
      return '<div class="loose"><span class="kind">' + esc(LOOSE_KINDS[l.kind] || l.kind) + "</span><div>" + esc(l.text) + "</div></div>";
    }).join("");
  }

  function renderTheirs(d) {
    if (!d.theirs.length) return '<div class="empty">No questions for them yet. These get drafted from what research finds about the team and the role.</div>';
    return '<ol class="qft">' + d.theirs.map(function (t) { return "<li>" + esc(t) + "</li>"; }).join("") + "</ol>";
  }

  /* ---------- form ---------- */

  function renderForm(existing) {
    var o = state.options;
    var c = existing || { occasion: "interview", format: "unknown" };
    var html = '<div class="cb-head"><div><h1 class="cb-title">' + (existing ? "Edit the case" : "What's the case?") + "</h1>" +
      '<div class="cb-meta">' + (existing ? esc(caseTitle(existing)) : "Tell it what's coming up. Research fills in the rest.") + "</div></div></div>";
    html += '<form class="form" id="case-form" novalidate>';
    html += '<fieldset class="full"><legend>Occasion</legend><div class="occ">';
    Object.keys(o.occasions).forEach(function (k) {
      html += '<label><input type="radio" name="occasion" value="' + k + '"' + (c.occasion === k ? " checked" : "") + "><span>" + esc(o.occasions[k]) + "</span></label>";
    });
    html += "</div></fieldset>";
    html += field("organisation", "Organisation", '<input type="text" id="f-organisation" name="organisation" maxlength="120" required autocomplete="off" value="' + esc(c.organisation || "") + '">');
    html += field("role", "Role or programme", '<input type="text" id="f-role" name="role" maxlength="160" autocomplete="off" value="' + esc(c.role || "") + '">');
    html += field("date", "Date", '<input type="date" id="f-date" name="date" value="' + esc(c.date || "") + '">');
    var sel = '<select id="f-format" name="format">';
    Object.keys(o.formats).forEach(function (k) {
      sel += '<option value="' + k + '"' + (c.format === k ? " selected" : "") + ">" + esc(o.formats[k]) + "</option>";
    });
    html += field("format", "Format", sel + "</select>");
    html += field("posting_url", "Link to the posting", '<input type="url" id="f-posting_url" name="posting_url" maxlength="500" placeholder="https://" value="' + esc(c.posting_url || "") + '">', "full");
    if (!existing) {
      html += field("posting_text", "Or paste the posting", '<textarea id="f-posting_text" name="posting_text" rows="5"></textarea>', "full",
        "Read once when research runs and never kept. Research isn't on yet, so a link is the safer bet for now.");
    }
    html += field("notes", "Anything else you know", '<textarea id="f-notes" name="notes" rows="3" maxlength="4000">' + esc(c.notes || "") + "</textarea>", "full");
    html += '<div class="full actions"><button type="submit" class="btn primary">' + (existing ? "Save changes" : "Build the case") + "</button>" +
      (existing ? '<button type="button" class="btn" data-act="cancel-edit">Cancel</button>' : "") +
      '<span class="err" id="form-err" role="alert"></span></div></form>';
    main.innerHTML = html;

    document.getElementById("case-form").addEventListener("submit", function (e) {
      e.preventDefault();
      submitForm(e.target, existing);
    });
  }

  function field(name, label, control, cls, hint) {
    return '<div class="' + (cls || "") + '"><label for="f-' + name + '">' + esc(label) + "</label>" + control +
      (hint ? '<div class="hint">' + esc(hint) + "</div>" : "") + "</div>";
  }

  var FIELD_ERRORS = {
    occasion: "Pick an occasion.",
    organisation: "Who's it with? The organisation is needed.",
    date: "That date doesn't look right.",
    format: "Pick a format.",
    posting_url: "The link needs to start with https://.",
  };

  function submitForm(form, existing) {
    var data = {};
    new FormData(form).forEach(function (v, k) { data[k] = typeof v === "string" ? v.trim() : v; });
    var errEl = document.getElementById("form-err");
    form.querySelectorAll("[aria-invalid]").forEach(function (el) { el.removeAttribute("aria-invalid"); });
    if (!data.organisation) {
      showErrors(["organisation"], errEl);
      return;
    }
    var btn = form.querySelector("button[type=submit]");
    btn.disabled = true;
    say(existing ? "Saving..." : "Opening the case...");
    var req = existing ? api("PATCH", "/api/owner/casebooks/" + existing.id, data) : api("POST", "/api/owner/casebooks", data);
    req.then(function (saved) {
      say(existing ? "Saved." : "Case opened.");
      return loadCases().then(function () { go("case/" + saved.id); });
    }).catch(function (err) {
      btn.disabled = false;
      say("");
      if (err.status === 404) return signedOut();
      showErrors(err.fields && err.fields.length ? err.fields : [], errEl, err.message);
    });
  }

  function showErrors(fields, errEl, fallback) {
    var msgs = fields.map(function (f) {
      var el = document.getElementById("f-" + f);
      if (el) el.setAttribute("aria-invalid", "true");
      return FIELD_ERRORS[f] || "Check " + f + ".";
    });
    errEl.textContent = msgs.length ? msgs.join(" ") : (fallback || "That didn't save. Try again.");
    var first = fields.length && document.getElementById("f-" + fields[0]);
    if (first) first.focus();
  }

  /* ---------- navigation ---------- */

  function signedOut() {
    main.innerHTML = '<div class="empty">You\'ve been signed out. <a href="/" style="color:var(--accent)">Sign in again</a> to open your cases.</div>';
    say("");
  }

  function go(view) {
    if (location.hash.slice(1) !== view) {
      location.hash = view;
    } else {
      route();
    }
  }

  function route() {
    var view = location.hash.slice(1) || (state.cases.length ? "case/" + state.cases[0].id : "sample");
    state.view = view;
    renderList();
    if (view === "new") {
      renderForm(null);
      focusMain();
      return;
    }
    var load;
    if (view === "sample") {
      load = api("GET", "/api/owner/casebooks/sample").then(function (raw) { return normalise(raw, true); });
    } else if (/^case\/[0-9a-f]{12}$/.test(view)) {
      load = api("GET", "/api/owner/casebooks/" + view.slice(5)).then(function (raw) { return normalise(raw, false); });
    } else {
      location.hash = "";
      return;
    }
    say("Opening...");
    load.then(function (data) {
      if (state.view !== view) return;
      if (!state.data || state.data.casebook.id !== data.casebook.id) {
        state.tab = "questions";
        state.q = 0;
      }
      state.data = data;
      renderCase();
      say("");
      focusMain();
    }).catch(function (err) {
      if (err.status === 404 && view !== "sample") {
        main.innerHTML = '<div class="empty">That case isn\'t here any more. It may have been closed.</div>';
        say("");
        return;
      }
      if (err.status === 404) return signedOut();
      main.innerHTML = '<div class="empty">Couldn\'t open that case. Check your connection and try again.</div>';
      say("");
    });
  }

  function focusMain() {
    var h = main.querySelector("h1");
    if (h) {
      h.setAttribute("tabindex", "-1");
      h.focus({ preventScroll: true });
    }
    window.scrollTo(0, 0);
  }

  function loadCases() {
    return api("GET", "/api/owner/casebooks").then(function (items) {
      state.cases = items;
    });
  }

  /* ---------- events ---------- */

  document.getElementById("cb-new").addEventListener("click", function () { go("new"); });

  listEl.addEventListener("click", function (e) {
    var b = e.target.closest("[data-open]");
    if (b) go(b.getAttribute("data-open"));
  });

  main.addEventListener("click", function (e) {
    var tab = e.target.closest("[data-tab]");
    if (tab) {
      state.tab = tab.getAttribute("data-tab");
      renderCase();
      document.getElementById("tab-" + state.tab).focus();
      return;
    }
    var q = e.target.closest("[data-q]");
    if (q) {
      state.q = parseInt(q.getAttribute("data-q"), 10);
      renderCase();
      var detail = document.getElementById("q-detail");
      if (window.matchMedia("(max-width: 760px)").matches) {
        detail.focus();
      } else {
        main.querySelector('[data-q="' + state.q + '"]').focus();
      }
      return;
    }
    var act = e.target.closest("[data-act]");
    if (!act) return;
    var name = act.getAttribute("data-act");
    if (name === "sheet") {
      say("The day-of sheet arrives in a later update.");
    } else if (name === "edit") {
      renderForm(state.data.casebook);
      focusMain();
    } else if (name === "cancel-edit") {
      renderCase();
      focusMain();
    } else if (name === "close") {
      var c = state.data.casebook;
      if (!window.confirm("Close the case for " + caseTitle(c) + "? This deletes it for good.")) return;
      say("Closing...");
      api("DELETE", "/api/owner/casebooks/" + c.id).then(function () {
        state.data = null;
        say("Case closed.");
        return loadCases().then(function () { go(state.cases.length ? "case/" + state.cases[0].id : "sample"); });
      }).catch(function (err) {
        if (err.status === 404) return signedOut();
        say("Couldn't close it. Try again.");
      });
    }
  });

  main.addEventListener("keydown", function (e) {
    var tab = e.target.closest && e.target.closest('[role="tab"]');
    if (!tab || (e.key !== "ArrowRight" && e.key !== "ArrowLeft" && e.key !== "Home" && e.key !== "End")) return;
    e.preventDefault();
    var ids = TABS.map(function (t) { return t[0]; });
    var i = ids.indexOf(state.tab);
    if (e.key === "ArrowRight") i = (i + 1) % ids.length;
    if (e.key === "ArrowLeft") i = (i - 1 + ids.length) % ids.length;
    if (e.key === "Home") i = 0;
    if (e.key === "End") i = ids.length - 1;
    state.tab = ids[i];
    renderCase();
    document.getElementById("tab-" + state.tab).focus();
  });

  window.addEventListener("hashchange", route);

  Promise.all([api("GET", "/api/owner/casebook/options"), loadCases()]).then(function (res) {
    state.options = res[0];
    route();
  }).catch(function (err) {
    if (err.status === 404) return signedOut();
    main.innerHTML = '<div class="empty">Casebook didn\'t load. Check your connection and refresh.</div>';
  });
})();
