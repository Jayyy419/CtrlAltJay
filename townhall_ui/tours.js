(function () {
  "use strict";

  var main = document.getElementById("th-main");
  var NS = "http://www.w3.org/2000/svg";
  var MAX_LINES = 40;
  var COLORS = ["#3794ff", "#c586c0", "#4ec9b0", "#dcdcaa", "#ce9178", "#9cdcfe", "#d7ba7d", "#b5cea8"];
  var t = { list: null, tour: null, files: null, district: null, file: null, sel: null, anchor: null, stop: null, mode: "start", filter: "", replace: null, dragging: null };
  var H;

  function esc(v) { return H.esc(v); }
  function mine() { return main.getAttribute("data-owner") === "tours"; }
  function base() { return "/api/owner/townhall/tours/" + t.tour.repo.id; }

  /* ---------- the list ---------- */

  function renderList() {
    var rows = t.list || [];
    var html = '<div class="cb-head"><div><h1 class="cb-title">Tours</h1><div class="cb-meta">Source Map tours, plotted stop by stop on the map visitors will walk.</div></div></div>';
    if (!rows.length) return html + '<div class="empty">Approve a repo for the skyline first. Its tour can be plotted here once it\'s on the skyline.</div>';
    html += '<div class="tt-list">';
    rows.forEach(function (r) {
      html += '<div class="th-card tt-card"><button type="button" class="th-open" data-tour="' + esc(r.id) + '">' + esc(r.name || "Unnamed") + "</button>" +
        '<span class="th-real">' + esc(r.full_name) + "</span>" +
        '<span class="badge ' + (r.private ? "private" : "public") + '">' + (r.private ? "Private" : "Public") + "</span>" +
        (r.mode !== "approved" ? '<span class="badge mode-hidden">In the drawer</span>' : "") +
        (r.published_slug ? '<span class="badge mode-approved">On the map at /map/' + esc(r.published_slug) + "</span>" : '<span class="badge mode-hidden">Not published</span>') +
        (r.needs_look ? '<span class="badge look">' + r.needs_look + " need a look</span>" : "") +
        (r.flagged ? '<span class="badge gone">' + r.flagged + " to check for secrets</span>" : "") +
        '<p class="cb-meta" style="margin:8px 0 0">' + (r.stops ? r.stops + " stop" + (r.stops === 1 ? "" : "s") : "No stops yet") +
        (r.published_at ? " · published " + esc(H.sgStamp(r.published_at)) : "") + "</p></div>";
    });
    return html + "</div>";
  }

  function showList(focus) {
    main.setAttribute("data-owner", "tours");
    H.say("Loading tours...");
    return H.api("GET", "/api/owner/townhall/tours").then(function (d) {
      t.list = d.tours;
      t.tour = null;
      main.innerHTML = renderList();
      H.say("");
      if (focus) H.focusHeading();
    }).catch(H.failed);
  }

  /* ---------- one tour ---------- */

  function districtOf(path) { return path.indexOf("/") === -1 ? "." : path.split("/")[0]; }
  function labelOf(name) {
    var d = (t.tour.districts || []).filter(function (x) { return x.name === name; })[0];
    return d ? d.shown_label : name;
  }
  function stopIndex(id) {
    for (var i = 0; i < t.tour.stops.length; i++) if (t.tour.stops[i].id === id) return i;
    return -1;
  }
  function shortSha(sha) { return sha ? sha.slice(0, 7) : ""; }

  function openTour(id) {
    main.setAttribute("data-owner", "tours");
    H.say("Opening...");
    return H.api("GET", "/api/owner/townhall/tours/" + id).then(function (d) {
      t.tour = d;
      t.files = null; t.district = null; t.file = null; t.sel = null; t.stop = null; t.replace = null;
      t.mode = d.stops.length ? "stop" : "start";
      if (d.stops.length) t.stop = d.stops[0].id;
      renderTour();
      H.focusHeading();
      H.say("");
    }).catch(H.failed);
  }

  function problemsBox() {
    var p = t.tour.problems || [];
    var looks = t.tour.stops.filter(function (s) { return s.needs_look; }).length;
    var html = "";
    if (p.length) html += '<div class="tt-flag" role="status"><b>Before you publish:</b><ul>' + p.map(function (x) { return "<li>" + esc(x) + "</li>"; }).join("") + "</ul></div>";
    if (looks) html += '<div class="tt-look">' + looks + " stop" + (looks === 1 ? " needs" : "s need") + " a look: the code changed since you plotted " + (looks === 1 ? "it" : "them") + ". Visitors still see the excerpt you approved.</div>";
    return html;
  }

  function settingsForm() {
    var d = t.tour;
    var html = '<form id="tt-settings" class="form tt-settings" novalidate>' +
      '<div><label for="tt-title">Tour title</label><input type="text" id="tt-title" maxlength="100" value="' + esc(d.title) + '" placeholder="' + esc("A tour of " + d.repo.name) + '"></div>' +
      '<div><label for="tt-slug">Address</label><div class="tt-slug"><span>/map/</span><input type="text" id="tt-slug" maxlength="61" value="' + esc(d.slug) + '" autocapitalize="off" spellcheck="false"></div></div>';
    if (d.repo.private && d.districts.length) {
      html += '<fieldset class="full tt-labels"><legend>District names visitors see</legend><p class="hint">Folder names stay in Town hall. Visitors see these instead.</p><div class="tt-label-grid">' +
        d.districts.map(function (x, i) {
          return '<div><label for="tt-l' + i + '">' + esc(x.name === "." ? "Top level" : x.name + "/") + ' <span class="hint">(only you see this)</span></label>' +
            '<input type="text" id="tt-l' + i + '" data-label="' + esc(x.name) + '" maxlength="30" value="' + esc(x.label) + '" placeholder="' + esc(x.shown_label) + '"></div>';
        }).join("") + "</div></fieldset>";
    }
    return html + '<div class="full actions"><button type="submit" class="btn">Save the details</button></div></form>';
  }

  function renderTour() {
    var d = t.tour;
    var pub = d.published_slug
      ? 'On the public site at <a href="/map/' + esc(d.published_slug) + '" target="_blank" rel="noopener">/map/' + esc(d.published_slug) + "</a> since " + esc(H.sgStamp(d.published_at)) + "."
      : "Not published yet. Nothing here is public until you press Publish the map.";
    var html = '<p class="cb-meta" style="margin:0 0 6px"><button type="button" class="linkish" data-tt="list">Tours</button> / ' + esc(d.repo.name) + "</p>" +
      '<div class="cb-head"><div><h1 class="cb-title">' + esc(d.repo.name) + "</h1>" +
      '<div class="cb-meta">' + esc(d.repo.full_name) + (d.sha ? " · plotting at " + esc(d.branch) + " " + esc(shortSha(d.sha)) : "") + "</div>" +
      '<div class="cb-meta">' + pub + "</div></div></div>" + settingsForm();
    html += '<div class="tt-stage"><div class="tt-map"><svg id="tt-svg" viewBox="0 0 700 500" role="group" aria-label="Map of the repo\'s districts. Choose a district to see its files."></svg></div>' +
      '<aside class="tt-drawer" id="tt-drawer" aria-live="polite"></aside>' +
      '<div class="tt-strip" role="toolbar" aria-label="Route"><span class="tt-strip-label" id="tt-route-label">Route</span><ol class="tt-pins" aria-labelledby="tt-route-label">' + pinsHtml() + "</ol>" +
      '<button type="button" class="tt-pin add" data-tt="plot">Plot a stop</button>' +
      '<div class="tt-strip-actions">' + (d.stops.length ? '<a class="btn" href="/owner/townhall/tour-preview/' + esc(d.repo.id) + '" target="_blank" rel="noopener">Preview</a>' : "") +
      (d.published_slug ? '<button type="button" class="btn danger" data-tt="unpublish">Take the map down</button>' : "") +
      '<button type="button" class="btn primary" data-tt="publish"' + (d.problems.length ? " disabled" : "") + ">Publish the map</button></div></div></div>" + problemsBox();
    main.innerHTML = html;
    drawMap();
    renderDrawer();
  }

  function pinsHtml() {
    return t.tour.stops.map(function (s, i) {
      var cls = "tt-pin" + (s.id === t.stop && t.mode === "stop" ? " cur" : "") + (s.scan && s.scan.status === "flagged" ? " warn" : "") + (s.needs_look ? " look" : "");
      var extra = (s.scan && s.scan.status === "flagged" ? ", check for secrets" : "") + (s.needs_look ? ", needs a look" : "");
      return '<li><button type="button" class="' + cls + '" draggable="true" data-pin="' + esc(s.id) + '" aria-label="Stop ' + (i + 1) + ": " + esc(s.title || "Untitled") + extra + '"' +
        (s.id === t.stop && t.mode === "stop" ? ' aria-current="step"' : "") + ">" + (i + 1) +
        (s.scan && s.scan.status === "flagged" ? '<span aria-hidden="true"> !</span>' : s.needs_look ? '<span aria-hidden="true"> ?</span>' : "") + "</button></li>";
    }).join("");
  }

  /* ---------- the map ---------- */

  function el(name, attrs, parent) {
    var e = document.createElementNS(NS, name);
    for (var k in attrs) e.setAttribute(k, attrs[k]);
    parent.appendChild(e);
    return e;
  }

  function treemap(items, x, y, w, h, out) {
    if (!items.length) return out;
    if (items.length === 1) { out.push({ d: items[0], x: x, y: y, w: w, h: h }); return out; }
    var total = items.reduce(function (a, d) { return a + Math.max(1, d.size); }, 0), acc = 0, cut = 0;
    for (var i = 0; i < items.length - 1; i++) { acc += Math.max(1, items[i].size); cut = i + 1; if (acc >= total / 2) break; }
    var share = items.slice(0, cut).reduce(function (a, d) { return a + Math.max(1, d.size); }, 0) / total;
    if (w >= h) {
      treemap(items.slice(0, cut), x, y, w * share, h, out);
      treemap(items.slice(cut), x + w * share, y, w * (1 - share), h, out);
    } else {
      treemap(items.slice(0, cut), x, y, w, h * share, out);
      treemap(items.slice(cut), x, y + h * share, w, h * (1 - share), out);
    }
    return out;
  }

  // Labels are cut to fit their district; the full name is in the aria-label.
  function fit(text, w, h) {
    if (h < 34) return "";
    var room = Math.floor((w - 22) / 8);
    if (room < 2) return "";
    return text.length > room ? text.slice(0, Math.max(1, room - 1)) + "\u2026" : text;
  }

  function drawMap() {
    var svg = document.getElementById("tt-svg"), d = t.tour;
    while (svg.firstChild) svg.removeChild(svg.firstChild);
    if (!d.districts.length) {
      var g0 = el("g", { class: "tt-load", tabindex: "0", role: "button", "data-tt": "load", "aria-label": "Load the file list" }, svg);
      el("rect", { x: 180, y: 200, width: 340, height: 100, rx: 10, fill: "#101540", stroke: "#3794ff" }, g0);
      var tx = el("text", { x: 350, y: 256, "text-anchor": "middle", class: "tt-d-label", fill: "#ffffff" }, g0);
      tx.textContent = "Load the file list to draw the map";
      return;
    }
    // Square roots even the sizes out, so a small folder is still big enough to tap.
    var sizes = d.districts.map(function (x) { return { name: x.name, label: x.shown_label, size: Math.sqrt(Math.max(1, x.size)) }; });
    var boxes = treemap(sizes.slice().sort(function (a, b) { return b.size - a.size; }), 14, 14, 672, 472, []);
    var byName = {};
    boxes.forEach(function (b, i) {
      var c = COLORS[i % COLORS.length], open = t.district === b.d.name;
      byName[b.d.name] = b;
      var g = el("g", { class: "tt-district" + (open ? " open" : ""), tabindex: "0", role: "button", "data-district": b.d.name,
        "aria-label": "Open " + b.d.label + (open ? ", open now" : "") }, svg);
      el("rect", { x: b.x + 3, y: b.y + 3, width: Math.max(0, b.w - 6), height: Math.max(0, b.h - 6), rx: 6, fill: c, "fill-opacity": open ? 0.2 : 0.08, stroke: c, "stroke-opacity": open ? 1 : 0.55, "stroke-width": open ? 2 : 1 }, g);
      var label = el("text", { x: b.x + 14, y: b.y + 26, class: "tt-d-label", fill: c }, g);
      label.textContent = fit(b.d.label + (b.d.label === b.d.name && b.d.name !== "." ? "/" : "") + (open ? " (open)" : ""), b.w, b.h);
    });
    var seen = {}, pins = d.stops.map(function (s) {
      var b = byName[s.district] || boxes[0];
      var total = d.stops.filter(function (q) { return q.district === s.district; }).length;
      var k = seen[s.district] = (seen[s.district] || 0) + 1;
      var fx = 0.22 + 0.56 * (total === 1 ? 0.5 : (k - 1) / (total - 1));
      return [b.x + b.w * fx, b.y + Math.max(40, b.h * (0.55 + (k % 2 ? -0.12 : 0.12)))];
    });
    if (pins.length > 1) {
      el("path", { d: "M" + pins.map(function (p) { return p[0].toFixed(1) + " " + p[1].toFixed(1); }).join(" L"), fill: "none", stroke: "#5aa2ff", "stroke-width": 2.5, "stroke-dasharray": "7 6", opacity: 0.9, "pointer-events": "none" }, svg);
    }
    pins.forEach(function (p, i) {
      var s = d.stops[i], cur = s.id === t.stop && t.mode === "stop";
      var ring = s.scan && s.scan.status === "flagged" ? "#f48771" : s.needs_look ? "#dcdcaa" : "#7fb6ff";
      var g = el("g", { class: "tt-mpin", "data-pin": s.id, "aria-hidden": "true" }, svg);
      el("circle", { cx: p[0], cy: p[1], r: cur ? 15 : 11, fill: cur ? "#1f4fd1" : "#0b0e22", stroke: cur ? "#ffffff" : ring, "stroke-width": 2.5 }, g);
      var n = el("text", { x: p[0], y: p[1] + 4, "text-anchor": "middle", class: "tt-pin-n" }, g);
      n.textContent = i + 1;
    });
  }

  /* ---------- the drawer ---------- */

  function renderDrawer() {
    var box = document.getElementById("tt-drawer");
    if (!box) return;
    if (t.mode === "files") box.innerHTML = drawerFiles();
    else if (t.mode === "code") box.innerHTML = drawerCode();
    else if (t.mode === "stop") box.innerHTML = drawerStop();
    else box.innerHTML = drawerStart();
  }

  function drawerStart() {
    if (!t.files) {
      return '<h2 class="tt-h">Plot a stop</h2><p>Load the file list from GitHub, then choose a district on the map to see its files.</p>' +
        '<button type="button" class="btn primary" data-tt="load">Load the file list</button>' +
        '<p class="tt-hint">The list comes from the latest commit on ' + esc(t.tour.branch || "the default branch") + ". Each stop keeps a copy of its lines from that commit.</p>";
    }
    return '<h2 class="tt-h">Plot a stop</h2><p>Choose a district on the map to see its files.</p><ul class="tt-dlist">' +
      t.tour.districts.map(function (x) { return '<li><button type="button" class="tt-row" data-district="' + esc(x.name) + '">' + esc(x.shown_label) + "</button></li>"; }).join("") + "</ul>";
  }

  function districtFiles() {
    var f = (t.filter || "").toLowerCase();
    return (t.files || []).filter(function (row) {
      return districtOf(row[0]) === t.district && (!f || row[0].toLowerCase().indexOf(f) !== -1);
    });
  }

  function drawerFiles() {
    var rows = districtFiles(), shown = rows.slice(0, 300);
    return '<p class="tt-crumb">' + esc(labelOf(t.district)) + " · " + esc(t.tour.branch) + " " + esc(shortSha(t.tour.sha)) + "</p>" +
      '<h2 class="tt-h">Files in ' + esc(labelOf(t.district)) + "</h2>" +
      '<label class="tt-lab" for="tt-filter">Find a file</label><input type="search" id="tt-filter" class="tt-input" value="' + esc(t.filter) + '" autocomplete="off">' +
      '<ul class="tt-files">' + shown.map(function (row) {
        return '<li><button type="button" class="tt-row" data-file="' + esc(row[0]) + '">' + esc(row[0]) + "</button></li>";
      }).join("") + "</ul>" +
      (rows.length > shown.length ? '<p class="tt-hint">Showing 300 of ' + rows.length + ". Type to narrow it down.</p>" : "") +
      (!rows.length ? '<p class="tt-hint">No files match.</p>' : "") +
      '<button type="button" class="btn" data-tt="start">All districts</button>';
  }

  function selInfo() {
    if (!t.sel) return "Choose the first line, then the last. Up to " + MAX_LINES + " lines.";
    var n = t.sel[1] - t.sel[0] + 1;
    return "Lines " + t.sel[0] + " to " + t.sel[1] + " selected · " + n + " of " + MAX_LINES + (n > MAX_LINES ? " (too many)" : "");
  }

  function codeTable(lines, start, mark, pickable) {
    var rows = lines.map(function (line, k) {
      var n = start + k, inSel = mark && n >= mark[0] && n <= mark[1];
      var num = pickable ? '<button type="button" class="tt-ln" data-line="' + n + '" aria-pressed="' + (inSel ? "true" : "false") + '">' + n + "</button>" : n;
      return "<tr" + (inSel ? ' class="sel"' : "") + '><td class="n">' + num + "</td><td>" + (esc(line) || " ") + "</td></tr>";
    }).join("");
    return '<div class="tt-code" tabindex="0" role="region" aria-label="Code"><table>' + rows + "</table></div>";
  }

  function drawerCode() {
    var f = t.file, sel = t.sel || [0, 0], old = t.replace ? t.tour.stops[stopIndex(t.replace)] : null;
    var html = '<p class="tt-crumb"><button type="button" class="linkish" data-tt="files">' + esc(labelOf(districtOf(f.path))) + "</button> · " + esc(shortSha(f.sha)) + "</p>" +
      '<h2 class="tt-h">' + esc(f.path) + "</h2>" + (old ? '<p class="tt-hint">Plotting stop ' + (stopIndex(old.id) + 1) + " again from the latest code.</p>" : "") +
      '<p class="tt-hint" id="tt-selinfo">' + selInfo() + "</p>" + codeTable(f.lines, 1, t.sel, true) +
      '<form id="tt-plot" class="tt-form" novalidate><div class="tt-two">' +
      '<div><label class="tt-lab" for="tt-from">First line</label><input type="number" id="tt-from" class="tt-input" min="1" max="' + f.lines.length + '" value="' + (sel[0] || "") + '"></div>' +
      '<div><label class="tt-lab" for="tt-to">Last line</label><input type="number" id="tt-to" class="tt-input" min="1" max="' + f.lines.length + '" value="' + (sel[1] || "") + '"></div></div>' +
      '<div class="tt-two"><div><label class="tt-lab" for="tt-mfrom">Highlight from</label><input type="number" id="tt-mfrom" class="tt-input" value="' + (sel[0] || "") + '"></div>' +
      '<div><label class="tt-lab" for="tt-mto">Highlight to</label><input type="number" id="tt-mto" class="tt-input" value="' + (sel[1] || "") + '"></div></div>' +
      '<label class="tt-lab" for="tt-stitle">Stop title</label><input type="text" id="tt-stitle" class="tt-input" maxlength="80" value="' + esc(old ? old.title : "") + '">' +
      '<label class="tt-lab" for="tt-sexp">What to notice</label><textarea id="tt-sexp" class="tt-input" maxlength="600" rows="4">' + esc(old ? old.explanation : "") + "</textarea>" +
      '<div class="tt-actions"><button type="submit" class="btn primary">' + (old ? "Plot it again" : "Plot a stop") + '</button><button type="button" class="btn" data-tt="files">Back to the files</button></div></form>';
    return html;
  }

  function drawerStop() {
    var i = stopIndex(t.stop), s = t.tour.stops[i];
    if (!s) { t.mode = "start"; return drawerStart(); }
    var html = '<p class="tt-crumb">Stop ' + (i + 1) + " of " + t.tour.stops.length + " · " + esc(labelOf(s.district)) + "</p>" +
      '<h2 class="tt-h">' + esc(s.title || "Untitled stop") + "</h2>" +
      '<p class="tt-hint">' + esc(s.path) + " · lines " + s.start + " to " + s.end + " · copied at " + esc(shortSha(s.sha)) + "</p>";
    if (s.scan && s.scan.status === "flagged") {
      html += '<div class="tt-flag"><b>This might hold a secret.</b><ul>' + s.scan.findings.map(function (f) {
        return "<li>Line " + f.line + " looks like " + esc(f.kind.toLowerCase()) + ".</li>";
      }).join("") + '</ul><div class="tt-actions"><button type="button" class="btn" data-tt="replot">Change the lines</button><button type="button" class="btn" data-tt="notsecret">It\'s not a secret</button></div></div>';
    } else if (s.scan && s.scan.status === "false_positive") {
      html += '<p class="tt-hint">Secret check: you marked this as not a secret.</p>';
    } else {
      html += '<p class="tt-hint">Secret check: <span class="tt-ok">clear</span></p>';
    }
    if (s.needs_look) {
      html += '<div class="tt-look"><b>Needs a look.</b> ' + (s.needs_look.gone ? "This file is gone from the latest code." : "These lines changed in the latest code.") +
        ' Visitors still see the excerpt you approved.<div class="tt-actions"><button type="button" class="btn" data-tt="replot">Plot it again</button><button type="button" class="btn" data-tt="keep">Keep as is</button></div></div>';
    }
    html += codeTable(s.lines, s.start, s.mark, false) +
      '<form id="tt-stop" class="tt-form" novalidate>' +
      '<label class="tt-lab" for="tt-stitle">Stop title</label><input type="text" id="tt-stitle" class="tt-input" maxlength="80" value="' + esc(s.title) + '">' +
      '<label class="tt-lab" for="tt-sexp">What to notice</label><textarea id="tt-sexp" class="tt-input" maxlength="600" rows="4">' + esc(s.explanation) + "</textarea>" +
      '<div class="tt-two"><div><label class="tt-lab" for="tt-mfrom">Highlight from</label><input type="number" id="tt-mfrom" class="tt-input" min="' + s.start + '" max="' + s.end + '" value="' + s.mark[0] + '"></div>' +
      '<div><label class="tt-lab" for="tt-mto">Highlight to</label><input type="number" id="tt-mto" class="tt-input" min="' + s.start + '" max="' + s.end + '" value="' + s.mark[1] + '"></div></div>' +
      '<div class="tt-actions"><button type="submit" class="btn primary">Save the stop</button>' +
      '<button type="button" class="btn" data-tt="earlier"' + (i === 0 ? " disabled" : "") + ">Move earlier</button>" +
      '<button type="button" class="btn" data-tt="later"' + (i === t.tour.stops.length - 1 ? " disabled" : "") + ">Move later</button>" +
      '<button type="button" class="btn danger" data-tt="remove">Remove the stop</button></div></form>';
    return html;
  }

  /* ---------- actions ---------- */

  function applied(d, message) {
    t.tour = d;
    renderTour();
    H.say(message || "");
  }

  function refocus(selector) {
    var e = main.querySelector(selector);
    if (e) e.focus();
  }

  function loadFiles() {
    H.say("Reading the file list from GitHub...");
    return H.api("POST", base() + "/tree").then(function (d) {
      t.files = d.files;
      delete d.files;
      var trunc = d.truncated;
      t.tour = d;
      t.mode = "start";
      renderTour();
      H.say(d.districts.length + " districts. Choose one on the map." + (trunc ? " The repo is big, so only part of the list came back." : ""));
      refocus("#tt-drawer .tt-row");
    }).catch(H.failed);
  }

  function openDistrict(name) {
    if (!t.files) return loadFiles().then(function () { if (t.files) openDistrict(name); });
    t.district = name;
    t.filter = "";
    t.mode = "files";
    drawMap();
    renderDrawer();
    refocus("#tt-filter");
  }

  function openFile(path, sel) {
    H.say("Opening " + path + "...");
    return H.api("POST", base() + "/file", { path: path }).then(function (f) {
      t.file = f;
      t.district = districtOf(path);
      t.sel = sel ? [Math.min(sel[0], f.lines.length), Math.min(sel[1], f.lines.length)] : null;
      t.anchor = null;
      t.mode = "code";
      drawMap();
      renderDrawer();
      H.say("");
      refocus("#tt-drawer .tt-h");
      var h = main.querySelector("#tt-drawer .tt-h");
      if (h) { h.setAttribute("tabindex", "-1"); h.focus(); }
      if (t.sel) scrollToLine(t.sel[0]);
    }).catch(H.failed);
  }

  function scrollToLine(n) {
    var b = main.querySelector('.tt-code [data-line="' + n + '"]');
    var box = main.querySelector(".tt-code");
    if (b && box) box.scrollTop = Math.max(0, b.closest("tr").offsetTop - 40);
  }

  function selectStop(id, focus) {
    t.stop = id;
    t.district = null;
    t.mode = "stop";
    renderTour();
    if (focus) refocus('[data-pin="' + id + '"].tt-pin');
  }

  function saveOrder(ids, message, focusId) {
    return H.api("PATCH", base(), { order: ids }).then(function (d) {
      applied(d, message);
      if (focusId) refocus('[data-pin="' + focusId + '"].tt-pin');
    }).catch(H.failed);
  }

  function move(id, by) {
    var ids = t.tour.stops.map(function (s) { return s.id; }), i = ids.indexOf(id), j = i + by;
    if (i < 0 || j < 0 || j >= ids.length) return;
    ids.splice(i, 1);
    ids.splice(j, 0, id);
    t.stop = id;
    saveOrder(ids, "Moved to stop " + (j + 1) + ".", id);
  }

  function pickLine(n, extend) {
    if (!t.anchor || extend === false) {
      t.anchor = n;
      t.sel = [n, n];
    } else {
      t.sel = [Math.min(t.anchor, n), Math.max(t.anchor, n)];
      t.anchor = null;
    }
    syncSelection();
  }

  function syncSelection() {
    var sel = t.sel || [0, 0];
    main.querySelectorAll(".tt-code tr").forEach(function (tr) {
      var b = tr.querySelector("[data-line]"), n = Number(b.getAttribute("data-line")), on = n >= sel[0] && n <= sel[1];
      tr.classList.toggle("sel", on);
      b.setAttribute("aria-pressed", on ? "true" : "false");
    });
    ["tt-from", "tt-mfrom"].forEach(function (id) { var e = document.getElementById(id); if (e) e.value = sel[0] || ""; });
    ["tt-to", "tt-mto"].forEach(function (id) { var e = document.getElementById(id); if (e) e.value = sel[1] || ""; });
    var info = document.getElementById("tt-selinfo");
    if (info) info.textContent = selInfo();
  }

  function num(id) { var e = document.getElementById(id); return e ? Number(e.value) : 0; }

  main.addEventListener("click", function (e) {
    if (!mine()) return;
    var open = e.target.closest("[data-tour]");
    if (open) return openTour(open.getAttribute("data-tour"));
    var line = e.target.closest("[data-line]");
    if (line) return pickLine(Number(line.getAttribute("data-line")), !e.shiftKey ? undefined : true);
    var dist = e.target.closest("[data-district]");
    if (dist) return openDistrict(dist.getAttribute("data-district"));
    var file = e.target.closest("[data-file]");
    if (file) { t.replace = null; return openFile(file.getAttribute("data-file")); }
    var pin = e.target.closest("[data-pin]");
    if (pin) return selectStop(pin.getAttribute("data-pin"), true);
    var act = e.target.closest("[data-tt]");
    if (!act) return;
    var name = act.getAttribute("data-tt"), s = t.tour && t.tour.stops[stopIndex(t.stop)];
    if (name === "list") return showList(true);
    if (name === "load") return loadFiles();
    if (name === "plot" || name === "start") {
      t.mode = "start";
      t.district = null;
      t.replace = null;
      drawMap();
      renderDrawer();
      main.querySelectorAll(".tt-pin.cur").forEach(function (b) { b.classList.remove("cur"); b.removeAttribute("aria-current"); });
      return refocus("#tt-drawer button");
    }
    if (name === "files") { t.mode = "files"; renderDrawer(); return refocus("#tt-filter"); }
    if (name === "replot" && s) {
      t.replace = s.id;
      var go = function () { return openFile(s.path, [s.start, s.end]); };
      return t.files ? go() : loadFiles().then(go);
    }
    if (name === "keep" && s) {
      return H.api("POST", base() + "/stops/" + s.id + "/keep").then(function (d) { applied(d, "Kept as is. The stop won't be flagged again unless the lines change again."); }).catch(H.failed);
    }
    if (name === "notsecret" && s) {
      if (!window.confirm("Mark stop " + (stopIndex(s.id) + 1) + " as not a secret? This is logged, and the lines can then be published.")) return;
      return H.api("POST", base() + "/stops/" + s.id + "/not-a-secret").then(function (d) { applied(d, "Marked as not a secret."); }).catch(H.failed);
    }
    if (name === "earlier" && s) return move(s.id, -1);
    if (name === "later" && s) return move(s.id, 1);
    if (name === "remove" && s) {
      if (!window.confirm("Remove stop " + (stopIndex(s.id) + 1) + ", " + (s.title || "untitled") + "?")) return;
      return H.api("DELETE", base() + "/stops/" + s.id).then(function (d) {
        t.stop = d.stops.length ? d.stops[Math.min(stopIndex(s.id) === -1 ? 0 : stopIndex(s.id), d.stops.length - 1)].id : null;
        t.mode = d.stops.length ? "stop" : "start";
        applied(d, "Stop removed.");
      }).catch(H.failed);
    }
    if (name === "publish") {
      var d = t.tour;
      var msg = d.repo.private
        ? "Publish this map? Visitors will see the stop titles, explanations and excerpts, with your district names. No file names, paths or links."
        : "Publish this map at /map/" + d.slug + "? Visitors will see every stop, with links to these lines on GitHub.";
      if (!window.confirm(msg)) return;
      act.disabled = true;
      return H.api("POST", base() + "/publish").then(function (r) { applied(r, "Published at /map/" + r.published_slug + "."); }).catch(function (err) { act.disabled = false; H.failed(err); });
    }
    if (name === "unpublish") {
      if (!window.confirm("Take this map off the public site? The stops stay here.")) return;
      return H.api("POST", base() + "/unpublish").then(function (r) { applied(r, "The map is off the public site."); }).catch(H.failed);
    }
  });

  main.addEventListener("keydown", function (e) {
    if (!mine()) return;
    var g = e.target.closest && e.target.closest("[data-district], .tt-load");
    if (g && g.tagName.toLowerCase() === "g" && (e.key === "Enter" || e.key === " ")) {
      e.preventDefault();
      if (g.hasAttribute("data-district")) openDistrict(g.getAttribute("data-district"));
      else loadFiles();
      return;
    }
    // Shift with an arrow moves the focused stop along the route.
    var pin = e.target.closest && e.target.closest(".tt-pin[data-pin]");
    if (pin && e.shiftKey && (e.key === "ArrowLeft" || e.key === "ArrowRight")) {
      e.preventDefault();
      move(pin.getAttribute("data-pin"), e.key === "ArrowLeft" ? -1 : 1);
    }
  });

  main.addEventListener("input", function (e) {
    if (!mine()) return;
    if (e.target.id === "tt-filter") {
      t.filter = e.target.value;
      var list = main.querySelector(".tt-files"), rows = districtFiles().slice(0, 300);
      if (list) list.innerHTML = rows.map(function (row) { return '<li><button type="button" class="tt-row" data-file="' + esc(row[0]) + '">' + esc(row[0]) + "</button></li>"; }).join("");
    }
    if ((e.target.id === "tt-from" || e.target.id === "tt-to") && t.mode === "code") {
      var a = num("tt-from"), b = num("tt-to") || a;
      if (a > 0) {
        t.sel = [Math.min(a, b), Math.max(a, b)];
        var mf = document.getElementById("tt-mfrom"), mt = document.getElementById("tt-mto");
        main.querySelectorAll(".tt-code tr").forEach(function (tr) {
          var n = Number(tr.querySelector("[data-line]").getAttribute("data-line")), on = n >= t.sel[0] && n <= t.sel[1];
          tr.classList.toggle("sel", on);
        });
        if (mf) mf.value = t.sel[0];
        if (mt) mt.value = t.sel[1];
        document.getElementById("tt-selinfo").textContent = selInfo();
      }
    }
  });

  main.addEventListener("dragstart", function (e) {
    if (!mine()) return;
    var pin = e.target.closest && e.target.closest(".tt-pin[data-pin]");
    if (!pin) return;
    t.dragging = pin.getAttribute("data-pin");
    e.dataTransfer.effectAllowed = "move";
    e.dataTransfer.setData("text/plain", t.dragging);
  });
  main.addEventListener("dragover", function (e) {
    if (mine() && t.dragging && e.target.closest && e.target.closest(".tt-pin[data-pin]")) e.preventDefault();
  });
  main.addEventListener("drop", function (e) {
    if (!mine() || !t.dragging) return;
    var target = e.target.closest && e.target.closest(".tt-pin[data-pin]");
    var from = t.dragging;
    t.dragging = null;
    if (!target) return;
    e.preventDefault();
    var to = target.getAttribute("data-pin");
    if (to === from) return;
    var ids = t.tour.stops.map(function (s) { return s.id; });
    ids.splice(ids.indexOf(from), 1);
    ids.splice(ids.indexOf(to) + (stopIndex(from) < stopIndex(to) ? 1 : 0), 0, from);
    saveOrder(ids, "Moved to stop " + (ids.indexOf(from) + 1) + ".", from);
  });
  main.addEventListener("dragend", function () { t.dragging = null; });

  main.addEventListener("submit", function (e) {
    if (!mine()) return;
    e.preventDefault();
    var id = e.target.id;
    if (id === "tt-settings") {
      var body = { title: document.getElementById("tt-title").value, slug: document.getElementById("tt-slug").value.trim().toLowerCase() };
      var labels = {};
      main.querySelectorAll("[data-label]").forEach(function (i) { labels[i.getAttribute("data-label")] = i.value; });
      if (Object.keys(labels).length) body.labels = labels;
      H.say("Saving...");
      return H.api("PATCH", base(), body).then(function (d) { applied(d, d.published_slug ? "Saved. Publish the map again to update the public page." : "Saved."); }).catch(H.failed);
    }
    if (id === "tt-plot") {
      var a = num("tt-from"), b = num("tt-to");
      if (!a || !b) return H.say("Choose the first and last line.");
      if (Math.abs(b - a) + 1 > MAX_LINES) return H.say("A stop can show up to " + MAX_LINES + " lines.");
      var payload = { path: t.file.path, start: a, end: b, mark: [num("tt-mfrom") || a, num("tt-mto") || b],
        title: document.getElementById("tt-stitle").value, explanation: document.getElementById("tt-sexp").value };
      if (t.replace) payload.replace = t.replace;
      H.say("Copying the lines and checking them for secrets...");
      return H.api("POST", base() + "/stops", payload).then(function (d) {
        t.stop = d.plotted;
        t.mode = "stop";
        t.replace = null;
        t.district = null;
        t.tour = d;
        var s = d.stops.filter(function (x) { return x.id === d.plotted; })[0];
        applied(d, s && s.scan.status === "flagged" ? "Plotted, but it might hold a secret. Check it before publishing." : "Plotted as stop " + (stopIndex(d.plotted) + 1) + ".");
        refocus('[data-pin="' + d.plotted + '"].tt-pin');
      }).catch(H.failed);
    }
    if (id === "tt-stop") {
      var cur = t.tour.stops[stopIndex(t.stop)];
      H.say("Saving...");
      return H.api("PATCH", base(), { stop: { id: cur.id, title: document.getElementById("tt-stitle").value, explanation: document.getElementById("tt-sexp").value,
        mark: [num("tt-mfrom"), num("tt-mto")] } }).then(function (d) { applied(d, "Stop saved."); refocus('[data-pin="' + cur.id + '"].tt-pin'); }).catch(H.failed);
    }
  });

  window.TownTours = {
    init: function (helpers) { H = helpers; },
    show: function () { return showList(true); },
  };
})();
