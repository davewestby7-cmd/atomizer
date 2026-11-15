// PsyPull front end. Plain JavaScript, no build step: edit and reload the page.

const $ = (sel) => document.querySelector(sel);
const view = { bucket: "free", q: "", tag: "", source: "" };
let status = null;
let playingId = null;
const player = $("#player");

// ------------------------------------------------------------ helpers
function timeAgo(iso) {
  if (!iso) return "never";
  const hasZone = /([zZ]|[+-]\d\d:\d\d)$/.test(iso);
  const secs = (Date.now() - new Date(hasZone ? iso : iso + "Z").getTime()) / 1000;
  if (secs < 60) return "just now";
  if (secs < 3600) return `${Math.round(secs / 60)} min ago`;
  if (secs < 86400) return `${Math.round(secs / 3600)} h ago`;
  return `${Math.round(secs / 86400)} days ago`;
}
function bytes(n) {
  if (n < 1024 ** 2) return `${(n / 1024).toFixed(0)} KB`;
  if (n < 1024 ** 3) return `${(n / 1024 ** 2).toFixed(1)} MB`;
  return `${(n / 1024 ** 3).toFixed(2)} GB`;
}
function notice(text, kind = "info") {
  const el = $("#notice");
  const styles = {
    info: "border-teal-700/60 bg-teal-950/40 text-teal-200",
    error: "border-rose-700/60 bg-rose-950/40 text-rose-200",
  };
  el.className = `mb-4 text-sm rounded-lg px-4 py-3 border ${styles[kind]}`;
  el.textContent = text;
  el.classList.toggle("hidden", !text);
}
function priceBadge(r) {
  if (r.price_kind === "free") return ["FREE", "bg-lime-400 text-black"];
  if (r.price_kind === "nyp") return ["NYP · $0+", "bg-cyan-300 text-black"];
  const home = status?.home_currency || "";
  const local = r.price_home != null ? ` ≈ ${home} ${r.price_home.toFixed(2)}` : "";
  return [`${r.currency} ${r.price.toFixed(2)}${local}`, "bg-fuchsia-400 text-black"];
}

// ------------------------------------------------------------ status bar
async function loadStatus() {
  status = await (await fetch("/api/status")).json();
  for (const el of document.querySelectorAll("[data-count]")) {
    el.textContent = status.counts[el.dataset.count] || "";
  }
  $("#refreshInfo").textContent = status.refreshing
    ? "⟳ Checking sources… (this takes a minute)"
    : `Sources checked ${timeAgo(status.last_refresh)}` +
      (Object.keys(status.errors).length ? ` · problems with: ${Object.keys(status.errors).join(", ")}` : "");
  $("#refreshBtn").disabled = status.refreshing;
  $("#refreshBtn").classList.toggle("opacity-50", status.refreshing);

  const syncText = {
    "no-rclone": "Drive sync: rclone not installed (see README)",
    "no-remote": "Drive sync: rclone not configured (set rclone_remote in config.yaml)",
    ready: `Drive sync → ${status.rclone_remote} · last ${timeAgo(status.last_sync)}` +
      (status.last_sync && !status.last_sync_ok ? " (failed)" : ""),
  };
  $("#syncInfo").textContent = syncText[status.sync_state];
  $("#syncBtn").classList.toggle("opacity-50", status.sync_state !== "ready");
  $("#folderInfo").textContent = `Downloads: ${bytes(status.download_bytes)}`;
  $("#pulledPath").textContent = status.download_dir;

  renderChips();
  return status;
}

