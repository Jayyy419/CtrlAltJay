(function () {
  "use strict";

  var main = document.getElementById("th-main");
  var nav = document.getElementById("th-nav");
  var statusEl = document.getElementById("th-status");
  var state = { view: "skyline", data: null, poll: null };
  var MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

  function esc(value) {
    return String(value == null ? "" : value)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
  }

  function say(text) { statusEl.textContent = text || ""; }

  function api(method, url) {
    return fetch(url, { method: method, credentials: "same-origin" }).then(function (res) {
      if (res.status === 404) { var e = new Error("gone"); e.status = 404; throw e; }
      return res.json().then(function (data) {
        if (!res.ok) throw new Error(data.error || "Request failed");
        return data;
      });
    });
  }

  // Every time shown in Town hall is Singapore time, whatever the device is set to.
  function sgParts(iso) {
    var d = new Date(iso);
    if (isNaN(d)) return null;
    var sg = new Date(d.getTime() + 8 * 3600 * 1000);
    return { y: sg.getUTCFullYear(), m: sg.getUTCMonth(), d: sg.getUTCDate(), h: sg.getUTCHours(), min: sg.getUTCMinutes() };
  }

  function sgStamp(iso) {
    var p = sgParts(iso);
    if (!p) return "";
    var h = p.h % 12 || 12;
    return p.d + " " + MONTHS[p.m] + " " + p.y + ", " + h + ":" + String(p.min).padStart(2, "0") + " " + (p.h >= 12 ? "pm" : "am");
  }

  function sgDate(iso) {
    var p = sgParts(iso);
    return p ? p.d + " " + MONTHS[p.m] + " " + p.y : "";
  }

  function signedOut() {
    main.innerHTML = '<div class="empty">You\'ve been signed out. <a href="/?admin=login" style="color:var(--accent)">Sign in again</a>.</div>';
    say("");
  }

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

  function nameCell(r) {
    var shown = r.public_name || r.full_name.split("/").pop();
    return '<span class="th-name">' + esc(shown) + "</span>" +
      '<span class="th-real">' + esc(r.full_name) + "</span>" +
      '<span class="badge ' + (r.private ? "private" : "public") + '">' + (r.private ? "Private" : "Public") + "</span>" + modeBadge(r) +
      (r.archived ? '<span class="badge mode-hidden">Boarded up</span>' : "");
  }

  function renderSkyline() {
    var d = state.data;
    var html = '<div class="cb-head"><div><h1 class="cb-title">The skyline</h1>' +
      '<div class="cb-meta">Every repo the GitHub token can see. New ones stay in the drawer until you approve them.</div></div>' +
      '<div class="cb-side-actions"><button type="button" class="btn primary" data-act="refresh"' + (d.run && d.run.status === "running" ? " disabled" : "") + ">Refresh now</button></div></div>";
    html += '<div class="th-run" role="status">' + runLine(d.run) + "</div>";
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
    html += "</tbody></table><div class=\"th-cards\">";
    d.repos.forEach(function (r) {
      var s = r.stats;
      html += '<div class="th-card">' + nameCell(r) + "<dl>" +
        "<div><dt>Floors</dt><dd>" + (s ? s.commits : "None yet") + "</dd></div>" +
        "<div><dt>Lights on</dt><dd>" + (s ? s.weeks_active + " weeks" : "None yet") + "</dd></div>" +
        "<div><dt>Built with</dt><dd>" + esc(s ? s.main_language || "Not known" : "Not counted") + "</dd></div>" +
        "<div><dt>Last built</dt><dd>" + esc(sgDate(r.pushed_at)) + "</dd></div></dl></div>";
    });
    html += "</div>";
    return html;
  }

  function renderTours() {
    return '<div class="cb-head"><div><h1 class="cb-title">Tours</h1><div class="cb-meta">Source Map tours, plotted stop by stop.</div></div></div>' +
      '<div class="empty">No maps yet. Plotting a stop comes once the skyline is approved.</div>';
  }

  function render() {
    nav.querySelectorAll("[data-view]").forEach(function (b) {
      if (b.getAttribute("data-view") === state.view) b.setAttribute("aria-current", "true");
      else b.removeAttribute("aria-current");
    });
    main.innerHTML = state.view === "tours" ? renderTours() : renderSkyline();
  }

  function load() {
    return api("GET", "/api/owner/townhall/repos").then(function (data) {
      state.data = data;
      render();
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
            say(data.run.status === "done" ? "Stats updated." : "The refresh stopped.");
          }
        }).catch(function () {});
      }, 5000);
    }
  }

  nav.addEventListener("click", function (e) {
    var b = e.target.closest("[data-view]");
    if (!b) return;
    state.view = b.getAttribute("data-view");
    render();
    var h = main.querySelector("h1");
    if (h) { h.setAttribute("tabindex", "-1"); h.focus(); }
  });

  main.addEventListener("click", function (e) {
    var act = e.target.closest("[data-act]");
    if (!act) return;
    if (act.getAttribute("data-act") === "refresh") {
      act.disabled = true;
      say("Starting a refresh...");
      api("POST", "/api/owner/townhall/refresh").then(function () {
        say("Refresh started.");
        return load();
      }).catch(function (err) {
        if (err.status === 404) return signedOut();
        act.disabled = false;
        say(err.message);
      });
    }
  });

  load();
})();
