/* No credentials or generated HTML are inserted into the page. */
"use strict";
const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => [...document.querySelectorAll(selector)];
const phases = [
  ["rules", "读取规则", "READ", "▤"], ["ideas", "生成选题", "IDEATE", "✧"],
  ["build", "生成代码", "BUILD", "⌘"], ["test", "测试修复", "TEST", "✓"],
  ["package", "材料打包", "PACKAGE", "▣"]
];
const labels = { ready: "已完成", running: "运行中", queued: "排队中", blocked: "待处理", paused: "已暂停", interrupted: "运行中断", submitted: "已提交", unknown: "提交状态未知", preview: "已预览", sending: "正在提交" };
const store = { token: null, runs: [], selected: null, detail: null, tab: "result", health: {}, online: false, busy: false, refreshing: false };
const esc = (value) => String(value ?? "").replace(/[&<>"']/g, (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[char]));
const date = (value) => value && Number.isFinite(Date.parse(value)) ? new Date(value).toLocaleString("zh-CN", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", hour12: false }) : "—";
const badge = (status) => `<span class="badge ${esc(Object.hasOwn(labels, status) ? status : "neutral")}">${esc(labels[status] || status || "未开始")}</span>`;
function safeLink(value) { try { const url = new URL(value); return ["http:", "https:"].includes(url.protocol) ? url.href : ""; } catch { return ""; } }
function source(value) { const url = safeLink(value); return url ? `<a class="source-link" href="${esc(url)}" target="_blank" rel="noopener noreferrer">↗ ${esc(url)}</a>` : `<span class="muted">无可用来源</span>`; }
function empty(title, subtitle, symbol = "✧") { return `<div class="empty-state"><div class="empty-symbol">${symbol}</div><h3>${esc(title)}</h3><p>${esc(subtitle)}</p></div>`; }
function fileUrl(name) { return `/api/runs/${encodeURIComponent(store.selected)}/files/${encodeURIComponent(name)}`; }
function toast(message) { $("#toast").textContent = message; $("#toast").hidden = false; clearTimeout(toast.timer); toast.timer = setTimeout(() => { $("#toast").hidden = true; }, 4500); }

async function api(path, payload) {
  const response = await fetch(path, {
    method: payload === undefined ? "GET" : "POST",
    headers: payload === undefined ? {} : { "Content-Type": "application/json", "X-Autolex-Token": store.token || "" },
    body: payload === undefined ? undefined : JSON.stringify(payload),
    signal: AbortSignal.timeout(12000), cache: "no-store"
  });
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || `请求失败 (${response.status})`);
  return data;
}

function renderHealth() {
  const names = [["lexmount", "Lexmount 云平台", "L"], ["model", "模型服务", "✳"], ["docker", "Docker 执行器", "▧"]];
  const html = names.map(([key, name, icon]) => `<div class="health-item"><span class="health-icon">${icon}</span><span>${name}</span><span class="${store.health[key] ? "ok" : ""}">${!store.online ? "未连接" : store.health[key] ? "已配置" : "待配置"}</span></div>`).join("");
  $("#health-list").innerHTML = html;
  $("#environment-checks").innerHTML = html;
  $("#connection").classList.toggle("online", store.online);
  $("#connection").innerHTML = `<i></i>${store.online ? "本地服务已连接" : "服务未连接"}`;
  $("#offline-banner").hidden = store.online;
  updateButtons();
}

function updateButtons() {
  const active = store.runs.some((run) => run.state.active);
  $("#quick-demo").disabled = !store.online || store.busy || active;
  $("#new-task").disabled = !store.online || store.busy || active;
  $("#submit-task").disabled = !store.online || store.busy || active;
  $("#resume-task").disabled = !store.online || store.busy || active;
  $("#revise-task").disabled = !store.online || store.busy || active;
  $("#release-task").disabled = !store.online || store.busy || active;
}

async function health() {
  try {
    const response = await api("/api/health");
    store.token = response.token;
    store.health = response.configuration;
    store.online = true;
  } catch { store.online = false; }
  renderHealth();
}

function renderHistory() {
  $("#run-count").textContent = store.runs.length;
  $("#stat-total").textContent = store.runs.length;
  $("#stat-ready").textContent = store.runs.filter((run) => run.state.status === "ready").length;
  $("#stat-active").textContent = store.runs.filter((run) => run.state.active).length;
  $("#history-body").innerHTML = store.runs.length ? store.runs.map(({ state, summary }) => `<tr>
    <td>${esc(summary?.title || state.id)}<span class="history-url">${esc(state.id)}${summary?.parent ? " · 来自 " + esc(summary.parent) : ""}</span></td>
    <td><span class="badge ${state.demo ? "demo" : "live"}">${state.demo ? "DEMO" : "LIVE"}</span></td>
    <td>${(state.completed || []).length} / 5</td><td>${badge(state.status)}</td><td>${date(state.created_at)}</td>
    <td><button class="history-view" data-run="${esc(state.id)}" aria-label="查看任务 ${esc(state.id)}">查看 ↗</button></td></tr>`).join("") : '<tr><td colspan="6" class="history-empty">还没有运行记录。第一个任务，就从一次小实验开始。</td></tr>';
  updateButtons();
}

function renderPipeline() {
  const detail = store.detail;
  const state = detail?.state || {};
  const completed = state.completed || [];
  $("#pipeline").innerHTML = phases.map(([key, title, en, icon]) => {
    const done = completed.includes(key);
    const current = state.stage === key && !done;
    const style = done ? "done" : current ? (state.status === "blocked" ? "failed" : "current") : "";
    const sub = done ? "已完成" : current ? (state.active ? "进行中" : "待继续") : en;
    return `<div class="stage ${style}"><span class="stage-symbol">${done ? "✓" : icon}</span><span class="stage-name">${title}</span><span class="stage-sub">${sub}</span></div>`;
  }).join("");
  $("#run-title").textContent = detail?.spec?.selected?.title || (state.id ? state.id : "下一个想法，从这里开始");
  $("#run-url").textContent = state.url || "创建一个任务，或者先试试离线演示。";
  $("#run-status").className = `badge ${Object.hasOwn(labels, state.status) ? state.status : "neutral"}`;
  $("#run-status").textContent = labels[state.status] || "未开始";
  $("#mode-badge").className = `badge ${state.id ? (state.demo ? "demo" : "live") : "neutral"}`;
  $("#mode-badge").textContent = state.id ? (state.demo ? "DEMO / 离线演示" : "LIVE / 真实运行") : "等待任务";
  $("#run-caption").textContent = state.id ? (state.demo ? "固定演示样例 · 无真实云调用" : "真实运行 · 结果与来源保存在本地") : "五个阶段，一份完整的成果。";
  $("#run-time").textContent = state.updated_at ? `更新于 ${date(state.updated_at)}` : "—";
  $("#run-error").hidden = !state.error;
  $("#run-error").textContent = state.error ? `任务暂停：${state.error}` : "";
  $("#resume-task").hidden = !state.id || state.active || state.status === "ready" || state.status === "queued";
  const overview = detail?.summary;
  $("#run-overview").hidden = !state.id;
  const operation = ({RULES:"模型正在提取规则",IDEAS:"模型正在生成选题",CODE:"模型正在生成或修复代码",REVIEW:"模型正在检查内容"})[state.operation];
  $("#run-overview").innerHTML = state.id ? `<div class="outcome-metrics"><div><small>成果</small><strong>${overview?.sources ? `${overview.sources} 个来源 · ${overview.points} 条依据` : "等待生成"}</strong></div><div><small>${state.demo ? "演示模型调用" : "模型调用"}</small><strong>${Number(state.model_calls || 0)}${state.model_budget ? " / " + Number(state.model_budget) : ""} 次</strong></div><div><small>执行记录（含恢复前）</small><strong>${Number(overview?.attempts || 0)} 轮</strong></div></div><p>${esc(operation || overview?.next_step || "阶段进展会自动更新。")}</p>${overview?.parent ? `<small>本版本来自 ${esc(overview.parent)}</small>` : ""}` : "";
  $("#open-preview").hidden = !detail?.artifacts?.includes("index.html");
  $("#open-preview").href = state.id ? `/api/runs/${encodeURIComponent(state.id)}/preview` : "#";
  $("#revise-task").hidden = !state.id || state.active || !completed.includes("build");
  const released = detail?.release;
  $("#release-task").hidden = !state.id || state.demo || state.status !== "ready" || !detail?.release_configured || ["submitted","publishing","submitting","unknown"].includes(released?.status);
  $("#release-summary").hidden = !state.id || state.demo;
  $("#release-summary").innerHTML = released?.status === "submitted" ? `这件作品已提交 · 收件编号 ${esc(released.receipt?.id || "")}<br>${source(released.url)}${released.passcode ? ` · 访问码 ${esc(released.passcode)}` : ""}` : released ? `发布进度：${esc(({published:"材料已发布，继续核验并投稿",publishing:"正在发布材料",submitting:"正在提交作品",unknown:"结果待核对，请勿重复发送"})[released.status] || released.status)}` : "发布会使用当前作品的标题、成果和独立链接，并保存它自己的投稿回执。";
  if (detail?.release_error) $("#release-summary").innerHTML += `<br>发布待处理：${esc(detail.release_error)}`;
  const events = completed.map((key) => `<div class="activity"><b>${esc(phases.find((phase) => phase[0] === key)?.[1] || key)}</b><small>已完成并保存产物</small></div>`);
  if (state.error) events.push(`<div class="activity"><b>等待处理</b><small>${esc(state.error)}</small></div>`);
  if (state.active) events.push(`<div class="activity"><b>Agent 正在执行</b><small>页面每 2 秒刷新任务状态</small></div>`);
  $("#activity-list").innerHTML = events.length ? events.join("") : '<p class="muted">运行后，这里会留下过程。</p>';
  renderOutput();
  updateButtons();
}

function renderOutput() {
  const detail = store.detail;
  const area = $("#result-content");
  area.setAttribute("aria-labelledby", `tab-${store.tab}`);
  if (!detail) { area.innerHTML = empty("你的下一个作品，还在路上", "点击「运行离线演示」，先体验一次完整流程。"); delete area.dataset.renderKey; return; }
  const banner = detail.state.demo ? '<div class="result-banner">◌　离线固定样例，仅用于体验流程。</div>' : "";
  let html = "";
  if (store.tab === "result") {
    const items = detail.output?.items;
    html = items?.length ? banner + items.map((item, index) => `<article class="output-item"><div class="section-kicker">SOURCE ${String(index + 1).padStart(2, "0")}</div><h3>${esc(item.title)}</h3><p>${esc(item.summary)}</p>${Array.isArray(item.points) ? `<ol class="evidence-points">${item.points.map(point => `<li><p>${esc(point.summary)}</p><blockquote>${esc(point.quote)}</blockquote><small>${esc(point.id)}</small></li>`).join("")}</ol>` : ""}${Array.isArray(item.not_mentioned) && item.not_mentioned.length ? `<p>本页未提及：${esc(item.not_mentioned.join("、"))}</p>` : ""}${source(item.url)}</article>`).join("") : empty("成果正在路上", "运行通过测试后，这里会展示带来源的整理结果。", "▤");
    if (Array.isArray(detail.output?.conclusions) && detail.output.conclusions.length) html += `<article class="output-item"><h3>对比结论</h3>${detail.output.conclusions.map(item => `<p>${esc(item.text)} <small>依据：${esc((item.point_refs || []).join(", "))}</small></p>`).join("")}</article>`;
  } else if (store.tab === "ideas") {
    const ideas = detail.ideas?.ideas;
    html = ideas?.length ? banner + ideas.map((idea) => `<article class="output-item"><div class="idea-heading"><h3>${esc(idea.title)} ${idea.title === detail.spec?.selected?.title ? '<span class="badge demo">已选中</span>' : ""}</h3><span class="score">${esc(idea.score)} 分</span></div><p>${esc(idea.description)}</p><div class="idea-meta">验收：${esc(idea.acceptance)}</div></article>`).join("") + '<p class="small-footnote">分数用于内部选题排序，不代表官方评分。</p>' : empty("好想法需要一点时间", "选题阶段完成后，会展示候选方向和最终选择。", "✧");
  } else if (store.tab === "code") {
    html = detail.code ? `<div class="code-toolbar"><span>main.py · Python · ${detail.code.split("\n").length} 行</span><button id="copy-code" class="text-button">复制代码 ⧉</button></div><pre class="code-block"><code>${detail.code.split("\n").map((line, index) => `<span class="code-line"><span class="line-number" aria-hidden="true">${index + 1}</span>${esc(line)}</span>`).join("")}</code></pre>` : empty("还没有生成代码", "构建阶段会把选题变成可以运行的 Python 程序。", "⌘");
  } else if (store.tab === "tests") {
    const tests = detail.tests;
    const histories = detail.test_history || [];
    html = tests ? `<div class="test-heading"><span>${tests.attempts.length} 次执行 · ${tests.passed ? "最终通过" : "待修复"}</span>${badge(tests.passed ? "ready" : "blocked")}</div>${tests.attempts.map((attempt) => `<details class="test-attempt" ${attempt.failures.length ? "open" : ""}><summary><span>第 ${attempt.attempt} 轮 · 退出码 ${attempt.returncode}</span><span>${attempt.failures.length ? "查看问题 ↘" : "查看日志 ↘"}</span></summary><pre>${esc([...attempt.failures, attempt.log || "程序没有输出日志。"].join("\n"))}</pre></details>`).join("")}<p class="small-footnote">自动检查运行结果、输出格式与来源覆盖；摘要语义准确性仍需核对。</p>` : empty("测试还没开始", "每轮执行和修复结果都会保存在这里。", "✓");
    if (histories.length) html += `<details class="test-attempt"><summary>恢复前的 ${histories.length} 次测试记录</summary>${histories.map((record,index) => `<h3>第 ${index+1} 次执行批次</h3><pre>${esc(record.attempts.map(a => `第 ${a.attempt} 轮：${a.failures.join("；") || "通过"}`).join("\n"))}</pre>`).join("")}</details>`;
    if (detail.quality) html += `<div class="output-item"><h3>输入变化检查 · ${detail.quality.passed ? "通过" : "未通过"}</h3>${detail.quality.checks.map(check => `<p>${check.passed ? "✓" : "✕"} ${esc(({equivalent_whitespace:"来源空白格式变化",duplicate_source:"重复来源拒绝",repeat:"原样复跑",reverse_pages:"调换页面顺序",missing_page:"移除一页正文",empty_evidence:"清空全部正文",irrelevant_evidence:"正文替换成无关内容"})[check.name] || check.name.replace(/^missing_source_(\d+)$/, "移除来源 $1").replace(/^empty_source_(\d+)$/, "清空来源 $1"))}</p>`).join("")}<p class="small-footnote">复跑、缺失证据与顺序变化检查；视觉检查另行记录。</p></div>`;
    if (detail.visual) html += `<div class="output-item"><h3>自动视觉验收 · ${detail.visual.passed ? "通过" : "未通过"}</h3><p>截图评审 ${Number(detail.visual.attempts)} 轮 · ${esc(detail.visual.model)}</p>${(detail.visual.last?.review?.issues || []).map(issue => `<p>${esc(issue.severity)} · ${esc(issue.problem)}</p>`).join("")}<p class="small-footnote">模型检查桌面、手机及代码目录截图；不代表所有页面区域均已覆盖。</p></div>`;
    if (detail.citations) html += `<div class="output-item"><h3>引用支撑检查 · ${detail.citations.passed ? "通过" : "未通过"}</h3>${detail.citations.checks.map(check => `<p>${check.passed ? "✓" : "✕"} ${esc(check.id || `${check.kind === "item_checks" ? "页面摘要" : "结论"} ${check.index + 1}`)}<br>${esc(check.reason)}</p>`).join("")}<p class="small-footnote">模型只核对摘录能否支撑对应说法；仍需结合完整资料复核。</p></div>`;
    if (detail.review) html += `<div class="output-item"><h3>模型辅助验收 · ${detail.review.passed ? "通过" : "未通过"}</h3>${detail.review.checks.map(check => `<p>${check.passed ? "✓" : "✕"} ${esc(check.requirement)}<br>${esc(check.reason)}</p>`).join("")}</div>`;
  } else if (store.tab === "materials") {
    html = detail.report ? `${banner}<div class="test-heading"><span>作品材料已生成</span>${badge(detail.submission?.status || "ready")}</div><div class="download-row">${["submission.zip", "index.html", "submission.md", "output.json", "tests.json", "quality.json", "citations.json", "visual-review.json", "visual-evidence.zip"].filter((name) => detail.artifacts.includes(name)).map((name) => `<a class="button ${name.endsWith("zip") ? "primary" : "subtle"}" href="${fileUrl(name)}" download>${name.endsWith("zip") ? "↓ 下载作品包" : "↓ " + name}</a>`).join("")}</div><div class="report-text">${esc(detail.report)}</div><p class="submission-note">${detail.state.demo ? "演示产物不能进入真实投稿。" : "使用上方“发布并提交这件作品”可自动上传当前成果、核验访问并投稿；也可使用 CLI 的 release 命令。"}</p>${detail.submission ? `<pre class="report-text">${esc(JSON.stringify(detail.submission, null, 2))}</pre>` : '<p class="submission-note">尚无提交回执。</p>'}` : empty("最后一步，把过程变成作品", "打包完成后，可下载说明、运行结果和测试证据。", "▣");
  }
  // Preserve scrolling and open log panels on background polls when nothing changed.
  if (area.dataset.renderKey !== html) { area.innerHTML = html; area.dataset.renderKey = html; }
}

async function refresh() {
  if (store.refreshing) return;
  store.refreshing = true;
  try {
    if (!store.online) { await health(); if (!store.online) return; }
    store.runs = (await api("/api/runs")).runs;
    renderHistory();
    if (!store.selected && store.runs.length) store.selected = (store.runs.find((run) => run.state.active) || store.runs.find((run) => run.state.status === "ready") || store.runs[0]).state.id;
    const requested = store.selected;
    if (requested) {
      const result = await api(`/api/runs/${encodeURIComponent(requested)}`);
      if (store.selected !== requested) return;
      store.detail = result;
    }
    renderPipeline();
  } catch { store.online = false; renderHealth(); }
  finally { store.refreshing = false; }
}

async function launch(payload) {
  store.busy = true;
  updateButtons();
  try {
    const result = await api("/api/runs", payload);
    store.selected = result.id;
    store.detail = null;
    $("#task-dialog").close();
    toast(payload.mode === "demo" ? "离线演示已启动，来看看 Agent 的工作过程。" : "任务已启动，运行结果会自动更新。");
    navigate("overview");
    await refresh();
  } finally { store.busy = false; updateButtons(); }
}

function navigate(target) {
  $$("[data-nav]").forEach((button) => button.classList.toggle("active", button.dataset.nav === target));
  $("#breadcrumb").textContent = { overview: "工作台", history: "运行记录", environment: "环境配置" }[target];
  $("#environment-section").hidden = target !== "environment";
  if (target === "history") $("#history-section").scrollIntoView({ behavior: "smooth", block: "start" });
  else window.scrollTo({ top: 0, behavior: "smooth" });
}

function switchTab(tab) {
  store.tab = tab;
  $$("[data-tab]").forEach((button) => {
    const selected = button.dataset.tab === tab;
    button.setAttribute("aria-selected", String(selected));
    button.tabIndex = selected ? 0 : -1;
  });
  renderOutput();
}

document.addEventListener("click", async (event) => {
  const nav = event.target.closest("[data-nav]");
  if (nav) navigate(nav.dataset.nav);
  const tab = event.target.closest("[data-tab]");
  if (tab) switchTab(tab.dataset.tab);
  const run = event.target.closest("[data-run]");
  if (run) {
    store.selected = run.dataset.run;
    store.detail = null;
    renderPipeline();
    navigate("overview");
    await refresh();
  }
  if (event.target.closest("#copy-code")) {
    try { await navigator.clipboard.writeText(store.detail.code); toast("代码已复制。"); }
    catch { toast("浏览器未允许复制，请在代码区域手动选择。 "); }
  }
});
$(".tabs").addEventListener("keydown", (event) => {
  if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
  const buttons = $$("[data-tab]");
  const current = buttons.findIndex((button) => button.dataset.tab === store.tab);
  const index = event.key === "Home" ? 0 : event.key === "End" ? buttons.length - 1 : (current + (event.key === "ArrowRight" ? 1 : -1) + buttons.length) % buttons.length;
  event.preventDefault(); switchTab(buttons[index].dataset.tab); buttons[index].focus();
});
function openTaskDialog(revision = false) {
  $("#form-error").hidden = true;
  $("#revision-of").value = revision ? store.selected : "";
  $("#revision-fields").hidden = !revision;
  $("#task-feedback").required = revision;
  $("#task-feedback").value = "";
  $("#auto-release").checked = false;
  $("#task-url").readOnly = revision;
  $("#task-brief").readOnly = revision;
  $$("input[name=mode]").forEach(input => {
    input.disabled = revision;
    if (revision) input.checked = input.value === (store.detail.state.demo ? "demo" : "live");
  });
  if (revision) {
    $("#task-url").value = store.detail.state.url;
    $("#task-brief").value = store.detail.state.brief || "";
  }
  updateModeHelp(revision ? (store.detail.state.demo ? "demo" : "live") : $("input[name=mode]:checked").value);
  $("#dialog-title").textContent = revision ? "保留这个作品，再改好一点。" : "一个链接，一次新尝试。";
  $("#submit-task").textContent = revision ? "创建新版本 ↗" : "启动流水线 ↗";
  $("#task-dialog").showModal();
}
$("#new-task").addEventListener("click", () => openTaskDialog());
$("#revise-task").addEventListener("click", () => openTaskDialog(true));
$("#close-dialog").addEventListener("click", () => $("#task-dialog").close());
$("#task-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  $("#form-error").hidden = true;
  const data = Object.fromEntries(new FormData(event.currentTarget));
  data.repairs = Number(data.repairs);
  data.auto_release = data.auto_release === "on";
  if (data.revision_of) data.mode = store.detail.state.demo ? "demo" : "live";
  try { await launch(data); }
  catch (error) { $("#form-error").textContent = error.message; $("#form-error").hidden = false; }
});
function updateModeHelp(mode) {
  $("#auto-release").disabled = mode === "demo";
  if (mode === "demo") $("#auto-release").checked = false;
  $("#mode-help").textContent = mode === "demo" ? "演示不会访问填写的网址，结果将标注为 DEMO。" : "需在服务端配置 API 和 Docker。网页不会读取或保存你的密钥。";
}
$$("input[name=mode]").forEach((input) => input.addEventListener("change", () => updateModeHelp($("input[name=mode]:checked").value)));
$("#quick-demo").addEventListener("click", async () => {
  try { await launch({ url: "https://browser.lexmount.cn/events/real-task-challenge", mode: "demo", until: "package", repairs: 3 }); }
  catch (error) { toast(error.message); }
});
$("#resume-task").addEventListener("click", async () => {
  store.busy = true; updateButtons();
  try { await api(`/api/runs/${encodeURIComponent(store.selected)}/resume`, { until: "package", repairs: 3 }); toast("继续执行未完成阶段。"); await refresh(); }
  catch (error) { toast(error.message); }
  finally { store.busy = false; updateButtons(); }
});
$("#release-task").addEventListener("click", async () => {
  store.busy = true; updateButtons();
  try { await api(`/api/runs/${encodeURIComponent(store.selected)}/release`, {}); toast("正在发布并提交当前作品，进度会自动更新。"); await refresh(); }
  catch (error) { toast(error.message); }
  finally { store.busy = false; updateButtons(); }
});
$("#show-environment").addEventListener("click", () => navigate("environment"));
$("#refresh-health").addEventListener("click", health);
$("#refresh-run").addEventListener("click", refresh);
$("#refresh-history").addEventListener("click", refresh);
document.addEventListener("visibilitychange", () => { if (!document.hidden) refresh(); });
renderPipeline(); renderHistory();
health().then(refresh);
setInterval(() => { if (!document.hidden && !$("#task-dialog").open) refresh(); }, 2000);