function renderChips() {
  const box = $("#chips");
  box.innerHTML = "";
  const src = document.createElement("select");
  src.className = "bg-slate-900/80 border border-violet-800/60 rounded-full px-2 py-1 text-slate-300";
  for (const [v, label] of [["", "all sources"], ["ektoplazm", "Ektoplazm"], ["bandcamp", "Bandcamp"]]) {
    src.add(new Option(label, v, false, view.source === v));
  }
  src.onchange = () => { view.source = src.value; loadReleases(); };
  box.appendChild(src);
  for (const t of ["", ...status.tags]) {
    const b = document.createElement("button");
    b.textContent = t || "all styles";
    b.className = "px-2.5 py-1 rounded-full border " + (view.tag === t
      ? "border-teal-300 bg-teal-400/20 text-teal-100"
      : "border-violet-800/60 text-slate-400 hover:text-slate-100");
    b.onclick = () => { view.tag = t; renderChips(); loadReleases(); };
    box.appendChild(b);
  }
}

// ------------------------------------------------------------ grid
async function loadReleases() {
  const params = new URLSearchParams({ bucket: view.bucket, q: view.q, tag: view.tag, source: view.source });
  const rows = await (await fetch(`/api/releases?${params}`)).json();
  const grid = $("#grid");
  grid.innerHTML = "";
  $("#pulledBar").classList.toggle("hidden", view.bucket !== "pulled");

  const empty = $("#empty");
  empty.classList.toggle("hidden", rows.length > 0);
  if (!rows.length) {
    empty.textContent = view.bucket === "pulled"
      ? "Nothing pulled yet. Find something on the Free tab and hit ⬇ Pull."
      : status?.refreshing ? "Checking sources… releases will appear shortly."
      : "Nothing here. Try another style, or press Refresh sources.";
  }
  for (const r of rows) grid.appendChild(card(r));
}

function card(r) {
  const node = $("#cardTpl").content.firstElementChild.cloneNode(true);
  node.dataset.id = r.id;
  node.querySelector(".cover").src = r.cover_url || "";
  node.querySelector(".artist").textContent = r.artist || r.label;
  node.querySelector(".title").textContent = r.title;
  node.querySelector(".title").title = r.title;
  node.querySelector(".meta").textContent =
    [r.label && r.label !== r.artist ? r.label : "", r.tags.slice(0, 3).join(" · "), r.released]
      .filter(Boolean).join(" · ");
  node.querySelector(".source").textContent = r.source;
  const [ptext, pcls] = priceBadge(r);
  const pb = node.querySelector(".price");
  pb.textContent = ptext;
  pb.className += " " + pcls;
  if (r.price_kind === "nyp") pb.title = "Name your price: pay what you like, even nothing";
  node.querySelector(".open").href = r.page_url;

  const play = node.querySelector(".play");
  if (!r.tracks.length) { play.disabled = true; play.classList.add("opacity-40"); play.title = "No sample available"; }
  play.onclick = () => togglePlay(r, node);
  if (playingId === r.id) { node.classList.add("playing"); play.textContent = "❚❚ Stop"; }

  const pull = node.querySelector(".pull");
  if (view.bucket === "pulled") {
    pull.textContent = "🗑 Delete";
    pull.className = pull.className.replace(/teal/g, "rose");
    pull.onclick = () => removePulled(r);
  } else if (r.pulled) {
    pull.textContent = "✓ Pulled";
    pull.disabled = true;
    pull.classList.add("opacity-60");
  } else if (r.can_pull) {
    pull.onclick = () => doPull(r, node);
  } else {
    // Bandcamp: downloads happen on Bandcamp's own page.
    pull.textContent = r.price_kind === "cheap" ? "🛒 Buy" : "⬇ Get";
    pull.title = "Opens the Bandcamp page";
    pull.onclick = () => window.open(r.page_url, "_blank", "noopener");
  }
  return node;
}

// ------------------------------------------------------------ actions
function togglePlay(r, node) {
  document.querySelectorAll(".playing").forEach((el) => {
    el.classList.remove("playing");
    el.querySelector(".play").textContent = "▶ Play";
  });
  if (playingId === r.id) { player.pause(); playingId = null; return; }
  playingId = r.id;
  // Ektoplazm gives a sample per track: pick one at random for variety.
  const src = r.tracks[Math.floor(Math.random() * r.tracks.length)];
  player.src = src;
  player.play().catch(() => notice("Couldn't play that sample. Try 🔗 to open the page.", "error"));
  node.classList.add("playing");
  node.querySelector(".play").textContent = "❚❚ Stop";
}
player.onended = () => { playingId = null; loadReleases(); };

