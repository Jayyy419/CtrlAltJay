(function () {
  "use strict";

  var main = document.getElementById("cb-main");
  var listEl = document.getElementById("cb-list");
  var statusEl = document.getElementById("cb-status");
  var state = {
    cases: [], options: null, view: null, data: null, tab: "questions", q: 0,
    stories: [], story: null, pool: null, addingQuestion: false,
  };

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
    own: "Added by you",
  };
  var LOOSE_KINDS = {
    question: "Unprepared question", skill: "Nothing shows it", story: "Story to finish", revise: "To revise",
  };
  var TYPE_LABEL = { item: "Portfolio", certification: "Certification", resume: "Resume", story: "Story" };
  var STAR = [["situation", "Situation"], ["task", "Task"], ["action", "Action"], ["result", "Result"]];
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

  function failed(err) {
    if (err && err.status === 404) return signedOut();
    say(err && err.message && err.message !== "Request failed" ? err.message : "That didn't save. Try again.");
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

  function plural(n, word) {
    return n + " " + word + (n === 1 ? "" : "s");
  }

  /* ---------- sidebar ---------- */

  function fileButton(view, label) {
    var on = state.view === view || (view === "stories" && state.view && state.view.indexOf("stories") === 0);
    return '<button type="button" class="cb-file" data-open="' + esc(view) + '"' + (on ? ' aria-current="true"' : "") + ">" + esc(label) + "</button>";
  }

  function renderList() {
    var html = '<div class="cb-list-label">Your cases</div>';
    if (!state.cases.length) {
      html += '<div class="cb-list-label cb-list-note">Nothing open yet.</div>';
    }
    state.cases.forEach(function (c) { html += fileButton("case/" + c.id, caseTitle(c)); });
    html += '<div class="cb-list-label">Your material</div>' + fileButton("stories", "Story bank");
    html += '<div class="cb-list-label">Try it out</div>' + fileButton("sample", "Sample: Accenture");
    listEl.innerHTML = html;
  }

  /* ---------- casebook view ---------- */

  function normalise(raw, sample) {
    return {
      sample: !!sample,
      casebook: raw.casebook,
      competencies: raw.competencies || [],
      questions: raw.questions || [],
      evidence: raw.evidence || [],
      matched: raw.matched_total || (raw.evidence || []).length,
      hidden: raw.hidden || [],
      stories: raw.stories || [],
      loose: raw.loose_ends || [],
      theirs: raw.questions_for_them || [],
    };
  }

  function costLine(c) {
    var cost = Number(c.cost_usd || 0).toFixed(2);
    if (c.research_status !== "done") return "<strong>US$" + cost + "</strong> · not researched yet";
    return "<strong>US$" + cost + "</strong> · " + plural(c.searches || 0, "search").replace("searchs", "searches");
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
      html += '<p class="sample-note">Research isn\'t switched on yet. For now the case works from your own material: add the usual questions, and your evidence is matched against what they look for.</p>';
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

  function kindLabel(kind) {
    var kinds = state.options && state.options.kinds;
    return (kinds && kinds[kind]) || kind;
  }

  function addQuestionControls(d) {
    if (d.sample) return "";
    var occasion = state.options.occasions[d.casebook.occasion] || "this occasion";
    var html = '<div class="toolbar"><button type="button" class="btn" data-act="add-usual">Add the usual questions</button>' +
      '<button type="button" class="btn" data-act="add-own" aria-expanded="' + state.addingQuestion + '">Add a question</button></div>';
    if (state.addingQuestion) {
      var kinds = state.options.kinds;
      html += '<form class="qform" id="q-form"><label for="q-text" class="sr">Question</label>' +
        '<input type="text" id="q-text" maxlength="300" placeholder="What do you think they\'ll ask?" autocomplete="off">' +
        '<label for="q-kind" class="sr">Kind</label><select id="q-kind">' +
        Object.keys(kinds).map(function (k) { return '<option value="' + k + '">' + esc(kinds[k]) + "</option>"; }).join("") +
        '</select><button type="submit" class="btn primary">Add</button></form>';
    }
    html += '<p class="hint" style="margin:0 0 16px">The usual questions are common ones for this kind of occasion (' + esc(occasion.toLowerCase()) + "). They aren't claims about this organisation.</p>";
    return html;
  }

  function renderQuestions(d) {
    var html = addQuestionControls(d);
    if (!d.questions.length) {
      return html + '<div class="empty">No questions on the table yet. ' +
        (d.sample ? "" : "Start with the usual ones for this occasion, or add your own. ") +
        "Research adds what people report being asked and what the posting points to.</div>";
    }
    state.q = Math.min(state.q, d.questions.length - 1);
    var q = d.questions[state.q];
    html += '<div class="bench"><div class="qlist" aria-label="Questions">';
    d.questions.forEach(function (item, i) {
      html += '<button type="button" class="qitem" data-q="' + i + '"' + (i === state.q ? ' aria-current="true"' : "") + ">" +
        '<span class="kind">' + esc(kindLabel(item.kind)) + "</span>" +
        '<div class="qt">' + esc(item.text) + "</div>" +
        '<div class="qm">' + badge(item.provenance) +
        "<span>" + (item.evidence && item.evidence.length ? item.evidence.length + " linked" : '<span class="gap">nothing linked</span>') + "</span>" +
        "</div></button>";
    });
    html += '</div><div class="detail" id="q-detail" tabindex="-1">';
    html += '<span class="kind">' + esc(kindLabel(q.kind)) + "</span><h2>" + esc(q.text) + "</h2>";
    html += '<div class="src-line">' + badge(q.provenance) + sourceText(q) + "</div>";
    if (q.why) html += '<p class="why" style="margin-top:12px">' + esc(q.why) + "</p>";
    else html += '<div style="height:16px"></div>';

    html += '<h3 class="h3">Your evidence</h3>';
    if (q.evidence && q.evidence.length) {
      html += '<div class="evc">';
      q.evidence.forEach(function (ev) {
        html += '<div class="card"><span class="rank">' + (ev.role === "lead" ? "Lead with" : "Back-up") + "</span><b>" + esc(ev.title) + "</b>" +
          (ev.type ? '<span class="type">' + esc(TYPE_LABEL[ev.type] || ev.type) + "</span>" : "") + "</div>";
      });
      html += "</div>";
    } else {
      html += '<p class="gap" style="margin:0 0 20px">Nothing in your material answers this yet. It\'s on the loose ends.</p>';
    }
    if (!d.sample) html += evidenceChooser(d, q);

    if (q.star) {
      html += '<h3 class="h3">Outline</h3><dl class="star">';
      STAR.forEach(function (f) {
        var v = q.star[f[0]];
        var from = q.star.from && q.star.from[f[0]];
        html += "<div><dt>" + f[1] + "</dt><dd>" + (v ? esc(v) + (from && from !== "story" ? ' <span class="from">from ' + esc(from) + "</span>" : "") : '<span class="gap">[your ' + f[0] + " here]</span>") + "</dd></div>";
      });
      html += "</dl>";
      if (!d.sample && q.evidence.length && q.evidence[0].type !== "story") {
        html += '<p class="hint">Only what\'s stored is used. Turn it into a story to fill the gaps in your own words.</p>' +
          '<div class="actions"><button type="button" class="btn" data-act="to-story">Turn this into a story</button></div>';
      }
    }
    if (!d.sample) {
      html += '<div class="actions" style="margin-top:28px"><button type="button" class="btn danger" data-act="drop-q">Take this question off the table</button></div>';
    }
    return html + "</div></div>";
  }

  function evidenceChooser(d, q) {
    var lead = q.chosen && q.evidence[0] ? q.evidence[0].ref : "";
    var backup = q.chosen && q.evidence[1] ? q.evidence[1].ref : "";
    var opts = [{ ref: "", title: "Best match" }];
    var seen = {};
    d.evidence.concat(q.evidence).forEach(function (e) {
      if (!seen[e.ref] && e.type !== "story") { seen[e.ref] = 1; opts.push(e); }
    });
    function select(id, label, value) {
      return '<div><label for="' + id + '">' + label + '</label><select id="' + id + '" data-ev="' + id + '">' +
        opts.map(function (o) { return '<option value="' + esc(o.ref) + '"' + (o.ref === value ? " selected" : "") + ">" + esc(o.title) + "</option>"; }).join("") +
        "</select></div>";
    }
    var storySel = '<div><label for="ev-story">Use a story</label><select id="ev-story" data-ev="ev-story"><option value="">No story</option>' +
      d.stories.map(function (s) { return '<option value="' + esc(s.id) + '"' + (s.id === q.story_id ? " selected" : "") + ">" + esc(s.title) + "</option>"; }).join("") +
      "</select></div>";
    return '<details class="chooser"><summary>Change the evidence</summary><div class="chooser-grid">' +
      storySel + select("ev-lead", "Lead with", lead) + select("ev-backup", "Back-up", backup) + "</div></details>";
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

  function competencyEditor(d) {
    if (d.sample) return "";
    var html = '<div class="comp-ed"><h3 class="h3">What they look for</h3><div class="chips">';
    d.competencies.forEach(function (k, i) {
      html += '<span class="chip chip-x">' + esc(k) + '<button type="button" data-act="comp-del" data-i="' + i + '" aria-label="Remove ' + esc(k) + '">&times;</button></span>';
    });
    if (!d.competencies.length) html += '<span class="hint">Nothing yet. Add what this case looks for.</span>';
    html += '</div><form class="qform" id="comp-form"><label for="comp-new" class="sr">Something they look for</label>' +
      '<input type="text" id="comp-new" maxlength="40" placeholder="Add something they look for, like SQL or Teamwork" autocomplete="off">' +
      '<button type="submit" class="btn">Add</button></form></div>';
    return html;
  }

  function whyLine(ev) {
    var parts = Object.keys(ev.why || {}).slice(0, 1).map(function (k) { return k + ": " + ev.why[k]; });
    return parts.length ? '<span class="why-line">' + esc(parts.join(" · ")) + "</span>" : "";
  }

  function renderEvidence(d) {
    var html = competencyEditor(d);
    if (!d.evidence.length) {
      return html + '<div class="empty">No evidence lined up yet. ' +
        (d.competencies.length ? "Nothing in your material matches what they look for. Add a story, or change the list above." : "Add what they look for and your material gets matched to it here.") + "</div>";
    }
    var comps = d.competencies;
    html += '<h3 class="h3">The mix to review' + (d.matched > d.evidence.length ? ", top " + d.evidence.length + " of " + d.matched : "") + "</h3>";
    if (!d.sample) html += '<p class="hint" style="margin:-4px 0 12px">Each match shows what triggered it. Click a cell to correct it.</p>';
    html += '<div class="grid-wrap"><table class="cov"><caption class="sr">Which of your material covers each thing they look for</caption><thead><tr><th scope="col"><span class="sr">Item</span></th>';
    comps.forEach(function (k) { html += '<th scope="col">' + esc(k) + "</th>"; });
    if (!d.sample) html += '<th scope="col"><span class="sr">Leave out</span></th>';
    html += "</tr></thead><tbody>";
    d.evidence.forEach(function (ev, i) {
      html += '<tr><th scope="row"><span class="rk">' + String(i + 1).padStart(2, "0") + "</span>" + esc(ev.title) +
        (ev.type ? '<span class="type">' + esc(TYPE_LABEL[ev.type] || ev.type) + "</span>" : "") + whyLine(ev) + "</th>";
      comps.forEach(function (k) {
        var hit = (ev.covers || []).indexOf(k) !== -1;
        if (d.sample) {
          html += "<td>" + (hit ? '<span class="dot" role="img" aria-label="Covers ' + esc(k) + '"></span>' : '<span class="sr">No</span>') + "</td>";
          return;
        }
        var forced = (ev.overridden || []).indexOf(k) !== -1;
        html += '<td><button type="button" class="cell' + (forced ? " forced" : "") + '" data-cell="' + i + '" data-comp="' + esc(k) + '" aria-pressed="' + hit + '"' +
          ' aria-label="' + esc(ev.title) + " covers " + esc(k) + (forced ? ", set by you" : "") + '"' +
          (ev.why && ev.why[k] ? ' title="' + esc(ev.why[k]) + '"' : "") + ">" +
          (hit ? '<span class="dot"></span>' : "") + "</button></td>";
      });
      if (!d.sample) html += '<td><button type="button" class="leave" data-leave="' + esc(ev.ref) + '" aria-label="Leave out ' + esc(ev.title) + '">Leave out</button></td>';
      html += "</tr>";
    });
    html += '</tbody><tfoot><tr><th scope="row">Items covering it</th>';
    comps.forEach(function (k) {
      var n = d.evidence.filter(function (ev) { return (ev.covers || []).indexOf(k) !== -1; }).length;
      html += "<td" + (n ? "" : ' class="none"') + ">" + n + "</td>";
    });
    if (!d.sample) html += "<td></td>";
    html += "</tr></tfoot></table></div>";

    html += '<div class="cov-list">';
    d.evidence.forEach(function (ev) {
      html += '<div class="card" style="margin-bottom:8px"><b>' + esc(ev.title) + "</b>" +
        (ev.type ? '<span class="type">' + esc(TYPE_LABEL[ev.type] || ev.type) + "</span>" : "") +
        '<div class="chips">' + (ev.covers || []).map(function (k) { return '<span class="chip">' + esc(k) + "</span>"; }).join("") + "</div>" +
        whyLine(ev) +
        (d.sample ? "" : '<div class="actions" style="margin-top:8px"><button type="button" class="btn" data-leave="' + esc(ev.ref) + '">Leave out</button></div>') +
        "</div>";
    });
    var missing = comps.filter(function (k) {
      return !d.evidence.some(function (ev) { return (ev.covers || []).indexOf(k) !== -1; });
    });
    if (missing.length) html += '<p class="gap">Nothing covers: ' + esc(missing.join(", ")) + "</p>";
    html += "</div>";

    if (d.hidden.length) {
      html += '<h3 class="h3" style="margin-top:24px">Left out of this case</h3><div class="chips">';
      d.hidden.forEach(function (h) {
        html += '<span class="chip chip-x">' + esc(h.title) + '<button type="button" data-unleave="' + esc(h.ref) + '" aria-label="Bring back ' + esc(h.title) + '">&#8634;</button></span>';
      });
      html += "</div>";
    }
    return html;
  }

  function renderLoose(d) {
    if (!d.loose.length) return '<div class="empty">No loose ends. Either you\'re ready or there\'s nothing on the table yet.</div>';
    return d.loose.map(function (l) {
      return '<div class="loose"><span class="kind">' + esc(LOOSE_KINDS[l.kind] || l.kind) + "</span><div>" + esc(l.text) + "</div></div>";
    }).join("");
  }

  function renderTheirs(d) {
    if (!d.theirs.length) return '<div class="empty">No questions for them yet. These get drafted from what research finds about the team and the role.</div>';
    return '<ol class="qft">' + d.theirs.map(function (t) { return "<li>" + esc(t) + "</li>"; }).join("") + "</ol>";
  }

  function reloadCase(keepQuestionId) {
    var id = state.data.casebook.id;
    return api("GET", "/api/owner/casebooks/" + id).then(function (raw) {
      var data = normalise(raw, false);
      if (keepQuestionId) {
        var idx = data.questions.map(function (q) { return q.id; }).indexOf(keepQuestionId);
        if (idx !== -1) state.q = idx;
      }
      state.data = data;
      renderCase();
    });
  }

  function currentQuestion() {
    return state.data.questions[state.q];
  }

  /* ---------- story bank ---------- */

  function filled(st) {
    return STAR.filter(function (f) { return st[f[0]]; }).length;
  }

  function seg(st) {
    return '<span class="seg" aria-hidden="true">' + STAR.map(function (f) { return st[f[0]] ? '<i class="on"></i>' : "<i></i>"; }).join("") + "</span>";
  }

  function poolTitle(id) {
    var hit = (state.pool ? state.pool.items : []).filter(function (p) { return p.id === id; })[0];
    return hit ? hit.title : "An item that's been removed";
  }

  function renderStories() {
    main.innerHTML = storiesHtml();
  }

  function storiesHtml() {
    var list = state.stories;
    var st = state.story;
    var html = '<div class="cb-head"><div><h1 class="cb-title">Story bank</h1><div class="cb-meta">' +
      plural(list.length, "story").replace("storys", "stories") + " · reused across your cases</div></div>" +
      '<div class="cb-side-actions"><button type="button" class="btn primary" data-act="new-story">+ New story</button></div></div>';
    if (!list.length && !st) {
      return html + '<div class="empty">No stories yet. A story is something you\'d tell in an interview, in your own words, with the result you can stand behind. Start one here, or turn a question\'s outline into one.</div>';
    }
    html += '<div class="bench sb"><div class="qlist" aria-label="Stories">';
    list.forEach(function (s) {
      var n = (s.used_in || []).length;
      html += '<button type="button" class="qitem" data-story="' + esc(s.id) + '"' + (st && st.id === s.id ? ' aria-current="true"' : "") + ">" +
        '<div class="qt">' + esc(s.title) + '</div><div class="qm">' + seg(s) + "<span>" + filled(s) + "/4 filled</span><span>· " + plural(n, "case") + "</span></div></button>";
    });
    html += "</div><div>" + (st ? storyEditor(st) : '<div class="empty">Pick a story to edit it.</div>') + "</div></div>";
    return html;
  }

  function storyEditor(st) {
    var html = '<form class="sb-ed" id="story-form" novalidate>';
    html += '<div class="row"><label for="s-title">Title</label><input type="text" id="s-title" maxlength="160" value="' + esc(st.title || "") + '"></div>';
    STAR.forEach(function (f) {
      var v = st[f[0]] || "";
      html += '<div class="row"><label for="s-' + f[0] + '">' + f[1] + '</label><textarea id="s-' + f[0] + '" data-star="1" rows="3" maxlength="2000"' +
        (v ? "" : ' class="empty-f"') + ' placeholder="[your ' + f[0] + ' here]">' + esc(v) + "</textarea></div>";
    });
    html += '<div class="row"><span class="lbl">Draws on</span><div><div class="chips">';
    (st.item_ids || []).forEach(function (id) {
      html += '<span class="chip chip-x">' + esc(poolTitle(id)) + '<button type="button" data-unlink-item="' + esc(id) + '" aria-label="Unlink ' + esc(poolTitle(id)) + '">&times;</button></span>';
    });
    (st.skills || []).forEach(function (s) {
      html += '<span class="chip chip-x">' + esc(s) + '<button type="button" data-unlink-skill="' + esc(s) + '" aria-label="Unlink ' + esc(s) + '">&times;</button></span>';
    });
    if (!(st.item_ids || []).length && !(st.skills || []).length) html += '<span class="hint">Nothing linked yet.</span>';
    html += '</div><div class="qform link-row"><label for="s-link" class="sr">Link an item or skill</label>' +
      '<input type="text" id="s-link" list="s-link-options" placeholder="Link an item or skill" autocomplete="off">' +
      '<datalist id="s-link-options">' + linkOptions() + '</datalist><button type="button" class="btn" data-act="link">Link</button></div></div></div>';
    var used = st.used_in || [];
    html += '<div class="row"><span class="lbl">Used in</span><div class="used">' +
      (used.length ? used.map(function (u) { return '<button type="button" class="linkish" data-open="case/' + esc(u.id) + '">' + esc(u.title) + "</button>"; }).join("") : '<span class="cb-meta">No cases yet</span>') +
      "</div></div>";
    html += '<div class="actions"><button type="submit" class="btn primary">Save story</button>' +
      (st.id ? '<button type="button" class="btn danger" data-act="del-story">Delete</button>' : '<button type="button" class="btn" data-act="cancel-story">Cancel</button>') +
      '<span class="err" id="story-err" role="alert"></span></div></form>';
    return html;
  }

  function linkOptions() {
    if (!state.pool) return "";
    return state.pool.items.map(function (p) { return '<option value="' + esc(p.title) + '"></option>'; }).join("") +
      state.pool.skills.map(function (s) { return '<option value="' + esc(s) + '"></option>'; }).join("");
  }

  function storyFromForm() {
    var st = state.story;
    st.title = document.getElementById("s-title").value.trim();
    STAR.forEach(function (f) { st[f[0]] = document.getElementById("s-" + f[0]).value.trim(); });
    return st;
  }

  function saveStory() {
    var st = storyFromForm();
    var errEl = document.getElementById("story-err");
    if (!st.title) {
      errEl.textContent = "Give the story a title.";
      document.getElementById("s-title").focus();
      return;
    }
    var body = { title: st.title, item_ids: st.item_ids || [], skills: st.skills || [] };
    STAR.forEach(function (f) { body[f[0]] = st[f[0]]; });
    say("Saving...");
    var req = st.id ? api("PUT", "/api/owner/stories/" + st.id, body) : api("POST", "/api/owner/stories", body);
    req.then(function (saved) {
      say("Story saved.");
      return loadStories(saved.id);
    }).catch(failed);
  }

  function loadStories(selectId) {
    var poolReq = state.pool ? Promise.resolve(state.pool) : api("GET", "/api/owner/evidence/pool");
    return Promise.all([api("GET", "/api/owner/stories"), poolReq]).then(function (res) {
      state.stories = res[0];
      state.pool = res[1];
      var pick = selectId || (state.story && state.story.id) || (state.stories[0] && state.stories[0].id);
      state.story = state.stories.filter(function (s) { return s.id === pick; })[0] || state.stories[0] || null;
      if (state.story) state.story = JSON.parse(JSON.stringify(state.story));
      renderStories();
    });
  }

  function linkSelected() {
    var input = document.getElementById("s-link");
    var value = input.value.trim();
    if (!value) return;
    storyFromForm();
    var st = state.story;
    var item = state.pool.items.filter(function (p) { return p.title === value; })[0];
    if (item) {
      st.item_ids = (st.item_ids || []).filter(function (id) { return id !== item.id; }).concat([item.id]);
    } else if (state.pool.skills.indexOf(value) !== -1) {
      st.skills = (st.skills || []).filter(function (s) { return s !== value; }).concat([value]);
    } else {
      say("Pick an item or skill from the list.");
      return;
    }
    renderStories();
    document.getElementById("s-link").focus();
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
    state.addingQuestion = false;
    renderList();
    if (view === "new") {
      renderForm(null);
      focusMain();
      return;
    }
    if (view === "stories") {
      say("Opening...");
      loadStories().then(function () { say(""); focusMain(); }).catch(failed);
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

  function refocus(selector) {
    var el = main.querySelector(selector);
    if (el) el.focus();
  }

  /* ---------- case actions ---------- */

  function patchQuestion(body) {
    var q = currentQuestion();
    say("Saving...");
    return api("PATCH", "/api/owner/casebooks/" + state.data.casebook.id + "/questions/" + q.id, body)
      .then(function () { return reloadCase(q.id); })
      .then(function () { say("Saved."); })
      .catch(failed);
  }

  function setCompetencies(list, focusSel) {
    say("Saving...");
    api("PATCH", "/api/owner/casebooks/" + state.data.casebook.id, { competencies: list })
      .then(function () { return reloadCase(); })
      .then(function () { say("Saved."); refocus(focusSel); })
      .catch(failed);
  }

  function setCoverage(body, focusSel) {
    say("Saving...");
    api("PUT", "/api/owner/casebooks/" + state.data.casebook.id + "/coverage", body)
      .then(function () { return reloadCase(); })
      .then(function () { say("Saved."); if (focusSel) refocus(focusSel); })
      .catch(failed);
  }

  function questionToStory() {
    var q = currentQuestion();
    var lead = q.evidence[0];
    var body = { title: lead.title, item_ids: [], skills: [] };
    STAR.forEach(function (f) { body[f[0]] = q.star[f[0]] || ""; });
    var m = /^(item|resume):(.+)$/.exec(lead.ref);
    if (m) body.item_ids = [m[2]];
    say("Saving to your story bank...");
    api("POST", "/api/owner/stories", body).then(function (story) {
      return api("PATCH", "/api/owner/casebooks/" + state.data.casebook.id + "/questions/" + q.id, { story_id: story.id });
    }).then(function () {
      return reloadCase(q.id);
    }).then(function () {
      say("Saved to your story bank. Fill in the gaps there.");
    }).catch(failed);
  }

  /* ---------- events ---------- */

  document.getElementById("cb-new").addEventListener("click", function () { go("new"); });

  listEl.addEventListener("click", function (e) {
    var b = e.target.closest("[data-open]");
    if (b) go(b.getAttribute("data-open"));
  });

  main.addEventListener("click", function (e) {
    var t = e.target;
    var el;
    if ((el = t.closest("[data-open]"))) return go(el.getAttribute("data-open"));
    if ((el = t.closest("[data-tab]"))) {
      state.tab = el.getAttribute("data-tab");
      renderCase();
      return refocus("#tab-" + state.tab);
    }
    if ((el = t.closest("[data-q]"))) {
      state.q = parseInt(el.getAttribute("data-q"), 10);
      renderCase();
      if (window.matchMedia("(max-width: 760px)").matches) return refocus("#q-detail");
      return refocus('[data-q="' + state.q + '"]');
    }
    if ((el = t.closest("[data-cell]"))) {
      var ev = state.data.evidence[parseInt(el.getAttribute("data-cell"), 10)];
      var comp = el.getAttribute("data-comp");
      var forced = (ev.overridden || []).indexOf(comp) !== -1;
      var covers = forced ? null : el.getAttribute("aria-pressed") !== "true";
      return setCoverage({ ref: ev.ref, competency: comp, covers: covers },
        '[data-cell="' + el.getAttribute("data-cell") + '"][data-comp="' + comp.replace(/"/g, '\\"') + '"]');
    }
    if ((el = t.closest("[data-leave]"))) return setCoverage({ ref: el.getAttribute("data-leave"), hidden: true });
    if ((el = t.closest("[data-unleave]"))) return setCoverage({ ref: el.getAttribute("data-unleave"), hidden: false });
    if ((el = t.closest("[data-story]"))) {
      var id = el.getAttribute("data-story");
      state.story = JSON.parse(JSON.stringify(state.stories.filter(function (s) { return s.id === id; })[0]));
      renderStories();
      return refocus(window.matchMedia("(max-width: 760px)").matches ? "#s-title" : '[data-story="' + id + '"]');
    }
    if ((el = t.closest("[data-unlink-item]"))) {
      storyFromForm();
      var iid = el.getAttribute("data-unlink-item");
      state.story.item_ids = (state.story.item_ids || []).filter(function (x) { return x !== iid; });
      renderStories();
      return refocus("#s-link");
    }
    if ((el = t.closest("[data-unlink-skill]"))) {
      storyFromForm();
      var sk = el.getAttribute("data-unlink-skill");
      state.story.skills = (state.story.skills || []).filter(function (x) { return x !== sk; });
      renderStories();
      return refocus("#s-link");
    }
    if (!(el = t.closest("[data-act]"))) return;
    var name = el.getAttribute("data-act");
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
      }).catch(failed);
    } else if (name === "add-usual") {
      say("Adding...");
      api("POST", "/api/owner/casebooks/" + state.data.casebook.id + "/questions", { usual: true }).then(function (r) {
        return reloadCase().then(function () {
          say(r.added ? plural(r.added, "question") + " added." : "The usual questions are already on the table.");
          refocus('[data-act="add-usual"]');
        });
      }).catch(failed);
    } else if (name === "add-own") {
      state.addingQuestion = !state.addingQuestion;
      renderCase();
      refocus(state.addingQuestion ? "#q-text" : '[data-act="add-own"]');
    } else if (name === "to-story") {
      questionToStory();
    } else if (name === "drop-q") {
      var q = currentQuestion();
      if (!window.confirm("Take “" + q.text + "” off the table?")) return;
      api("DELETE", "/api/owner/casebooks/" + state.data.casebook.id + "/questions/" + q.id).then(function () {
        state.q = Math.max(0, state.q - 1);
        return reloadCase();
      }).then(function () { say("Question removed."); }).catch(failed);
    } else if (name === "comp-del") {
      var i = parseInt(el.getAttribute("data-i"), 10);
      setCompetencies(state.data.competencies.filter(function (_, j) { return j !== i; }), "#comp-new");
    } else if (name === "new-story") {
      state.story = { title: "", item_ids: [], skills: [], used_in: [] };
      renderStories();
      refocus("#s-title");
    } else if (name === "cancel-story") {
      state.story = state.stories[0] ? JSON.parse(JSON.stringify(state.stories[0])) : null;
      renderStories();
    } else if (name === "del-story") {
      var st = state.story;
      var uses = (st.used_in || []).length;
      if (!window.confirm("Delete “" + st.title + "”?" + (uses ? " It's used in " + plural(uses, "case") + "; those questions go back to their best match." : ""))) return;
      api("DELETE", "/api/owner/stories/" + st.id).then(function () {
        state.story = null;
        say("Story deleted.");
        return loadStories();
      }).catch(failed);
    } else if (name === "link") {
      linkSelected();
    }
  });

  main.addEventListener("change", function (e) {
    var sel = e.target.closest("[data-ev]");
    if (!sel) return;
    if (sel.id === "ev-story") return patchQuestion({ story_id: sel.value });
    var lead = document.getElementById("ev-lead").value;
    var backup = document.getElementById("ev-backup").value;
    patchQuestion({ evidence_refs: [lead, backup].filter(function (r, i, a) { return r && a.indexOf(r) === i; }) });
  });

  main.addEventListener("input", function (e) {
    if (e.target.matches && e.target.matches("textarea[data-star]")) {
      e.target.classList.toggle("empty-f", !e.target.value.trim());
    }
  });

  main.addEventListener("submit", function (e) {
    var form = e.target;
    if (form.id === "q-form") {
      e.preventDefault();
      var text = document.getElementById("q-text").value.trim();
      if (!text) {
        say("Type the question first.");
        return refocus("#q-text");
      }
      api("POST", "/api/owner/casebooks/" + state.data.casebook.id + "/questions", { text: text, kind: document.getElementById("q-kind").value })
        .then(function () {
          state.addingQuestion = false;
          state.q = state.data.questions.length;
          return reloadCase();
        }).then(function () { say("Question added."); refocus("#q-detail"); }).catch(failed);
    } else if (form.id === "comp-form") {
      e.preventDefault();
      var v = document.getElementById("comp-new").value.trim();
      if (!v) return;
      setCompetencies(state.data.competencies.concat([v]), "#comp-new");
    } else if (form.id === "story-form") {
      e.preventDefault();
      saveStory();
    }
  });

  main.addEventListener("keydown", function (e) {
    if (e.key === "Enter" && e.target.id === "s-link") {
      e.preventDefault();
      return linkSelected();
    }
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
    refocus("#tab-" + state.tab);
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
