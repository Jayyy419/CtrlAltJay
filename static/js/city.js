(function () {
  "use strict";

  var NS = "http://www.w3.org/2000/svg";
  var MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  var WEEK = 7 * 24 * 3600;
  var reduce = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  var svg = document.getElementById("city-svg");
  var card = document.getElementById("city-card");
  var range = document.getElementById("city-range");
  var whenEl = document.getElementById("city-when");
  var playBtn = document.getElementById("city-play");
  var tableBody = document.getElementById("city-table-body");
  var picker = document.getElementById("city-picker");
  var skyNote = document.getElementById("city-sky");
  var state = { city: null, t: 0, weeks: [], selected: 0, playing: null, vb: null };

  function esc(v) {
    return String(v == null ? "" : v).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
  }

  function el(name, attrs, parent) {
    var e = document.createElementNS(NS, name);
    for (var k in attrs) e.setAttribute(k, attrs[k]);
    (parent || svg).appendChild(e);
    return e;
  }

  // Singapore time, read from the clock without trusting the device's zone.
  function sgNow() {
    var d = new Date(Date.now() + 8 * 3600 * 1000);
    return isNaN(d) ? null : { h: d.getUTCHours(), m: d.getUTCMinutes() };
  }

  function sgDate(ts) {
    var d = new Date(ts * 1000 + 8 * 3600 * 1000);
    return d.getUTCDate() + " " + MONTHS[d.getUTCMonth()] + " " + d.getUTCFullYear();
  }

  function monthLabel(ts) {
    var d = new Date(ts * 1000 + 8 * 3600 * 1000);
    return MONTHS[d.getUTCMonth()] + " " + d.getUTCFullYear();
  }

  // Night by default is the city's look; the palette shifts with the hour,
  // and a calm dusk is used if the time can't be read.
  function skyFor(now) {
    if (!now) return { name: "dusk", top: "#1b1e3d", mid: "#3a2f5c", low: "#8a4f6b", stars: 0.3 };
    var h = now.h;
    if (h >= 20 || h < 5) return { name: "night", top: "#05060d", mid: "#0b0e22", low: "#1a2350", stars: 1 };
    if (h < 7) return { name: "dawn", top: "#1c2550", mid: "#5a4a78", low: "#e39a7a", stars: 0.2 };
    if (h < 17) return { name: "day", top: "#24406e", mid: "#3c6aa3", low: "#8fb4d8", stars: 0 };
    return { name: "dusk", top: "#1b1e3d", mid: "#3a2f5c", low: "#b45f6e", stars: 0.3 };
  }

  function rng(seed) {
    var x = seed % 233280 || 7;
    return function () { x = (x * 9301 + 49297) % 233280; return x / 233280; };
  }

  function statsAt(b, t) {
    var commits = 0, active = 0;
    for (var i = 0; i < b.weeks.length; i++) {
      if (b.weeks[i][0] > t) break;
      commits += b.weeks[i][1];
      active += 1;
    }
    var span = b.first_week && t >= b.first_week ? Math.floor((t - b.first_week) / WEEK) + 1 : 0;
    return { commits: commits, active: active, span: Math.max(span, active) };
  }

  function iso(x, y, z, o) { return [o.cx + (x - y) * 0.866, o.cy + (x + y) * 0.5 - z]; }

  function poly(points, attrs, parent) {
    attrs.points = points.map(function (p) { return p[0].toFixed(1) + "," + p[1].toFixed(1); }).join(" ");
    return el("polygon", attrs, parent);
  }

  function draw() {
    var city = state.city;
    var buildings = city.buildings;
    while (svg.firstChild) svg.removeChild(svg.firstChild);
    var sky = skyFor(sgNow());
    skyNote.textContent = (sky.name === "day" ? "Daytime" : sky.name.charAt(0).toUpperCase() + sky.name.slice(1)) + " sky, Singapore time";

    var widths = buildings.map(function (b) { return Math.max(30, Math.min(110, 26 + Math.sqrt(b.bytes || 0) / 12)); });
    var gap = 34, total = widths.reduce(function (a, w) { return a + w + gap; }, 0) - gap;
    var maxCommits = Math.max.apply(null, buildings.map(function (b) { return b.commits || 1; }).concat([1]));
    var maxH = 300;
    var o = { cx: 0, cy: 0 };

    var defs = el("defs", {});
    var g = el("linearGradient", { id: "city-sky-grad", x1: 0, y1: 0, x2: 0, y2: 1 }, defs);
    [["0", sky.top], ["0.6", sky.mid], ["1", sky.low]].forEach(function (s) { el("stop", { offset: s[0], "stop-color": s[1] }, g); });
    var glow = el("filter", { id: "city-glow", x: "-50%", y: "-50%", width: "200%", height: "200%" }, defs);
    el("feGaussianBlur", { stdDeviation: 2.2, result: "b" }, glow);
    var merge = el("feMerge", {}, glow);
    el("feMergeNode", { in: "b" }, merge);
    el("feMergeNode", { in: "SourceGraphic" }, merge);
    var bg = el("g", {});
    var scene = el("g", {});

    var x0 = 0, depth = 42;
    poly([iso(-40, -30, 0, o), iso(total + 40, -30, 0, o), iso(total + 40, depth + 60, 0, o), iso(-40, depth + 60, 0, o)], { fill: "#10142c", stroke: "#232a55" }, scene);
    var now = Date.now() / 1000;

    buildings.forEach(function (b, idx) {
      var w = widths[idx], s = statsAt(b, state.t);
      var x = x0;
      x0 += w + gap;
      if (!s.commits && (!b.first_week || b.first_week > state.t)) return;
      var h = 14 + (s.commits / maxCommits) * maxH;
      var grp = el("g", {
        class: "bldg" + (idx === state.selected ? " is-selected" : ""), tabindex: idx === state.selected ? "0" : "-1",
        role: "button", "data-i": idx,
        "aria-label": b.name + ": " + s.commits + " floors, lights on " + s.active + " weeks" + (b.archived ? ", boarded up" : "") + (b.under_construction ? ", under construction" : ""),
      }, scene);
      var y = 0;
      poly([iso(x, y + depth, 0, o), iso(x + w, y + depth, 0, o), iso(x + w, y + depth, h, o), iso(x, y + depth, h, o)], { fill: "#161b3d", stroke: idx === state.selected ? "#7fb6ff" : "#232a55", "stroke-width": idx === state.selected ? 2 : 1 }, grp);
      poly([iso(x + w, y, 0, o), iso(x + w, y + depth, 0, o), iso(x + w, y + depth, h, o), iso(x + w, y, h, o)], { fill: "#0f1330", stroke: "#232a55" }, grp);
      poly([iso(x, y, h, o), iso(x + w, y, h, o), iso(x + w, y + depth, h, o), iso(x, y + depth, h, o)], { fill: "#252d63" }, grp);
      var rows = Math.floor(h / 13), cols = Math.max(2, Math.floor((w - 4) / 11));
      var lit = s.span ? s.active / s.span : 0, wr = rng(b.seed || idx * 31 + 7);
      for (var ry = 1; ry < rows; ry++) {
        for (var c = 0; c < cols; c++) {
          var on = wr() < lit;
          var a = iso(x + 4 + c * 11, y + depth, ry * 13, o), bb = iso(x + 10 + c * 11, y + depth, ry * 13, o),
              cc = iso(x + 10 + c * 11, y + depth, ry * 13 - 7, o), d = iso(x + 4 + c * 11, y + depth, ry * 13 - 7, o);
          if (b.archived) {
            poly([a, bb, cc, d], { fill: "#3b2a1c" }, grp);
            el("line", { x1: a[0], y1: a[1], x2: cc[0], y2: cc[1], stroke: "#7a5638", "stroke-width": 0.8 }, grp);
          } else {
            poly([a, bb, cc, d], on ? { fill: b.color, filter: "url(#city-glow)" } : { fill: "#1c2148" }, grp);
          }
        }
      }
      if (b.under_construction && state.t >= now - 8 * 24 * 3600) {
        var top = iso(x + w / 2, y + depth / 2, h, o);
        var crane = el("g", { class: "crane" + (reduce ? "" : " swing"), style: "transform-origin:" + top[0].toFixed(1) + "px " + (top[1] - 70).toFixed(1) + "px" }, grp);
        el("line", { x1: top[0], y1: top[1], x2: top[0], y2: top[1] - 72, stroke: "#ffcf5a", "stroke-width": 3 }, grp);
        el("line", { x1: top[0] - 30, y1: top[1] - 66, x2: top[0] + 70, y2: top[1] - 82, stroke: "#ffcf5a", "stroke-width": 3 }, crane);
        el("line", { x1: top[0] + 60, y1: top[1] - 80, x2: top[0] + 60, y2: top[1] - 52, stroke: "#ffcf5a" }, crane);
        el("circle", { cx: top[0], cy: top[1] - 74, r: 3, fill: "#ff5a5a", filter: "url(#city-glow)", class: reduce ? "" : "blink" }, grp);
        for (var sy = 12; sy < h; sy += 22) {
          var p1 = iso(x - 4, y + depth + 4, sy, o), p2 = iso(x + w + 4, y + depth + 4, sy, o);
          el("line", { x1: p1[0], y1: p1[1], x2: p2[0], y2: p2[1], stroke: "#c9a227", "stroke-width": 1, opacity: 0.8 }, grp);
        }
      }
      var lab = iso(x + w / 2, y + depth + 30, 0, o);
      var t = el("text", { x: lab[0].toFixed(1), y: lab[1].toFixed(1), "text-anchor": "middle", class: "bldg-label" }, grp);
      t.textContent = b.name;
    });

    // The frame is measured once, with the whole city standing, so scrubbing
    // back never makes the picture jump or crop.
    if (!state.vb) {
      var box = scene.getBBox();
      var wide = window.matchMedia("(min-width: 761px)").matches;
      var padX = 40, top = box.y - 120, bottom = box.y + box.height + 30;
      var left = box.x - padX, right = box.x + box.width + padX + (wide ? box.width * 0.42 : 0);
      state.vb = [left, top, right - left, bottom - top];
    }
    var vb = state.vb;
    svg.setAttribute("viewBox", vb.map(function (n) { return n.toFixed(1); }).join(" "));
    el("rect", { x: vb[0], y: vb[1], width: vb[2], height: vb[3], fill: "url(#city-sky-grad)" }, bg);
    var r = rng(42);
    for (var i = 0; i < Math.round(110 * sky.stars); i++) {
      el("circle", { cx: (vb[0] + r() * vb[2]).toFixed(1), cy: (vb[1] + r() * vb[3] * 0.45).toFixed(1), r: (r() * 1.3 + 0.3).toFixed(2), fill: "#fff", opacity: (r() * 0.7 + 0.2).toFixed(2) }, bg);
    }
  }

  function renderCard() {
    var b = state.city.buildings[state.selected];
    if (!b) { card.innerHTML = ""; return; }
    var s = statsAt(b, state.t);
    var langs = (b.languages || []).slice(0, 3).map(function (l) { return esc(l[0]) + " " + Math.round(l[1] * 100) + "%"; }).join(" · ");
    var links = "";
    if (b.project_url) links += '<a href="' + esc(b.project_url) + '">Project page</a>';
    if (b.tour_url) links += '<a href="' + esc(b.tour_url) + '">Take the tour</a>';
    card.innerHTML = '<div class="k">You picked</div><h2 id="city-card-title">' + esc(b.name) + "</h2>" +
      (b.description ? "<p>" + esc(b.description) + "</p>" : "") +
      '<div class="k">Built with</div><div class="v small">' + (langs || "Not known") + "</div>" +
      '<dl class="city-stats"><div><dt class="k">Floors</dt><dd class="v">' + s.commits + '</dd></div>' +
      '<div><dt class="k">Lights on</dt><dd class="v">' + s.active + " wk</dd></div>" +
      '<div><dt class="k">Last built</dt><dd class="v">' + esc(b.last_push ? sgDate(b.last_push) : "Not known") + "</dd></div></dl>" +
      ((b.archived || b.under_construction) ? '<p class="city-flag">' + (b.archived ? "Boarded up" : "Under construction") + "</p>" : "") +
      (links ? '<div class="city-links">' + links + "</div>" : "");
  }

  function renderTable() {
    tableBody.innerHTML = state.city.buildings.map(function (b) {
      var s = statsAt(b, state.t);
      return "<tr><th scope=\"row\">" + esc(b.name) + "</th><td>" + esc(b.main_language || "Not known") + "</td><td class=\"num\">" + s.commits +
        "</td><td class=\"num\">" + s.active + "</td><td>" + esc(b.last_push ? sgDate(b.last_push) : "") + "</td><td>" +
        (b.archived ? "Boarded up" : b.under_construction ? "Under construction" : "") + "</td></tr>";
    }).join("");
  }

  function renderPicker() {
    picker.innerHTML = state.city.buildings.map(function (b, i) {
      return '<button type="button" data-pick="' + i + '"' + (i === state.selected ? ' aria-pressed="true"' : ' aria-pressed="false"') + ">" + esc(b.name) + "</button>";
    }).join("");
  }

  function setTime(idx) {
    state.t = state.weeks[idx];
    range.value = idx;
    whenEl.textContent = "City as of " + monthLabel(state.t);
    range.setAttribute("aria-valuetext", whenEl.textContent);
    draw();
    renderCard();
    renderTable();
  }

  function select(i, focus) {
    state.selected = i;
    draw();
    renderCard();
    renderPicker();
    if (focus) {
      var g = svg.querySelector('[data-i="' + i + '"]');
      if (g) g.focus();
    }
  }

  function stop() {
    if (state.playing) cancelAnimationFrame(state.playing);
    state.playing = null;
    playBtn.setAttribute("aria-label", "Play the city's history");
    playBtn.textContent = "▶";
  }

  function play() {
    if (state.playing) return stop();
    if (reduce) { setTime(state.weeks.length - 1); return; }
    var startIdx = Number(range.value) >= state.weeks.length - 1 ? 0 : Number(range.value);
    var duration = 6000, began = null;
    playBtn.setAttribute("aria-label", "Pause");
    playBtn.textContent = "❚❚";
    function frame(ts) {
      if (began === null) began = ts;
      var p = Math.min(1, (ts - began) / duration);
      var idx = Math.round(startIdx + (state.weeks.length - 1 - startIdx) * p);
      if (idx !== Number(range.value) || p === 1) setTime(idx);
      if (p < 1) state.playing = requestAnimationFrame(frame);
      else stop();
    }
    state.playing = requestAnimationFrame(frame);
  }

  function prepare(city) {
    var now = Math.floor(Date.now() / 1000);
    var first = Infinity;
    city.buildings.forEach(function (b, i) {
      b.weeks = (b.weeks || []).slice().sort(function (a, c) { return a[0] - c[0]; });
      b.first_week = b.first_week || (b.weeks[0] ? b.weeks[0][0] : 0);
      if (b.first_week) first = Math.min(first, b.first_week);
      b.seed = (b.name || "").split("").reduce(function (a, ch) { return a + ch.charCodeAt(0); }, i * 13 + 5);
      b.under_construction = !!b.last_push && now - b.last_push < 7 * 24 * 3600;
    });
    var end = now - (now % WEEK);
    var weeks = [];
    for (var t = isFinite(first) ? first : end; t <= end + WEEK; t += WEEK) weeks.push(t);
    if (!weeks.length) weeks.push(end);
    state.weeks = weeks;
    range.max = weeks.length - 1;
  }

  svg.addEventListener("click", function (e) {
    var g = e.target.closest("[data-i]");
    if (g) select(Number(g.getAttribute("data-i")), true);
  });
  svg.addEventListener("keydown", function (e) {
    var n = state.city.buildings.length;
    if (e.key === "ArrowRight" || e.key === "ArrowDown") { e.preventDefault(); select((state.selected + 1) % n, true); }
    else if (e.key === "ArrowLeft" || e.key === "ArrowUp") { e.preventDefault(); select((state.selected - 1 + n) % n, true); }
    else if (e.key === "Home") { e.preventDefault(); select(0, true); }
    else if (e.key === "End") { e.preventDefault(); select(n - 1, true); }
    else if (e.key === "Enter" || e.key === " ") { e.preventDefault(); card.focus(); }
  });
  picker.addEventListener("click", function (e) {
    var b = e.target.closest("[data-pick]");
    if (b) { select(Number(b.getAttribute("data-pick")), false); card.focus(); }
  });
  range.addEventListener("input", function () { stop(); setTime(Number(range.value)); });
  playBtn.addEventListener("click", play);
  var wideQuery = window.matchMedia("(min-width: 761px)");
  function refit() {
    if (!state.city || !state.weeks.length) return;
    var keep = state.t;
    state.vb = null;
    state.t = state.weeks[state.weeks.length - 1];
    draw();
    state.t = keep;
    draw();
  }
  if (wideQuery.addEventListener) wideQuery.addEventListener("change", refit);

  fetch("/api/city", { credentials: "same-origin" })
    .then(function (r) { return r.json(); })
    .then(function (city) {
      state.city = city;
      document.getElementById("city-sample").hidden = !city.sample;
      document.getElementById("city-sample-note").hidden = !city.sample;
      if (!city.buildings.length) {
        document.getElementById("city-stage").innerHTML = '<p class="city-empty">The lots are empty for now. Buildings go up once a project is approved for the skyline.</p>';
        return;
      }
      prepare(city);
      renderPicker();
      setTime(state.weeks.length - 1);
    })
    .catch(function () {
      document.getElementById("city-stage").innerHTML = '<p class="city-empty">The city didn\'t load. Try again in a moment.</p>';
    });
})();