async function doPull(r, node) {
  const btn = node.querySelector(".pull");
  const prog = node.querySelector(".progress");
  const bar = prog.querySelector(".bar");
  btn.disabled = true;
  btn.textContent = "Starting…";
  prog.classList.remove("hidden");

  const res = await fetch(`/api/pull/${encodeURIComponent(r.id)}`, { method: "POST" });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    notice(err.detail || "Pull failed", "error");
    btn.disabled = false; btn.textContent = "⬇ Pull";
    return;
  }
  // Read the server-sent events as they arrive.
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const parts = buffer.split("\n\n");
    buffer = parts.pop();
    for (const part of parts) {
      if (!part.startsWith("data: ")) continue;
      const ev = JSON.parse(part.slice(6));
      if (ev.stage === "download") {
        if (ev.percent >= 0) { bar.style.width = ev.percent + "%"; btn.textContent = `${ev.percent}%`; }
        else btn.textContent = bytes(ev.bytes);
      } else if (ev.stage === "unzip") {
        btn.textContent = "Unzipping…"; bar.style.width = "100%";
      } else if (ev.stage === "done") {
        btn.textContent = "✓ Pulled";
        notice(`Pulled “${r.artist} – ${r.title}” (${ev.files} files) into ${ev.path}`);
        loadStatus();
      } else if (ev.stage === "error") {
        notice(`Pull failed: ${ev.message}`, "error");
        btn.disabled = false; btn.textContent = "⬇ Pull";
        prog.classList.add("hidden");
      }
    }
  }
}

async function removePulled(r) {
  if (!confirm(`Delete the local files for “${r.artist} – ${r.title}”?`)) return;
  await fetch(`/api/pulled/${encodeURIComponent(r.id)}`, { method: "DELETE" });
  await loadStatus();
  loadReleases();
}

$("#refreshBtn").onclick = async () => {
  await fetch("/api/refresh", { method: "POST" });
  notice("Checking Ektoplazm and Bandcamp… new releases will appear in a minute or so.");
  pollWhileRefreshing();
};

$("#syncBtn").onclick = async () => {
  if (status.sync_state !== "ready") {
    notice("Google Drive sync isn't set up yet. See “Google Drive sync” in the README.", "error");
    return;
  }
  $("#syncBtn").textContent = "☁ Syncing…";
  const res = await (await fetch("/api/sync", { method: "POST" })).json();
  $("#syncBtn").textContent = "☁ Sync to Drive";
  notice(res.ok ? "Synced to Google Drive ✓" : `Sync failed: ${res.output}`, res.ok ? "info" : "error");
  loadStatus();
};

$("#openFolderBtn").onclick = () => fetch("/api/open-folder", { method: "POST" });

let searchTimer;
$("#search").oninput = (e) => {
  clearTimeout(searchTimer);
  searchTimer = setTimeout(() => { view.q = e.target.value.trim(); loadReleases(); }, 250);
};

function setTab(bucket) {
  view.bucket = bucket;
  document.querySelectorAll(".tab").forEach((t) => t.classList.toggle("tab-active", t.dataset.bucket === bucket));
  try { localStorage.setItem("psypull.tab", bucket); } catch {}
  loadReleases();
}
document.querySelectorAll(".tab").forEach((t) => (t.onclick = () => setTab(t.dataset.bucket)));

async function pollWhileRefreshing() {
  await loadStatus();
  await loadReleases();
  if (status.refreshing) setTimeout(pollWhileRefreshing, 4000);
  else notice("");
}

// ------------------------------------------------------------ start
(async () => {
  let tab = "free";
  try { tab = localStorage.getItem("psypull.tab") || "free"; } catch {}
  await loadStatus();
  setTab(tab);
  if (status.refreshing) pollWhileRefreshing();
})();
