(function () {
  "use strict";

  var main = document.getElementById("th-main");
  var nav = document.getElementById("th-nav");
  var statusEl = document.getElementById("th-status");
  var state = { view: "skyline", data: null, poll: null, repo: null, preview: null, log: null };
  var MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  var SIZES = ["Small", "Medium", "Large", "Extra large"];

  function esc(value) {
    return String(value == null ? "" : value)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
  }

  function say(text) { statusEl.textContent = text || ""; }

  function api(method, url, body) {
    var opts = { method: method, credentials: "same-origin", headers: {} };
    if (body !== undefined) { opts.headers["Content-Type"] = "application/json"; opts.body = JSON.stringify(body); }
    return fetch(url, opts).then(function (res) {
      if (res.status === 404) { var e = new Error("gone"); e.status = 404; throw e; }
      return res.json().then(function (data) {
        if (!res.ok) throw new Error(data.error || "That didn't work. Try again.");
        return data;
      });
    });
  }

  // Every time shown in Town hall is Singapore time, whatever the device is set to.
  function sgParts(ms) {
    var d = new Date(ms + 8 * 3600 * 1000);
    return isNaN(d) ? null : { y: d.getUTCFullYear(), m: d.getUTCMonth(), d: d.getUTCDate(), h: d.getUTCHours(), min: d.getUTCMinutes() };
  }
  function sgStamp(iso) {
    var p = iso ? sgParts(Date.parse(iso)) : null;
    if (!p) return "";
    var h = p.h % 12 || 12;
    return p.d + " " + MONTHS[p.m] + " " + p.y + ", " + h + ":" + String(p.min).padStart(2, "0") + " " + (p.h >= 12 ? "pm" : "am");
  }
  function sgDate(iso) { var p = iso ? sgParts(Date.parse(iso)) : null; return p ? p.d + " " + MONTHS[p.m] + " " + p.y : ""; }
  function sgDateTs(ts) { var p = ts ? sgParts(ts * 1000) : null; return p ? p.d + " " + MONTHS[p.m] + " " + p.y : ""; }

  function failed(err) {
    if (err && err.status === 404) return signedOut();
    say(err && err.message ? err.message : "That didn't work. Try again.");
  }

  function signedOut() {
    main.innerHTML = '<div class="empty">You\'ve been signed out. <a href="/?admin=login" style="color:var(--accent)">Sign in again</a>.</div>';
    say("");
  }

  function focusHeading() {
    var h = main.querySelector("h1");
    if (h) { h.setAttribute("tabindex", "-1"); h.focus(); }
  }

  /* ---------- the skyline list ---------- */

  function runLine(run) {
    if (!run || !run.status) return '<span class="cb-meta">No stats yet. Refresh to take the first count.</span>';
    if (run.status === "running") return '<span class="cb-meta"><span class="spin" aria-hidden="true" style="display:inline-block;vertical-align:-3px;margin-right:6px"></span>Counting floors. This takes a minute or two.</span>';
    var when = sgStamp(run.finished_at || run.started_at);
    if (run.status === "done") {
      return '<span class="cb-meta">Stats as of ' + esc(when) + " · " + run.repos + " repo" + (run.repos === 1 ? "" : "s") +
        (run.errors ? ' · <span class="gap">' + run.errors + " couldn't be read</span>" : "") + "</span>";
    }
    if (run.status === "rate_limited") {
      return '<span class="err">GitHub asked us to slow down. The last count stopped early; try again after ' + esc(sgStamp(run.reset_at)) + ".</span>";
    }
    return '<span class="err">The last refresh stopped (' + esc(run.error || "unknown error") + "). Stats are from the run before.</span>";
  }

  function modeBadge(r) {
    if (!r.visible_to_token) return '<span class="badge gone">Token can\'t see it</span>';
    return r.mode === "approved" ? '<span class="badge mode-approved">On the skyline</span>' : '<span class="badge mode-hidden">In the drawer</span>';
  }

  function shownName(r) { return r.public_name || (r.private ? "Unnamed private repo" : r.full_name.split("/").pop()); }

  function nameCell(r) {
    return '<button type="button" class="th-open" data-repo="' + esc(r.id) + '">' + esc(shownName(r)) + "</button>" +
      '<span class="th-real">' + esc(r.full_name) + "</span>" +
      '<span class="badge ' + (r.private ? "private" : "public") + '">' + (r.private ? "Private" : "Public") + "</span>" + modeBadge(r) +
      (r.archived ? '<span class="badge mode-hidden">Boarded up</span>' : "");
  }

  function publishedLine(d) {
    var p = d.published || {};
    if (!p.at) return "Nothing is on the public skyline yet.";
    return "Public skyline: " + p.count + " building" + (p.count === 1 ? "" : "s") + ", published " + sgStamp(p.at) + ".";
  }

  function renderSkyline() {
    var d = state.data;
    var running = d.run && d.run.status === "running";
    var html = '<div class="cb-head"><div><h1 class="cb-title">The skyline</h1>' +
      '<div class="cb-meta">Every repo the GitHub token can see. New ones stay in the drawer until you approve them.</div></div>' +
      '<div class="cb-side-actions"><div class="cb-row">' +
      '<button type="button" class="btn" data-act="publish">Publish latest stats</button>' +
      '<button type="button" class="btn primary" data-act="refresh"' + (running ? " disabled" : "") + ">Refresh now</button></div></div></div>";
    html += '<div class="th-run" role="status">' + runLine(d.run) + '<span class="cb-meta">' + esc(publishedLine(d)) + "</span></div>";
    if (!d.repos.length) {
      return html + '<div class="empty">No repos yet. Press Refresh now to see what the token can reach. Nothing appears on the public site until you approve it.</div>';
    }
    html += '<table class="th-table"><caption class="sr">Repos the token can see</caption><thead><tr><th scope="col">Repo</th><th scope="col">Built with</th>' +
      '<th scope="col" class="num">Floors</th><th scope="col" class="num">Lights on</th><th scope="col">Last built</th></tr></thead><tbody>';
    d.repos.forEach(function (r) {
      var s = r.stats;
      html += "<tr><td>" + nameCell(r) + "</td><td>" + esc(s ? s.main_language || "Not known" : "Not counted yet") + "</td>" +
        '<td class="num">' + (s ? s.commits : "") + '</td><td class="num">' + (s ? s.weeks_active + " wk" : "") + "</td>" +
        "<td>" + esc(sgDate(r.pushed_at)) + "</td></tr>";
    });
    html += '</tbody></table><div class="th-cards">';
    d.repos.forEach(function (r) {
      var s = r.stats;
      html += '<div class="th-card">' + nameCell(r) + "<dl>" +
        "<div><dt>Floors</dt><dd>" + (s ? s.commits : "None yet") + "</dd></div>" +
        "<div><dt>Lights on</dt><dd>" + (s ? s.weeks_active + " weeks" : "None yet") + "</dd></div>" +
        "<div><dt>Built with</dt><dd>" + esc(s ? s.main_language || "Not known" : "Not counted") + "</dd></div>" +
        "<div><dt>Last built</dt><dd>" + esc(sgDate(r.pushed_at)) + "</dd></div></dl></div>";
    });
    return html + "</div>";
  }

  /* ---------- one repo ---------- */

  function publicRows(b, r) {
    var rows = [
      ["Name", b.name || '<span class="gap">[needs a public name]</span>', !b.name],
      ["Description", b.description || '<span class="gap">[needs a description]</span>', !b.description],
      ["Built with", (b.languages || []).map(function (l) { return esc(l[0]) + " " + Math.round(l[1] * 100) + "%"; }).join(" · ") || "Not known"],
      ["Floors", String(b.commits)],
      ["Lights on", b.weeks_active + " weeks"],
      ["Weekly history", b.weeks.length + " weeks with commits, counts only"],
      ["Last built", sgDateTs(b.last_push) || "Not known"],
    ];
    if (r.private) rows.push(["Size", SIZES[(b.size_class || 1) - 1] + " (a size class, not a byte count)"]);
    else {
      rows.push(["Code size", (b.bytes || 0).toLocaleString("en-GB") + " bytes"]);
      rows.push(["GitHub link", b.github_url ? esc(b.github_url) : "None"]);
      rows.push(["Boarded up", b.archived ? "Yes" : "No"]);
    }
    rows.push(["Project page", b.project_url ? esc(b.project_url) : "None"]);
    return rows.map(function (row) {
      var value = row[1];
      if (row[0] === "Name" || row[0] === "Description") value = row[2] ? row[1] : esc(row[1]);
      return '<tr><th scope="row">' + row[0] + "</th><td>" + value + "</td></tr>";
    }).join("");
  }

  function renderRepo() {
    var r = state.repo, p = state.preview, b = p.building;
    var html = '<p class="cb-meta" style="margin:0 0 6px"><button type="button" class="linkish" data-act="back">The skyline</button> / ' + esc(shownName(r)) + "</p>" +
      '<div class="cb-head"><div><h1 class="cb-title">' + esc(shownName(r)) + "</h1>" +
      '<div class="cb-meta">' + esc(r.full_name) + " · only you see this name</div>" +
      '<div><span class="badge ' + (r.private ? "private" : "public") + '">' + (r.private ? "Private" : "Public") + "</span>" + modeBadge(r) + "</div></div></div>";
    html += '<div class="th-detail"><form id="repo-form" class="form" novalidate>' +
      '<div class="full"><label for="f-name">Public name' + (r.private ? " (required)" : "") + '</label>' +
      '<input type="text" id="f-name" maxlength="60" value="' + esc(r.public_name) + '" placeholder="' + esc(r.private ? "What visitors will see" : r.full_name.split("/").pop()) + '"></div>' +
      '<div class="full"><label for="f-desc">Description' + (r.private ? " (required)" : "") + '</label>' +
      '<textarea id="f-desc" maxlength="280" rows="3" placeholder="' + esc(r.private ? "One or two sentences, in your words" : r.gh_description || "One or two sentences") + '">' + esc(r.description) + "</textarea></div>" +
      '<div class="full"><label for="f-project">Project page on CtrlAltJay</label><select id="f-project"><option value="">None</option>' +
      (p.projects || []).map(function (it) { return '<option value="' + esc(it.id) + '"' + (it.id === r.project_item_id ? " selected" : "") + ">" + esc(it.title) + "</option>"; }).join("") +
      '</select></div><div class="full actions"><button type="submit" class="btn">Save the words</button></div></form>';
    html += '<section class="th-public" aria-labelledby="pub-h"><h2 class="h3" id="pub-h">What goes public</h2>' +
      (r.private ? '<p class="hint" style="margin:0 0 10px">A private repo publishes only these. Its real name, file names, branches, commit messages and links never leave Town hall.</p>' : "") +
      '<table class="th-pubtable">' + publicRows(b, r) + "</table>" +
      (p.problems && p.problems.length ? '<ul class="th-problems">' + p.problems.map(function (x) { return "<li>" + esc(x) + "</li>"; }).join("") + "</ul>" : "") +
      '<div class="actions" style="margin-top:14px">' +
      '<a class="btn" href="/owner/townhall/preview/' + esc(r.id) + '" target="_blank" rel="noopener">Preview the building</a>' +
      (r.mode === "approved"
        ? '<button type="button" class="btn danger" data-act="drawer">Keep it in the drawer</button>'
        : '<button type="button" class="btn primary" data-act="approve"' + (p.problems && p.problems.length ? " disabled" : "") + ">Approve for the skyline</button>") +
      "</div>" + (r.approved_at ? '<p class="hint">On the skyline since ' + esc(sgStamp(r.approved_at)) + ".</p>" : "") + "</section></div>";
    return html;
  }

  function openRepo(id) {
    var r = state.data.repos.filter(function (x) { return String(x.id) === String(id); })[0];
    if (!r) return;
    say("Opening...");
    api("GET", "/api/owner/townhall/repos/" + id + "/preview").then(function (p) {
      state.repo = r;
      state.preview = p;
      state.view = "repo";
      render();
      focusHeading();
      say("");
    }).catch(failed);
  }

  function reloadRepo(message) {
    var id = state.repo.id;
    return load(true).then(function () {
      return api("GET", "/api/owner/townhall/repos/" + id + "/preview");
    }).then(function (p) {
      state.repo = state.data.repos.filter(function (x) { return String(x.id) === String(id); })[0];
      state.preview = p;
      render();
      say(message);
    });
  }

  /* ---------- approvals log ---------- */

  var ACTIONS = { approve: "Approved for the skyline", drawer: "Put in the drawer", publish: "Published latest stats", update: "Changed the words on" };

  function renderLog() {
    var rows = state.log || [];
    var html = '<div class="cb-head"><div><h1 class="cb-title">Approvals log</h1><div class="cb-meta">What you approved and when, newest first.</div></div></div>';
    if (!rows.length) return html + '<div class="empty">Nothing approved yet.</div>';
    html += '<table class="th-log"><thead><tr><th scope="col">When</th><th scope="col">What</th></tr></thead><tbody>';
    rows.forEach(function (row) {
      html += "<tr><td>" + esc(sgStamp(row.at)) + "</td><td>" + esc(ACTIONS[row.action] || row.action) +
        (row.repo ? " " + esc(row.repo) : "") + (row.detail ? ' <span class="cb-meta">(' + esc(row.detail) + ")</span>" : "") + "</td></tr>";
    });
    return html + "</tbody></table>";
  }

  function renderTours() {
    return '<div class="cb-head"><div><h1 class="cb-title">Tours</h1><div class="cb-meta">Source Map tours, plotted stop by stop.</div></div></div>' +
      '<div class="empty">No maps yet. Plotting a stop comes in a later step.</div>';
  }

  function render() {
    var navView = state.view === "repo" ? "skyline" : state.view;
    nav.querySelectorAll("[data-view]").forEach(function (b) {
      if (b.getAttribute("data-view") === navView) b.setAttribute("aria-current", "true");
      else b.removeAttribute("aria-current");
    });
    if (state.view === "tours") main.innerHTML = renderTours();
    else if (state.view === "log") main.innerHTML = renderLog();
    else if (state.view === "repo") main.innerHTML = renderRepo();
    else main.innerHTML = renderSkyline();
  }

  function load(quiet) {
    return api("GET", "/api/owner/townhall/repos").then(function (data) {
      state.data = data;
      if (!quiet) render();
      watch();
    }).catch(function (err) {
      if (err.status === 404) return signedOut();
      main.innerHTML = '<div class="empty">Town hall didn\'t load. Check your connection and refresh.</div>';
    });
  }

  function watch() {
    var running = state.data && state.data.run && state.data.run.status === "running";
    if (running && !state.poll) {
      state.poll = setInterval(function () {
        api("GET", "/api/owner/townhall/repos").then(function (data) {
          var still = data.run && data.run.status === "running";
          if (!still) {
            clearInterval(state.poll);
            state.poll = null;
            state.data = data;
            if (state.view === "skyline") render();
            say(data.run.status === "done" ? "Stats updated. Publish them when you're ready." : "The refresh stopped.");
          }
        }).catch(function () {});
      }, 5000);
    }
  }

  nav.addEventListener("click", function (e) {
    var b = e.target.closest("[data-view]");
    if (!b) return;
    state.view = b.getAttribute("data-view");
    if (state.view === "log") {
      api("GET", "/api/owner/townhall/approvals").then(function (rows) { state.log = rows; render(); focusHeading(); }).catch(failed);
      return;
    }
    render();
    focusHeading();
  });

  main.addEventListener("click", function (e) {
    var open = e.target.closest("[data-repo]");
    if (open) return openRepo(open.getAttribute("data-repo"));
    var act = e.target.closest("[data-act]");
    if (!act) return;
    var name = act.getAttribute("data-act");
    if (name === "back") {
      state.view = "skyline";
      render();
      var btn = main.querySelector('[data-repo="' + state.repo.id + '"]');
      if (btn) btn.focus();
    } else if (name === "refresh") {
      act.disabled = true;
      say("Starting a refresh...");
      api("POST", "/api/owner/townhall/refresh").then(function () { say("Refresh started."); return load(); }).catch(function (err) { act.disabled = false; failed(err); });
    } else if (name === "publish") {
      act.disabled = true;
      api("POST", "/api/owner/townhall/publish").then(function (r) {
        say("Published: " + r.buildings + " building" + (r.buildings === 1 ? "" : "s") + " on the public skyline.");
        return load();
      }).catch(function (err) { act.disabled = false; failed(err); });
    } else if (name === "approve") {
      var r = state.repo;
      var msg = r.private
        ? "Approve " + shownName(r) + " for the skyline? Only what's listed under What goes public will be published."
        : "Approve " + shownName(r) + " for the skyline? Its name, stats and GitHub link will be public.";
      if (!window.confirm(msg)) return;
      api("POST", "/api/owner/townhall/repos/" + r.id + "/approve").then(function () { return reloadRepo("Approved. It's on the public skyline."); }).catch(failed);
    } else if (name === "drawer") {
      if (!window.confirm("Take " + shownName(state.repo) + " off the public skyline?")) return;
      api("POST", "/api/owner/townhall/repos/" + state.repo.id + "/drawer").then(function () { return reloadRepo("In the drawer. It's gone from the public skyline."); }).catch(failed);
    }
  });

  main.addEventListener("submit", function (e) {
    if (e.target.id !== "repo-form") return;
    e.preventDefault();
    var body = {
      public_name: document.getElementById("f-name").value,
      description: document.getElementById("f-desc").value,
      project_item_id: document.getElementById("f-project").value,
    };
    say("Saving...");
    api("PATCH", "/api/owner/townhall/repos/" + state.repo.id, body)
      .then(function () { return reloadRepo(state.repo.mode === "approved" ? "Saved and republished." : "Saved."); })
      .catch(failed);
  });

  load();
})();
