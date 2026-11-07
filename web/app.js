const $ = (id) => document.getElementById(id);

const state = {
  dashboard: null,
  board: null,
  messages: [],
  prio: "all",
  auto: true,
  busy: false,
  refreshing: false,
  timer: null,
};

function fmtNum(n) {
  if (n == null || Number.isNaN(Number(n))) return "—";
  const x = Number(n);
  const abs = Math.abs(x);
  const sign = x < 0 ? "-" : "";
  if (abs >= 1e8) return sign + (abs / 1e8).toFixed(2) + "亿";
  if (abs >= 1e4) return sign + (abs / 1e4).toFixed(1) + "万";
  if (abs >= 100) return sign + Math.round(abs).toLocaleString("zh-CN");
  return sign + abs.toFixed(2);
}

function toast(text) {
  const el = $("toast");
  el.textContent = text;
  el.hidden = false;
  clearTimeout(el._t);
  el._t = setTimeout(() => { el.hidden = true; }, 3200);
}

async function api(path, opts = {}) {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json", ...(opts.headers || {}) },
    ...opts,
  });
  if (!res.ok) {
    let msg = res.statusText;
    try {
      const j = await res.json();
      msg = j.detail || j.message || JSON.stringify(j);
    } catch (_) {
      msg = await res.text();
    }
    throw new Error(msg);
  }
  if (res.headers.get("content-type")?.includes("text/event-stream")) return res;
  return res.json();
}

function kpi(label, value, sub, cls) {
  return `<article class="kpi ${cls || ""}"><div class="k">${label}</div><div class="v">${value}</div>${sub ? `<div class="s">${sub}</div>` : ""}</article>`;
}

function renderKpis(d) {
  const c = d.country || {};
  const t = c.treasury || {};
  const bal = t.weekly_balance;
  const balCls = bal > 0 ? "good" : bal < 0 ? "warn" : "";
  $("kpis").innerHTML = [
    kpi("日期", (d.meta || {}).game_date || "—", (d.meta || {}).version),
    kpi("国家", `${c.name || "—"}`, c.tag),
    kpi("等级", rankLabel(c.rank), `威望 ${fmtNum(c.prestige)} · #${c.prestige_rank_score ?? "—"}`),
    kpi("GDP", fmtNum(c.gdp), `${c.states || 0} 省`),
    kpi("人口", fmtNum(c.population), popMix(d.population_detail)),
    kpi("金库", fmtNum(t.money), `信用 ${fmtNum(t.credit_limit)}`),
    kpi("周结余", fmtNum(bal), `税 ${taxLabel(c.tax_level)}`, balCls),
    kpi("生活水平", c.sol != null ? Number(c.sol).toFixed(1) : "—", `恶名 ${fmtNum(c.infamy)}`),
  ].join("");
}

function rankLabel(r) {
  const map = {
    great_power: "列强",
    major_power: "大国",
    unrecognized_major_power: "未承认大国",
    minor_power: "小国",
    unrecognized_regional_power: "未承认区域强国",
    insignificant_power: "微不足道",
  };
  return map[r] || r || "—";
}
function taxLabel(t) {
  return ({ very_low: "极低", low: "低", medium: "中", high: "高", very_high: "极高" }[t] || t || "—");
}
function popMix(p) {
  if (!p) return "";
  const tot = p.total || 1;
  return `下 ${(100 * (p.lower || 0) / tot).toFixed(0)}% · 中 ${(100 * (p.middle || 0) / tot).toFixed(0)}%`;
}

function renderMeta(d) {
  const chips = [];
  for (const g of d.interest_groups || []) {
    const cls = g.in_government ? "gov" : (g.approval_state === "unhappy" || (g.approval ?? 0) <= -2 ? "bad" : "");
    chips.push(`<span class="chip ${cls}">${g.name || g.definition} ${(g.clout * 100).toFixed(0)}%</span>`);
  }
  const laws = (d.laws || []).slice(0, 12).map((l) => `<span class="chip">${l.name || l.law}</span>`);
  const gps = (d.great_powers || []).map((g) => `<span class="chip">${g.name || g.tag}</span>`);
  const jes = (d.journal || []).map((j) => `<span class="chip bad">${j.name || j.type}</span>`);
  $("meta-row").innerHTML = [
    ...chips,
    ...jes,
    ...laws,
    gps.length ? `<span class="chip">列强 ${gps.map((x) => x.replace(/<[^>]+>/g, "")).join(" · ")}</span>` : "",
  ].join("");
}

