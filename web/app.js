/* Temporal Entanglements - local map. Reads window.TE_DATA (written by update.py into data/events.js). */
(function () {
  "use strict";

  var DATA = window.TE_DATA;
  var $ = function (id) { return document.getElementById(id); };

  // ---------- tiny DOM helper (scraped text only ever goes in as text nodes) ----------
  function el(tag, attrs) {
    var n = document.createElement(tag);
    Object.keys(attrs || {}).forEach(function (k) {
      var v = attrs[k];
      if (v == null || v === false) return;
      if (k === "class") n.className = v;
      else if (k === "text") n.textContent = v;
      else if (k.slice(0, 2) === "on") n.addEventListener(k.slice(2), v);
      else n.setAttribute(k, v === true ? "" : v);
    });
    Array.prototype.slice.call(arguments, 2).forEach(function add(kid) {
      if (kid == null || kid === false) return;
      if (Array.isArray(kid)) return kid.forEach(add);
      n.appendChild(kid.nodeType ? kid : document.createTextNode(kid));
    });
    return n;
  }
  var safeUrl = function (u) { return /^https?:\/\//i.test(u || "") ? u : null; };

  // ---------- dates ----------
  var MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];
  var DOWS = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"];
  var pad = function (n) { return (n < 10 ? "0" : "") + n; };
  var parseDay = function (s) { var p = s.split("-").map(Number); return new Date(p[0], p[1] - 1, p[2]); };
  var dayKey = function (d) { return d.getFullYear() + "-" + pad(d.getMonth() + 1) + "-" + pad(d.getDate()); };
  var addDays = function (key, n) { var d = parseDay(key); d.setDate(d.getDate() + n); return dayKey(d); };
  var longDay = function (key) { var d = parseDay(key); return DOWS[d.getDay()] + ", " + MONTHS[d.getMonth()] + " " + d.getDate(); };
  var shortDay = function (key) { var d = parseDay(key); return MONTHS[d.getMonth()].slice(0, 3) + " " + d.getDate(); };
  function fmtTime(hhmm) {
    var p = hhmm.split(":").map(Number), h = p[0], m = p[1], ap = h >= 12 ? "PM" : "AM";
    h = h % 12 || 12;
    return m ? h + ":" + pad(m) + " " + ap : h + " " + ap;
  }

  // ---------- empty / stale data ----------
  if (!DATA || !DATA.events) {
    $("range").textContent = "no data yet";
    $("heading").textContent = "No events loaded";
    var e0 = $("empty"); e0.hidden = false;
    e0.textContent = /^(localhost|127\.0\.0\.1|\[::1\]|)$/.test(location.hostname)
      ? "Run  bash run.sh  (or  python3 update.py ) to collect events, then reload this page."
      : "The events are not available yet. The map updates itself every morning.";
    return;
  }

  var events = DATA.events;
  events.forEach(function (ev) {
    ev._first = ev.start.slice(0, 10);
    var last = (ev.end || ev.start).slice(0, 10);
    if (ev.end && /T00:00$/.test(ev.end) && ev.end > ev.start) last = addDays(last, -1);
    ev._last = last < ev._first ? ev._first : last;
  });

  // ---------- organizations (each calendar is one; an event listed by several belongs to all of them) ----------
  var PALETTE = ["#f5b04c", "#58c4dd", "#ef6f7e", "#8fd16a", "#b58cf2", "#f28c4a", "#4fa0f5", "#e8d35c", "#e57ac9",
    "#47cfa3", "#c8a57e", "#7f9cff", "#ff9d7d", "#a6d86f", "#d08af0", "#5fd7d0", "#f2b8b8", "#9bb0c4"];
  var orgs = (DATA.venues || []).map(function (v, i) {
    return { id: v.id, name: v.name, short: v.short || v.name, color: PALETTE[i % PALETTE.length], url: v.url };
  });
  var orgById = {};
  orgs.forEach(function (o) { orgById[o.id] = o; });
  events.forEach(function (ev) {
    ev._orgs = [ev.venue_id].concat(ev.also_on_ids || []).filter(function (id) { return orgById[id]; });
  });
  var off = {};   // organization ids switched off (remembered between visits when the browser allows it)
  try { JSON.parse(localStorage.getItem("te.hiddenOrgs") || "[]").forEach(function (id) { if (orgById[id]) off[id] = true; }); } catch (e) { /* storage unavailable */ }
  function saveOff() { try { localStorage.setItem("te.hiddenOrgs", JSON.stringify(Object.keys(off))); } catch (e) { /* ignore */ } }
  var isShown = function (ev) { return !ev._orgs.length || ev._orgs.some(function (id) { return !off[id]; }); };
  var orgColor = function (ev) { var o = orgById[ev.venue_id]; return o ? o.color : PALETTE[0]; };
  var rgba = function (hex, a) { var n = parseInt(hex.slice(1), 16); return "rgba(" + (n >> 16) + "," + ((n >> 8) & 255) + "," + (n & 255) + "," + a + ")"; };
  var redundant = function (o, text) {
    var t = (text || "").toLowerCase();
    return !o || t.indexOf(o.short.toLowerCase()) >= 0 || t.indexOf(o.name.toLowerCase()) >= 0;
  };

  var days = [];
  for (var k = DATA.window.start; k <= DATA.window.end; k = addDays(k, 1)) days.push(k);
  var todayKey = dayKey(new Date());
  var inWindow = todayKey >= days[0] && todayKey <= days[days.length - 1];
  var state = { day: null, ongoing: false, active: null };

  $("range").textContent = shortDay(days[0]) + " – " + shortDay(days[days.length - 1]);

  var banner = $("banner");
  if (todayKey > days[days.length - 1]) {
    banner.hidden = false;
    var local = /^(localhost|127\.0\.0\.1|\[::1\]|)$/.test(location.hostname);
    banner.textContent = "This data ends " + shortDay(days[days.length - 1]) + "." +
      (local ? " Run update.py to refresh it." : " The map updates itself every morning; try again later.");
  } else if (todayKey < days[0]) {
    banner.hidden = false;
    banner.textContent = "This data starts " + shortDay(days[0]) + ".";
  }

  // ---------- queries ----------
  function on(day, ignoreFilter) {
    var regular = [], ongoing = [], hiddenN = 0;
    events.forEach(function (ev) {
      if (day < ev._first || day > ev._last) return;
      if (!ignoreFilter && !isShown(ev)) { hiddenN++; return; }
      (ev.ongoing ? ongoing : regular).push(ev);
    });
    regular.sort(function (a, b) {
      if (a.has_time !== b.has_time) return a.has_time ? -1 : 1;
      return a.start < b.start ? -1 : a.start > b.start ? 1 : a.title.localeCompare(b.title);
    });
    ongoing.sort(function (a, b) { return a.title.localeCompare(b.title); });
    return { regular: regular, ongoing: ongoing, hidden: hiddenN };
  }
  function timeLabel(ev, day) {
    if (ev.ongoing) return "Through " + shortDay(ev._last);
    if (ev.all_day) return "All day";
    if (!ev.has_time) return "Time TBA";
    if (day !== ev._first) return "Continues";
    return fmtTime(ev.start.slice(11));
  }
  function detailBits(ev, day) {
    var bits = [];
    if (ev.has_time && ev.end && ev.end.slice(0, 10) === ev._first && day === ev._first) bits.push("until " + fmtTime(ev.end.slice(11)));
    if (ev.doors) bits.push("doors " + fmtTime(ev.doors));
    if (!ev.ongoing && ev._last !== ev._first) bits.push(shortDay(ev._first) + " – " + shortDay(ev._last));
    return bits;
  }

  // ---------- map ----------
  var map = L.map("map", { zoomControl: false, zoomSnap: 0.5 }).setView([38.627, -90.199], 12);
  L.control.zoom({ position: "bottomright" }).addTo(map);
  var cfg = window.TE_MAP || {};
  var tileUrl = cfg.tiles || "https://tile.openstreetmap.org/{z}/{x}/{y}.png";
  var tileAttr = cfg.attribution || '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors';
  var darken = cfg.darken !== false;
  if (cfg.cartoKey) {   // optional true-dark basemap, needs CARTO's free key
    tileUrl = "https://basemaps.cartocdn.com/rastertiles/dark_all/{z}/{x}/{y}{r}.png?key=" + encodeURIComponent(cfg.cartoKey);
    tileAttr = '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors, &copy; <a href="https://carto.com/attributions">CARTO</a>';
    darken = false;
  }
  $("map").classList.toggle("dark-tiles", darken);
  var tiles = L.tileLayer(tileUrl, { maxZoom: 19, attribution: tileAttr, referrerPolicy: "strict-origin-when-cross-origin" }).addTo(map);
  var tilesOk = 0, tilesBad = 0;
  tiles.on("tileload", function () { tilesOk++; });
  tiles.on("tileerror", function () {
    tilesBad++;
    if (tilesBad >= 4 && tilesOk === 0) {
      var n = $("tilenote"); n.hidden = false;
      n.textContent = "The map background isn't loading (the pins still work). Check your internet connection; browser privacy tools that strip the Referer header can also block OpenStreetMap tiles.";
    }
  });
  tiles.on("tileload", function () { if (tilesOk === 1) $("tilenote").hidden = true; });
  var layer = L.layerGroup().addTo(map);
  var markerOf = {};   // event id -> marker
  var pinOf = {};      // event id -> pin element wrapper (for highlight)

  function groupByPlace(list) {
    var groups = [];
    list.forEach(function (ev) {
      if (ev.lat == null) return;
      var g = groups.find(function (x) { return Math.abs(x.lat - ev.lat) < 0.0003 && Math.abs(x.lng - ev.lng) < 0.0003; });
      if (!g) { g = { lat: ev.lat, lng: ev.lng, events: [] }; groups.push(g); }
      g.events.push(ev);
    });
    return groups;
  }
  function mostCommon(arr) {
    var c = {}, best = arr[0];
    arr.forEach(function (x) { c[x] = (c[x] || 0) + 1; if (c[x] > c[best]) best = x; });
    return best;
  }
  function popupFor(g, day) {
    var name = mostCommon(g.events.map(function (e) { return e.location; }));
    var addr = (g.events.filter(function (e) { return e.location === name && e.address; })[0] || {}).address || "";
    var approx = g.events.every(function (e) { return e.approx; });
    return el("div", { class: "pop" },
      el("h4", { text: name }),
      el("div", { class: "addr", text: (addr || "") + (approx ? (addr ? " · " : "") + "approximate location" : "") }),
      el("ul", {}, g.events.map(function (ev) {
        var u = safeUrl(ev.url), o = orgById[ev.venue_id];
        var sub = [ev.location !== name ? ev.location : "", redundant(o, name + " " + ev.location) ? "" : o.short].filter(Boolean).join(" · ");
        return el("li", {},
          o ? el("span", { class: "sw-dot", style: "--oc:" + o.color }) : null,
          el("span", { class: "pt", text: timeLabel(ev, day) }),
          u ? el("a", { href: u, target: "_blank", rel: "noopener noreferrer", text: ev.title }) : ev.title,
          sub ? el("span", { class: "sub2", text: sub }) : null);
      })));
  }

  function drawMarkers(list, day) {
    layer.clearLayers();
    markerOf = {}; pinOf = {};
    var groups = groupByPlace(list), pts = [];
    groups.forEach(function (g) {
      var n = g.events.length;
      var allOngoing = g.events.every(function (e) { return e.ongoing; });
      var approx = g.events.every(function (e) { return e.approx; });
      var cols = [];
      g.events.forEach(function (e) { var c = orgColor(e); if (cols.indexOf(c) < 0) cols.push(c); });
      var mix = cols.length > 1;
      var cls = "pin " + (n > 1 ? "many" : "one") + (mix ? " mix" : "") + (!mix && allOngoing ? " ring" : "") + (!mix && approx && !allOngoing ? " approx" : "");
      var style = "--c:" + cols[0] + ";--g:" + rgba(cols[0], 0.22) + (mix ? ";background:conic-gradient(" + cols.map(function (c, i) {
        return c + " " + Math.round(i * 100 / cols.length) + "% " + Math.round((i + 1) * 100 / cols.length) + "%";
      }).join(",") + ")" : "");
      var size = n > 1 ? 28 : 16;
      var icon = L.divIcon({ className: "pin-wrap", html: '<div class="' + cls + '" style="' + style + '">' + (mix ? "<span>" + n + "</span>" : (n > 1 ? n : "")) + "</div>", iconSize: [size, size], iconAnchor: [size / 2, size / 2], popupAnchor: [0, -size / 2] });
      var m = L.marker([g.lat, g.lng], { icon: icon, riseOnHover: true, title: g.events.map(function (e) { return e.title; }).join("\n") }).addTo(layer);
      m.bindPopup(popupFor(g, day), { maxWidth: 320, minWidth: 220 });
      m.on("click", function () { setActive(g.events[0].id, false); });
      m.on("popupclose", function () { if (state.active && markerOf[state.active] === m) setActive(null, false); });
      g.events.forEach(function (e) { markerOf[e.id] = m; });
      pts.push([g.lat, g.lng]);
    });
    return pts;
  }
  function fit(pts) {
    if (!pts.length) return;
    var b = L.latLngBounds(pts);
    if (pts.length === 1) { if (!map.getBounds().contains(b)) map.setView(pts[0], Math.max(map.getZoom(), 14)); return; }
    if (!map.getBounds().pad(-0.08).contains(b)) map.fitBounds(b, { padding: [60, 60], maxZoom: 14 });
  }

  // ---------- list ----------
  function setActive(id, fromList) {
    state.active = id;
    Array.prototype.forEach.call(document.querySelectorAll(".ev"), function (n) {
      n.classList.toggle("active", n.dataset.id === id);
    });
    Array.prototype.forEach.call(document.querySelectorAll(".pin.on"), function (n) { n.classList.remove("on"); });
    if (!id) return;
    var m = markerOf[id];
    if (m && m.getElement()) { var p = m.getElement().querySelector(".pin"); if (p) p.classList.add("on"); }
    var li = document.querySelector('.ev[data-id="' + id + '"]');
    if (li && !fromList) li.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }

  function card(ev, day) {
    var u = safeUrl(ev.url);
    var where = ev.location;
    var tags = [];
    if (ev.lat == null) tags.push(el("span", { class: "tag warn", text: "not on map" }));
    else if (ev.approx) tags.push(el("span", { class: "tag warn", text: "approximate location" }));
    if (ev.confidence === "text") tags.push(el("span", { class: "tag warn", title: "The date was read from the page's text, not a calendar field", text: "date inferred" }));
    if (ev.also_on && ev.also_on.length) tags.push(el("span", { class: "tag", text: "also on " + ev.also_on.join(", ") }));
    var bits = detailBits(ev, day);
    var o = orgById[ev.venue_id];
    var whereText = [where].concat(bits).filter(Boolean).join(" · ");
    var li = el("li", { class: "ev", "data-id": ev.id, tabindex: "0", style: o ? "--oc:" + o.color : null, onclick: function (e) {
      if (e.target.closest("a")) return;
      focusEvent(ev);
    }, onkeydown: function (e) { if (e.key === "Enter" && !e.target.closest("a")) focusEvent(ev); } },
      el("div", { class: "t" + (ev.has_time && !ev.ongoing && !ev.all_day && day === ev._first ? "" : " dim"), text: timeLabel(ev, day) }),
      el("div", {},
        el("div", { class: "title" }, u ? el("a", { href: u, target: "_blank", rel: "noopener noreferrer", text: ev.title }) : ev.title),
        el("div", { class: "where" }, whereText, redundant(o, where) ? null : el("span", { class: "org", text: (whereText ? " · " : "") + o.short })),
        tags.length ? el("div", { class: "meta" }, tags) : null));
    return li;
  }
  function focusEvent(ev) {
    setActive(ev.id, true);
    var m = markerOf[ev.id];
    if (m) {
      map.flyTo(m.getLatLng(), Math.max(map.getZoom(), 15), { duration: 0.6 });
      map.once("moveend", function () { m.openPopup(); });
    }
  }

  // ---------- render ----------
  function render(refit) {
    var day = state.day, q = on(day);
    var shown = q.regular.concat(state.ongoing ? q.ongoing : []);
    updateChips(day);

    $("heading").textContent = (day === todayKey ? "Today · " : "") + longDay(day);
    $("count").textContent = q.regular.length + (q.regular.length === 1 ? " event" : " events");
    var list = $("list"); list.textContent = "";
    q.regular.forEach(function (ev) { list.appendChild(card(ev, day)); });
    var og = $("ongoing-block"), ol = $("ongoing-list"); ol.textContent = "";
    og.hidden = !(state.ongoing && q.ongoing.length);
    if (!og.hidden) q.ongoing.forEach(function (ev) { ol.appendChild(card(ev, day)); });

    var empty = $("empty");
    empty.hidden = q.regular.length > 0 || (state.ongoing && q.ongoing.length > 0);
    if (!empty.hidden) {
      empty.textContent = q.ongoing.length && !state.ongoing
        ? "Nothing scheduled on this day. " + q.ongoing.length + " ongoing run" + (q.ongoing.length > 1 ? "s are" : " is") + " hidden – tick the box above to include them."
        : q.hidden ? "Nothing to show – " + q.hidden + " event" + (q.hidden > 1 ? "s" : "") + " on this day come from organizations you have switched off."
        : "Nothing listed for this day.";
    }

    var pts = drawMarkers(shown, day);
    if (refit) fit(pts);
    setActive(state.active && shown.some(function (e) { return e.id === state.active; }) ? state.active : null, true);
    renderStrip();
    $("date").value = day;
    $("prev").disabled = day <= days[0];
    $("next").disabled = day >= days[days.length - 1];
    $("today").disabled = !inWindow;
    $("listwrap").scrollTop = 0;
    try { history.replaceState(null, "", "#" + day); } catch (e) { /* file:// in some browsers */ }
  }

  function renderStrip() {
    var strip = $("strip"); strip.textContent = "";
    days.forEach(function (key, i) {
      var q = on(key), n = q.regular.length + (state.ongoing ? q.ongoing.length : 0), d = parseDay(key);
      var showMonth = i === 0 || d.getDate() === 1;
      var b = el("button", { type: "button", class: "day" + (key === state.day ? " active" : "") + (n ? "" : " empty") + (key === todayKey ? " today" : ""),
        "data-day": key, "aria-pressed": key === state.day ? "true" : "false", "aria-label": longDay(key) + ", " + n + " events",
        onclick: function () { select(key); } },
        el("span", { class: "mon", text: showMonth ? MONTHS[d.getMonth()].slice(0, 3) : "" }),
        el("span", { class: "dow", text: DOWS[d.getDay()].slice(0, 3) }),
        el("span", { class: "num", text: String(d.getDate()) }),
        el("span", { class: "cnt", text: String(n) }));
      strip.appendChild(b);
    });
    var act = strip.querySelector(".active");
    if (act) strip.scrollLeft = act.offsetLeft - strip.clientWidth / 2 + act.clientWidth / 2;
  }

  function select(key, refit) {
    if (key < days[0]) key = days[0];
    if (key > days[days.length - 1]) key = days[days.length - 1];
    state.day = key; state.active = null;
    map.closePopup();
    render(refit !== false);
  }

  // ---------- organization filter ----------
  var chipEls = {};
  (function chips() {
    var box = $("org-chips");
    orgs.filter(function (o) { return events.some(function (ev) { return ev._orgs.indexOf(o.id) >= 0; }); }).forEach(function (o) {
      var b = el("button", { type: "button", class: "chip", "aria-pressed": "true", style: "--oc:" + o.color,
        title: o.name + " (click to hide or show, double-click to show only this one)",
        onclick: function () { if (off[o.id]) delete off[o.id]; else off[o.id] = true; saveOff(); render(true); },
        ondblclick: function () { off = {}; Object.keys(chipEls).forEach(function (id) { if (id !== o.id) off[id] = true; }); saveOff(); render(true); } },
        el("span", { class: "sw" }), el("span", { text: o.short }), el("span", { class: "n" }));
      chipEls[o.id] = b;
      box.appendChild(b);
    });
    var box2 = $("orgs");   // remember whether the panel was left open
    try { if (localStorage.getItem("te.orgsOpen") === "0") box2.open = false; } catch (e) { /* ignore */ }
    box2.addEventListener("toggle", function () { try { localStorage.setItem("te.orgsOpen", box2.open ? "1" : "0"); } catch (e) { /* ignore */ } });
    $("orgs-all").addEventListener("click", function () { off = {}; saveOff(); render(true); });
    $("orgs-none").addEventListener("click", function () { Object.keys(chipEls).forEach(function (id) { off[id] = true; }); saveOff(); render(true); });
  })();
  function updateChips(day) {
    var all = on(day, true), counts = {}, total = 0, active = 0;
    all.regular.concat(state.ongoing ? all.ongoing : []).forEach(function (ev) {
      ev._orgs.forEach(function (id) { counts[id] = (counts[id] || 0) + 1; });
    });
    Object.keys(chipEls).forEach(function (id) {
      var b = chipEls[id], c = counts[id] || 0, isOn = !off[id];
      total++;
      if (isOn) active++;
      b.setAttribute("aria-pressed", isOn ? "true" : "false");
      b.classList.toggle("none", c === 0);
      b.lastChild.textContent = c ? String(c) : "";
    });
    $("orgs-sum").textContent = active === total ? "all " + total + " shown" : active + " of " + total + " shown";
  }

  // ---------- sources ----------
  (function sources() {
    var gen = DATA.generated_at ? new Date(DATA.generated_at) : null;
    $("updated").textContent = gen ? "updated " + MONTHS[gen.getMonth()].slice(0, 3) + " " + gen.getDate() + ", " + fmtTime(pad(gen.getHours()) + ":" + pad(gen.getMinutes())) : "";
    var ul = $("source-list");
    DATA.venues.forEach(function (v) {
      var status = v.error || v.strategy === "none" ? "bad" : v.count === 0 ? "warn" : "";
      var u = safeUrl(v.url);
      var o = orgById[v.id];
      ul.appendChild(el("li", {},
        el("span", { class: "dot " + status }),
        el("span", {}, o ? el("span", { class: "sw-dot", style: "--oc:" + o.color }) : null,
          u ? el("a", { href: u, target: "_blank", rel: "noopener noreferrer", text: v.name }) : v.name),
        el("span", { class: "n", text: v.count + (v.count === 1 ? " event" : " events") }),
        (v.note || v.error) ? el("span", { class: "note", text: [v.error, v.note].filter(Boolean).join(" — ") }) : null));
    });
    var unplaced = events.filter(function (e) { return e.lat == null; }).length;
    if (unplaced) ul.appendChild(el("li", {}, el("span", { class: "dot warn" }), el("span", { text: unplaced + " event(s) have no map location" }), el("span")));
  })();

  // ---------- wire up ----------
  $("date").min = days[0]; $("date").max = days[days.length - 1];
  $("date").addEventListener("change", function (e) { if (e.target.value) select(e.target.value); });
  $("prev").addEventListener("click", function () { select(addDays(state.day, -1)); });
  $("next").addEventListener("click", function () { select(addDays(state.day, 1)); });
  $("today").addEventListener("click", function () { select(todayKey); });
  $("ongoing").addEventListener("change", function (e) { state.ongoing = e.target.checked; render(true); });
  document.addEventListener("keydown", function (e) {
    if (e.target.matches("input, textarea, select") || e.metaKey || e.ctrlKey || e.altKey) return;
    if (e.key === "ArrowLeft") { select(addDays(state.day, -1)); e.preventDefault(); }
    if (e.key === "ArrowRight") { select(addDays(state.day, 1)); e.preventDefault(); }
  });

  var fromHash = (location.hash || "").slice(1);
  var start = /^\d{4}-\d{2}-\d{2}$/.test(fromHash) ? fromHash : (inWindow ? todayKey : days[0]);
  select(start, true);
  window.addEventListener("load", function () { map.invalidateSize(); });
})();
