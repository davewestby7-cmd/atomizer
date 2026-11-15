// Atomizer front end. Plain JavaScript, no build step: edit and reload the page.

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
  for (const [v, label] of [["", "all sources"], ["ektoplazm", "Ektoplazm"], ["bandcamp", "Bandcamp"], ["archive", "Internet Archive"], ["hearthis", "hearthis.at mixes"], ["sonictantra", "Sonic Tantra"], ["audius", "Audius"]]) {
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
  syncPlayState();
}

function card(r) {
  const node = $("#cardTpl").content.firstElementChild.cloneNode(true);
  node.dataset.id = r.id;
  node.querySelector(".cover").src = r.cover_url || "";
  node.querySelector(".artist").textContent = r.artist || r.label;
  node.querySelector(".title").textContent = r.title;
  node.querySelector(".title").title = r.title;
  node.querySelector(".meta").title = r.origin || "";
  node.querySelector(".meta").textContent =
    [r.origin ? `🌍 ${r.origin}` : "", r.label && r.label !== r.artist ? r.label : "",
     r.tags.slice(0, 3).join(" · "), r.released]
      .filter(Boolean).join(" · ");
  node.querySelector(".source").textContent = r.kind === "mix" ? `${r.source} · mix` : r.source;
  const [ptext, pcls] = priceBadge(r);
  const pb = node.querySelector(".price");
  pb.textContent = ptext;
  pb.className += " " + pcls;
  if (r.price_kind === "nyp") pb.title = "Name your price: pay what you like, even nothing";
  node.querySelector(".open").href = r.page_url;

  const play = node.querySelector(".play");
  if (!r.tracks.length) { play.disabled = true; play.classList.add("opacity-40"); play.title = "No sample available"; }
  play.onclick = () => togglePlay(r);

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
    pull.title = `Opens the ${r.source} page`;
    pull.onclick = () => window.open(r.page_url, "_blank", "noopener");
  }
  return node;
}

// ------------------------------------------------------------ actions
// ---- player: one release at a time; ⏮/⏭ move between its tracks
let nowRelease = null;   // the release object that's loaded
let nowIndex = 0;        // which of its tracks
let seeking = false;     // true while the user drags the progress slider

function fmtTime(s) {
  if (!isFinite(s) || s < 0) return "0:00";
  const m = Math.floor(s / 60), sec = Math.floor(s % 60);
  return m >= 60 ? `${Math.floor(m / 60)}:${String(m % 60).padStart(2, "0")}:${String(sec).padStart(2, "0")}`
                 : `${m}:${String(sec).padStart(2, "0")}`;
}
function setFill(range) {
  range.style.setProperty("--pct", `${(range.value - range.min) * 100 / (range.max - range.min)}%`);
}

function togglePlay(r) {
  if (nowRelease && nowRelease.id === r.id) {
    player.paused ? player.play() : player.pause();
  } else {
    loadTrack(r, 0);
  }
}

function loadTrack(r, index) {
  nowRelease = r;
  nowIndex = index;
  playingId = r.id;
  player.src = r.tracks[index];
  player.play().catch(() => notice("Couldn't play that sample. Try 🔗 to open the page.", "error"));

  $("#nowBar").classList.remove("hidden");
  document.body.classList.add("has-player");
  $("#npCover").src = r.cover_url || "";
  $("#npTitle").textContent = r.title;
  $("#npTitle").title = r.title;
  $("#npArtist").textContent = [r.artist || r.label, r.origin ? `🌍 ${r.origin}` : ""].filter(Boolean).join(" · ");
  $("#npTrack").textContent = r.tracks.length > 1 ? `Track ${index + 1} of ${r.tracks.length}` : r.source;
  $("#npOpen").href = r.page_url;
  $("#npPrev").disabled = index === 0 && r.tracks.length < 2;
  $("#npNext").disabled = index >= r.tracks.length - 1;
  $("#npSeek").value = 0; setFill($("#npSeek"));
  $("#npTime").textContent = "0:00";
  $("#npDur").textContent = "…";
  syncPlayState();
}

function stopPlayer() {
  player.pause();
  player.removeAttribute("src");
  player.load();
  nowRelease = null;
  playingId = null;
  $("#nowBar").classList.add("hidden");
  document.body.classList.remove("has-player");
  syncPlayState();
}

// Keep the play buttons on the cards and in the bar in step with the audio.
function syncPlayState() {
  const playing = nowRelease && !player.paused;
  $("#npPlay").textContent = playing ? "⏸" : "▶";
  document.querySelectorAll("#grid article").forEach((el) => {
    const mine = nowRelease && el.dataset.id === nowRelease.id;
    el.classList.toggle("playing", !!mine);
    const btn = el.querySelector(".play");
    if (!btn.disabled) btn.textContent = mine && playing ? "❚❚ Pause" : "▶ Play";
  });
}