function renderBoard() {
  const board = state.board || { actions: [] };
  const intent = $("intent");
  if (board.intent) {
    intent.hidden = false;
    intent.textContent = "意图：" + board.intent;
  } else {
    intent.hidden = true;
  }
  $("board-hint").textContent =
    board.source === "agent" ? "顾问根据对话改写" : "由存档启发式生成，对话后会改写";
  if (board.save_changed) {
    $("board-hint").textContent += " · 存档已变，可让顾问按新数据重算";
  }
  const actions = (board.actions || []).filter((a) => state.prio === "all" || a.priority === state.prio);
  if (!actions.length) {
    $("board").innerHTML = `<div class="empty">还没有动作。先刷新存档，或在左边说明你想怎么玩。</div>`;
    return;
  }
  $("board").innerHTML = actions
    .map(
      (a) => `<article class="card ${a.priority}">
        <div class="row1">
          <h3>${esc(a.title)}</h3>
          <span class="tags">${esc(a.direction_label || a.direction)} · ${esc(a.priority_label || a.priority)}</span>
        </div>
        ${a.detail ? `<p>${esc(a.detail)}</p>` : ""}
        ${a.reason ? `<p>${esc(a.reason)}</p>` : ""}
      </article>`
    )
    .join("");
}

function esc(s) {
  return String(s ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;");
}

function applyPayload(payload) {
  if (payload.dashboard) {
    state.dashboard = payload.dashboard;
    const d = payload.dashboard;
    const c = d.country || {};
    $("save-line").textContent = `${d.save || ""} · ${c.name || ""} · 载入 ${d.loaded_at || ""}`;
    renderKpis(d);
    renderMeta(d);
  }
  if (payload.board) {
    state.board = payload.board;
    renderBoard();
  }
}

function showProgress(pct, label) {
  const wrap = $("progress-wrap");
  if (!wrap) return;
  wrap.hidden = false;
  const n = Math.max(0, Math.min(100, Number(pct) || 0));
  $("progress-label").textContent = label || "正在读取存档…";
  $("progress-pct").textContent = Math.round(n) + "%";
  const fill = $("progress-fill");
  fill.style.width = Math.max(n, 3) + "%";
  fill.classList.toggle("indeterminate", n < 3);
  $("progress-bar").setAttribute("aria-valuenow", String(Math.round(n)));
}

function hideProgress() {
  const wrap = $("progress-wrap");
  if (wrap) wrap.hidden = true;
}

async function readSSE(res, onEvent) {
  const reader = res.body.getReader();
  const dec = new TextDecoder();
  let buf = "";
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buf += dec.decode(value, { stream: true });
    const chunks = buf.split("\n\n");
    buf = chunks.pop() || "";
    for (const chunk of chunks) {
      const ev = chunk.match(/^event: (.+)$/m)?.[1];
      const dataLine = chunk
        .split("\n")
        .filter((l) => l.startsWith("data: "))
        .map((l) => l.slice(6))
        .join("\n");
      if (!ev) continue;
      let data = {};
      try {
        data = JSON.parse(dataLine || "{}");
      } catch (_) {
        data = { text: dataLine };
      }
      onEvent(ev, data);
    }
  }
}

async function refresh(force = false) {
  if (state.refreshing) return;
  state.refreshing = true;
  $("btn-refresh").disabled = true;
  showProgress(1, force ? "强制重读存档…" : "检查存档…");
  try {
    const qs = new URLSearchParams({ force: force ? "true" : "false" });
    const res = await fetch("/api/refresh/stream?" + qs.toString());
    if (!res.ok) throw new Error(await res.text());
    let donePayload = null;
    let errMsg = null;
    await readSSE(res, (ev, data) => {
      if (ev === "progress") showProgress(data.pct ?? 0, data.label);
      else if (ev === "done") donePayload = data;
      else if (ev === "error") errMsg = data.message || "刷新失败";
    });
    if (errMsg) throw new Error(errMsg);
    if (donePayload) {
      applyPayload(donePayload);
      if (donePayload.reloaded) toast("存档已重新读取");
    }
  } catch (err) {
    toast("刷新失败：" + err.message);
  } finally {
    hideProgress();
    state.refreshing = false;
    $("btn-refresh").disabled = false;
  }
}

async function poll() {
  if (!state.auto || state.busy || state.refreshing) return;
  try {
    const st = await api("/api/status");
    if (st.stale) {
      toast("检测到存档变化，正在刷新…");
      await refresh(false);
    }
  } catch (_) {
    /* ignore poll errors */
  }
}

function schedulePoll() {
  clearInterval(state.timer);
  const sec = Number($("refresh-sec").value || 20);
  state.timer = setInterval(poll, sec * 1000);
}

