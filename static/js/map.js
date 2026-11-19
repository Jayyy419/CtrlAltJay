(function () {
  "use strict";

  var NS = "http://www.w3.org/2000/svg";
  var reduce = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  var svg = document.getElementById("map-svg");
  var stopEl = document.getElementById("map-stop");
  var listEl = document.getElementById("map-list");
  var slug = document.body.getAttribute("data-slug");
  var state = { tour: null, i: Math.max(0, Number(document.body.getAttribute("data-stop") || 1) - 1), pins: [], marker: null, anim: null };
  var COLORS = ["#3794ff", "#c586c0", "#4ec9b0", "#dcdcaa", "#ce9178", "#9cdcfe", "#d7ba7d", "#b5cea8"];

  var KEYWORDS = {
    python: "and as assert async await break class continue def del elif else except False finally for from global if import in is lambda None nonlocal not or pass raise return True try while with yield",
    javascript: "async await break case catch class const continue default delete do else export extends false finally for function if import in instanceof let new null return super switch this throw true try typeof undefined var void while yield of",
  };
  KEYWORDS.typescript = KEYWORDS.javascript + " interface type enum implements private public readonly as";
  var COMMENT = { python: "#", javascript: "//", typescript: "//" };

  function esc(v) {
    return String(v == null ? "" : v).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
  }

  // A small highlighter for the languages tours use most; anything else is
  // shown plain, still with strings and numbers picked out.
  function highlight(line, lang) {
    var words = (KEYWORDS[lang] || "").split(" ");
    var hash = COMMENT[lang] || (lang === "shell" ? "#" : "//");
    var out = "", re = /("(?:[^"\\]|\\.)*"|'(?:[^'\\]|\\.)*'|`(?:[^`\\]|\\.)*`)|(\b\d+(?:\.\d+)?\b)|([A-Za-z_$][\w$]*)|([\s\S])/g, m, rest;
    var cut = line.indexOf(hash);
    while (cut !== -1) {
      var before = line.slice(0, cut);
      var quotes = (before.match(/"/g) || []).length + (before.match(/'/g) || []).length;
      if (quotes % 2 === 0) break;
      cut = line.indexOf(hash, cut + 1);
    }
    var code = cut === -1 ? line : line.slice(0, cut);
    rest = cut === -1 ? "" : line.slice(cut);
    while ((m = re.exec(code))) {
      if (m[1]) out += '<span class="t-s">' + esc(m[1]) + "</span>";
      else if (m[2]) out += '<span class="t-n">' + esc(m[2]) + "</span>";
      else if (m[3]) out += words.indexOf(m[3]) !== -1 ? '<span class="t-k">' + esc(m[3]) + "</span>" : esc(m[3]);
      else out += esc(m[4]);
    }
    if (rest) out += '<span class="t-c">' + esc(rest) + "</span>";
    return out || " ";
  }

  function el(name, attrs, parent) {
    var e = document.createElementNS(NS, name);
    for (var k in attrs) e.setAttribute(k, attrs[k]);
    (parent || svg).appendChild(e);
    return e;
  }

  // Split the districts into rectangles whose areas follow their size.
  function treemap(items, x, y, w, h, out) {
    if (!items.length) return out;
    if (items.length === 1) { out.push({ d: items[0], x: x, y: y, w: w, h: h }); return out; }
    var total = items.reduce(function (a, d) { return a + Math.max(1, d.size); }, 0), acc = 0, cut = 0;
    for (var i = 0; i < items.length - 1; i++) {
      acc += Math.max(1, items[i].size);
      cut = i + 1;
      if (acc >= total / 2) break;
    }
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

  function drawMap() {
    var t = state.tour;
    while (svg.firstChild) svg.removeChild(svg.firstChild);
    var defs = el("defs", {});
    var f = el("filter", { id: "map-glow", x: "-50%", y: "-50%", width: "200%", height: "200%" }, defs);
    el("feGaussianBlur", { stdDeviation: 4, result: "b" }, f);
    var mg = el("feMerge", {}, f);
    el("feMergeNode", { in: "b" }, mg);
    el("feMergeNode", { in: "SourceGraphic" }, mg);
    var boxes = treemap(t.districts.slice().sort(function (a, b) { return b.size - a.size; }), 20, 20, 660, 480, []);
    var byName = {};
    boxes.forEach(function (b, i) {
      var c = COLORS[i % COLORS.length];
      b.color = c;
      byName[b.d.name] = b;
      el("rect", { x: b.x + 4, y: b.y + 4, width: Math.max(0, b.w - 8), height: Math.max(0, b.h - 8), rx: 6, fill: c, "fill-opacity": 0.08, stroke: c, "stroke-opacity": 0.55 });
      for (var gx = b.x + 18; gx < b.x + b.w - 16; gx += 18) {
        for (var gy = b.y + 40; gy < b.y + b.h - 14; gy += 18) el("rect", { x: gx, y: gy, width: 10, height: 10, fill: c, "fill-opacity": 0.07 });
      }
      var label = el("text", { x: b.x + 14, y: b.y + 26, class: "d-label", fill: c }, null);
      label.textContent = b.d.name + (t.private ? "" : "/");
    });
    var seen = {};
    state.pins = t.stops.map(function (s, i) {
      var b = byName[s.district] || boxes[0];
      var total = t.stops.filter(function (q) { return q.district === s.district; }).length;
      var k = seen[s.district] = (seen[s.district] || 0) + 1;
      var fx = 0.22 + 0.56 * (total === 1 ? 0.5 : (k - 1) / (total - 1));
      var fy = 0.55 + (k % 2 ? -0.12 : 0.12);
      return [b.x + b.w * fx, b.y + Math.max(40, b.h * fy)];
    });
    var d = "M" + state.pins.map(function (p) { return p[0].toFixed(1) + " " + p[1].toFixed(1); }).join(" L");
    el("path", { d: d, fill: "none", stroke: "#3794ff", "stroke-width": 4, "stroke-linejoin": "round", "stroke-linecap": "round", filter: "url(#map-glow)", opacity: 0.85 });
    el("path", { d: d, fill: "none", stroke: "#ffffff", "stroke-width": 1.2, "stroke-dasharray": "2 8", "stroke-linecap": "round" });
    state.pins.forEach(function (p, i) {
      var g = el("g", { class: "pin", "data-pin": i });
      el("circle", { cx: p[0], cy: p[1], r: 9, fill: "#0b0e22", stroke: "#7fb6ff", "stroke-width": 3 }, g);
      var n = el("text", { x: p[0], y: p[1] + 3.5, "text-anchor": "middle", class: "pin-n" }, g);
      n.textContent = i + 1;
    });
    state.marker = el("g", { class: "here" });
    el("circle", { cx: 0, cy: 0, r: 26, fill: "#3794ff", opacity: 0.25, filter: "url(#map-glow)", class: reduce ? "" : "pulse" }, state.marker);
    el("circle", { cx: 0, cy: 0, r: 13, fill: "#ffffff", stroke: "#3794ff", "stroke-width": 3, filter: "url(#map-glow)" }, state.marker);
    state.markerNum = el("text", { x: 0, y: 4, "text-anchor": "middle", class: "here-n" }, state.marker);
    var lab = el("text", { x: 0, y: -24, "text-anchor": "middle", class: "here-label" }, state.marker);
    lab.textContent = "You are here";
    placeMarker(state.pins[state.i]);
  }

  function placeMarker(p) {
    state.marker.setAttribute("transform", "translate(" + p[0].toFixed(1) + " " + p[1].toFixed(1) + ")");
    state.markerNum.textContent = state.i + 1;
  }

  function moveMarker(from, to) {
    if (state.anim) cancelAnimationFrame(state.anim);
    if (reduce || !from) { placeMarker(state.pins[to]); return; }
    var a = state.pins[from], b = state.pins[to], start = null, dur = 600;
    state.markerNum.textContent = to + 1;
    function frame(ts) {
      if (start === null) start = ts;
      var p = Math.min(1, (ts - start) / dur), e = p < 0.5 ? 2 * p * p : 1 - Math.pow(-2 * p + 2, 2) / 2;
      state.marker.setAttribute("transform", "translate(" + (a[0] + (b[0] - a[0]) * e).toFixed(1) + " " + (a[1] + (b[1] - a[1]) * e).toFixed(1) + ")");
      if (p < 1) state.anim = requestAnimationFrame(frame);
    }
    state.anim = requestAnimationFrame(frame);
  }

  function renderStop() {
    var t = state.tour, s = t.stops[state.i], ex = s.excerpt || { start: 1, lines: [], mark: [0, 0] };
    var rows = ex.lines.map(function (line, k) {
      var n = ex.start + k, marked = n >= ex.mark[0] && n <= ex.mark[1];
      return "<tr" + (marked ? ' class="mark"' : "") + '><td class="ln">' + n + (marked ? '<span class="sr"> (marked)</span>' : "") +
        "</td><td>" + highlight(line, s.lang) + "</td></tr>";
    }).join("");
    var last = state.i === t.stops.length - 1;
    var html = '<p class="stop-n">Stop ' + (state.i + 1) + " of " + t.stops.length + " · " + esc(s.district) + (t.private ? "" : "/") + "</p>" +
      '<h2 id="stop-title">' + esc(s.title) + "</h2><p class=\"stop-ex\">" + esc(s.explanation) + "</p>" +
      '<div class="code" role="region" tabindex="0" aria-label="Code for this stop, lines ' + ex.start + " to " + (ex.start + ex.lines.length - 1) + '"><table>' + rows + "</table></div>";
    if (s.permalink) html += '<a class="perma" href="' + esc(s.permalink) + '" rel="noopener">See these lines on GitHub</a>';
    html += '<div class="stop-nav"><button type="button" class="btn" data-go="-1"' + (state.i === 0 ? " disabled" : "") + ">Back a stop</button>" +
      (last ? "" : '<button type="button" class="btn primary" data-go="1">Next stop</button>') + "</div>";
    if (last) {
      html += '<div class="tour-end"><p>That\'s the end of the tour.</p>' +
        (t.project_url ? '<a href="' + esc(t.project_url) + '">Back to the project page</a>' : "") +
        '<a href="/city' + (t.building_slug ? "#" + esc(t.building_slug) : "") + '">See it in Commit City</a></div>';
    }
    stopEl.innerHTML = html;
    listEl.innerHTML = t.stops.map(function (q, k) {
      return '<li><a href="/map/' + esc(slug) + "/" + (k + 1) + '"' + (k === state.i ? ' aria-current="step"' : "") + ">" + esc(q.title) + "</a></li>";
    }).join("");
    document.title = s.title + " · " + t.title;
  }

  function go(to, push, focus) {
    var t = state.tour;
    if (to < 0 || to >= t.stops.length || to === state.i) return;
    var from = state.i;
    state.i = to;
    moveMarker(from, to);
    renderStop();
    if (push) history.pushState({ stop: to }, "", "/map/" + slug + "/" + (to + 1));
    if (focus) {
      var h = document.getElementById("stop-title");
      if (h) { h.setAttribute("tabindex", "-1"); h.focus({ preventScroll: true }); }
    }
  }

  stopEl.addEventListener("click", function (e) {
    var b = e.target.closest("[data-go]");
    if (b) {
      go(state.i + Number(b.getAttribute("data-go")), true, false);
      var again = stopEl.querySelector('[data-go="' + b.getAttribute("data-go") + '"]') || stopEl.querySelector("[data-go]");
      if (again && !again.disabled) again.focus();
    }
  });
  listEl.addEventListener("click", function (e) {
    var a = e.target.closest("a");
    if (!a) return;
    e.preventDefault();
    var n = Number(a.getAttribute("href").split("/").pop()) - 1;
    go(n, true, true);
  });
  document.addEventListener("keydown", function (e) {
    if (e.altKey || e.ctrlKey || e.metaKey) return;
    var tag = (e.target.tagName || "").toLowerCase();
    if (tag === "input" || tag === "textarea" || tag === "select" || e.target.isContentEditable) return;
    // Inside the code box, arrows scroll the code instead.
    if (e.target.closest && e.target.closest(".code")) return;
    if (e.key === "ArrowRight") { e.preventDefault(); go(state.i + 1, true, true); }
    else if (e.key === "ArrowLeft") { e.preventDefault(); go(state.i - 1, true, true); }
  });
  window.addEventListener("popstate", function () {
    var n = Number(location.pathname.split("/").pop());
    if (n >= 1) go(n - 1, false, true);
  });

  fetch("/api/map/" + encodeURIComponent(slug), { credentials: "same-origin" })
    .then(function (r) { return r.json(); })
    .then(function (tour) {
      state.tour = tour;
      state.i = Math.min(state.i, tour.stops.length - 1);
      drawMap();
      renderStop();
      history.replaceState({ stop: state.i }, "", "/map/" + slug + "/" + (state.i + 1));
    })
    .catch(function () { stopEl.innerHTML = '<p>The map didn\'t load. Try again in a moment.</p>'; });
})();