player.addEventListener("play", syncPlayState);
player.addEventListener("pause", syncPlayState);
player.addEventListener("loadedmetadata", () => { $("#npDur").textContent = fmtTime(player.duration); });
player.addEventListener("timeupdate", () => {
  if (seeking || !isFinite(player.duration)) return;
  const seek = $("#npSeek");
  seek.value = Math.round(player.currentTime / player.duration * 1000);
  setFill(seek);
  $("#npTime").textContent = fmtTime(player.currentTime);
});
player.addEventListener("ended", () => {
  // Carry on through the release's tracks, then stop.
  if (nowRelease && nowIndex < nowRelease.tracks.length - 1) loadTrack(nowRelease, nowIndex + 1);
  else { player.currentTime = 0; syncPlayState(); }
});

$("#npPlay").onclick = () => { if (nowRelease) player.paused ? player.play() : player.pause(); };
$("#npPrev").onclick = () => {
  if (!nowRelease) return;
  // Like most players: past 3 seconds, ⏮ restarts the track; otherwise go back one.
  if (player.currentTime > 3 || nowIndex === 0) player.currentTime = 0;
  else loadTrack(nowRelease, nowIndex - 1);
};
$("#npNext").onclick = () => {
  if (nowRelease && nowIndex < nowRelease.tracks.length - 1) loadTrack(nowRelease, nowIndex + 1);
};
const skip = (secs) => {
  if (nowRelease && isFinite(player.duration))
    player.currentTime = Math.min(Math.max(0, player.currentTime + secs), player.duration - 0.1);
};
$("#npBack").onclick = () => skip(-10);
$("#npFwd").onclick = () => skip(10);
$("#npClose").onclick = stopPlayer;

const seek = $("#npSeek");
seek.addEventListener("input", () => {
  seeking = true;
  setFill(seek);
  if (isFinite(player.duration)) $("#npTime").textContent = fmtTime(seek.value / 1000 * player.duration);
});
seek.addEventListener("change", () => {
  if (isFinite(player.duration)) player.currentTime = seek.value / 1000 * player.duration;
  seeking = false;
});

const vol = $("#npVol");
try { vol.value = localStorage.getItem("atomizer.volume") ?? 80; } catch {}
player.volume = vol.value / 100;
setFill(vol);
vol.addEventListener("input", () => {
  player.volume = vol.value / 100;
  player.muted = false;
  $("#npMute").textContent = vol.value == 0 ? "🔇" : "🔊";
  setFill(vol);
  try { localStorage.setItem("atomizer.volume", vol.value); } catch {}
});
$("#npMute").onclick = () => {
  player.muted = !player.muted;
  $("#npMute").textContent = player.muted ? "🔇" : "🔊";
};

// Keyboard: space = play/pause, ←/→ = 10 s, shift+←/→ = previous/next track.
document.addEventListener("keydown", (e) => {
  if (!nowRelease || e.target.closest?.("input, textarea, select, button")) return;
  if (e.code === "Space") { e.preventDefault(); $("#npPlay").click(); }
  else if (e.key === "ArrowLeft") { e.preventDefault(); e.shiftKey ? $("#npPrev").click() : skip(-10); }
  else if (e.key === "ArrowRight") { e.preventDefault(); e.shiftKey ? $("#npNext").click() : skip(10); }
});

// Media keys / lock-screen / headphone buttons, where the browser supports it.
if ("mediaSession" in navigator) {
  player.addEventListener("play", () => {
    if (!nowRelease) return;
    navigator.mediaSession.metadata = new MediaMetadata({
      title: nowRelease.title, artist: nowRelease.artist, album: nowRelease.label || nowRelease.source,
      artwork: nowRelease.cover_url ? [{ src: nowRelease.cover_url, sizes: "350x350" }] : [],
    });
  });
  const ms = navigator.mediaSession;
  ms.setActionHandler("play", () => player.play());
  ms.setActionHandler("pause", () => player.pause());
  ms.setActionHandler("previoustrack", () => $("#npPrev").click());
  ms.setActionHandler("nexttrack", () => $("#npNext").click());
  ms.setActionHandler("seekbackward", () => skip(-10));
  ms.setActionHandler("seekforward", () => skip(10));
}

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
  notice("Checking all sources… new releases will appear over the next few minutes.");
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
  try { localStorage.setItem("atomizer.tab", bucket); } catch {}
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
  try { tab = localStorage.getItem("atomizer.tab") || "free"; } catch {}
  await loadStatus();
  setTab(tab);
  if (status.refreshing) pollWhileRefreshing();
})();