function addMsg(role, text, extra = "") {
  const box = $("messages");
  const el = document.createElement("div");
  el.className = `msg ${role}`;
  el.innerHTML = extra + esc(text);
  box.appendChild(el);
  box.scrollTop = box.scrollHeight;
  return el;
}

async function sendChat(text) {
  if (!text.trim() || state.busy) return;
  state.busy = true;
  $("btn-send").disabled = true;
  state.messages.push({ role: "user", content: text.trim() });
  addMsg("user", text.trim());
  const asst = addMsg("assistant", "");
  let acc = "";
  try {
    const res = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ messages: state.messages }),
    });
    if (!res.ok) throw new Error(await res.text());
    const reader = res.body.getReader();
    const dec = new TextDecoder();
    let buf = "";
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buf += dec.decode(value, { stream: true });
      const chunks = buf.split("\n\n");
      buf = chunks.pop() || "";
      for (const chunk of chunks) {
        const ev = chunk.match(/^event: (.+)$/m)?.[1];
        const dataLine = chunk.split("\n").filter((l) => l.startsWith("data: ")).map((l) => l.slice(6)).join("\n");
        if (!ev) continue;
        let data = {};
        try { data = JSON.parse(dataLine || "{}"); } catch (_) { data = { text: dataLine }; }
        if (ev === "token") {
          acc += data.text || "";
          asst.textContent = acc;
          $("messages").scrollTop = $("messages").scrollHeight;
        } else if (ev === "tool") {
          const chip = document.createElement("span");
          chip.className = "toolchip";
          chip.textContent = data.status === "running" ? `调用 ${data.name}…` : `${data.name} 完成`;
          asst.prepend(chip);
        } else if (ev === "actions") {
          state.board = data;
          renderBoard();
        } else if (ev === "error") {
          acc += (acc ? "\n" : "") + "错误：" + (data.message || dataLine);
          asst.textContent = acc;
        } else if (ev === "done" && !acc && data.text) {
          acc = data.text;
          asst.textContent = acc;
        }
      }
    }
    if (acc) state.messages.push({ role: "assistant", content: acc });
  } catch (err) {
    asst.textContent = "请求失败：" + err.message;
  } finally {
    state.busy = false;
    $("btn-send").disabled = false;
  }
}

async function loadSettings() {
  const s = await api("/api/settings");
  $("cfg-base").value = s.base_url || "";
  $("cfg-model").value = s.model || "kimi-k3";
  $("cfg-key").placeholder = s.api_key_set ? `已保存 ${s.api_key_masked}` : "尚未设置";
  $("refresh-sec").value = String(s.auto_refresh_sec || 20);
}

async function saveSettings(ev) {
  ev.preventDefault();
  const patch = {
    base_url: $("cfg-base").value,
    model: $("cfg-model").value,
    auto_refresh_sec: Number($("refresh-sec").value),
  };
  const key = $("cfg-key").value.trim();
  if (key) patch.api_key = key;
  await api("/api/settings", { method: "PUT", body: JSON.stringify(patch) });
  $("settings").close();
  toast("设置已保存");
  schedulePoll();
}

async function loadModels() {
  try {
    const data = await api("/api/models");
    $("model-list").innerHTML = (data.models || []).map((m) => `<option value="${esc(m)}"></option>`).join("");
    toast(`拉到 ${data.models.length} 个模型`);
  } catch (err) {
    toast("拉取失败：" + err.message);
  }
}

function bind() {
  $("btn-refresh").onclick = () => refresh(true);
  $("auto-refresh").onchange = (e) => {
    state.auto = e.target.checked;
    schedulePoll();
  };
  $("refresh-sec").onchange = schedulePoll;
  $("btn-settings").onclick = () => $("settings").showModal();
  $("btn-close-settings").onclick = () => $("settings").close();
  $("btn-save-settings").onclick = saveSettings;
  $("btn-load-models").onclick = loadModels;
  $("composer").onsubmit = (e) => {
    e.preventDefault();
    const t = $("input").value;
    $("input").value = "";
    sendChat(t);
  };
  $("input").addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      $("composer").requestSubmit();
    }
  });
  document.querySelectorAll("#starters button").forEach((b) => {
    b.onclick = () => sendChat(b.dataset.q);
  });
  document.querySelectorAll("#prio-filters button").forEach((b) => {
    b.onclick = () => {
      document.querySelectorAll("#prio-filters button").forEach((x) => x.classList.remove("on"));
      b.classList.add("on");
      state.prio = b.dataset.prio;
      renderBoard();
    };
  });
}

async function boot() {
  bind();
  await loadSettings().catch(() => {});
  showProgress(1, "载入存档…");
  await refresh(false);
  if (!state.dashboard) $("save-line").textContent = "尚未读到存档";
  schedulePoll();
}

boot();
