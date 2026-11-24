// The survey check page: read the files, assign columns, run web/engine.js, show and export the results.
import { createI18n } from "./design/i18n.js";
import { readTable, download } from "./design/table.js";
import { writeXlsx } from "./design/xlsx.js";
import { analyse, MIN_GROUP } from "./engine.js";

const T = {
  en: {
    brand: "Engagement survey", eyebrow: "Survey check · from your own survey export",
    title: "What does your survey say, and what moves it?",
    lead: "Load the answers, one row per person. You get each dimension's favourable score with an honest interval, the eNPS, what drives engagement, and results by team, with every group under five respondents hidden.",
    privacy: "Your file stays on this computer: it is read by this page and sent nowhere. Go offline after the page has loaded and it still works.",
    step1: "Your survey answers", step1sub: "An Excel or CSV export with one row per person: a team or department column and the questions scored 1 to 5. A questionnaire file (item, dimension, type) is optional and saves you naming the dimensions.",
    dropA: "Answers", dropQ: "Questionnaire (optional)", dropHint: ".xlsx or .csv", sample: "Try it on the example: 3,800 invitees",
    step2: "Check the columns", rGroup: "Team or department *", rResp: "Responded (1/0), if invitees are listed", rEnps: "eNPS question (0-10)",
    rOutcome: "Which dimension is engagement? *", itemsSub: "Questions scored 1 to 5, and the dimension each belongs to. Clear a name to leave a question out.",
    none: "— none —", col: "Column", dim: "Dimension", run: "Show the results",
    errRead: "The file could not be read: {msg}", errGroup: "Choose the team or department column.", errOutcome: "Choose which dimension is engagement.",
    errItems: "No questions scored 1 to 5 were found.", errDims: "Engagement needs at least one other dimension next to it.",
    kResp: "Response rate", kN: "Respondents", kEng: "Engagement", kEnps: "eNPS",
    dimTitle: "Dimension scores", dimSub: "The share of each person's answers that are favourable (4 or 5), averaged over people. The interval resamples whole teams, because people in a team answer alike.",
    dDim: "Dimension", dScore: "Favourable", dCi: "95% interval", dN: "People",
    drvTitle: "What drives engagement", drvSub: "{n} people who answered every dimension; together the dimensions explain {r2} of the variation in engagement.",
    drvNone: "Not run: it needs at least 50 people who answered every dimension, in five or more teams.",
    drvNote: "Relative weights (Johnson's method): each dimension's share of the variation in engagement the dimensions explain together. Dimensions move together, so this is the honest way to rank them; it shows where to look, not what causes what.",
    wDim: "Dimension", wShare: "Share of explained variation",
    grpTitle: "By team", grpSub: "Favourable scores per team. Teams under five respondents are never shown, not even their number of respondents.",
    gTeam: "Team", gN: "Respondents", hidden: "fewer than {n}: not shown", engagement: "Engagement",
    download: "Download the results (Excel)", print: "Print",
    foot: "The calculations are the same as the <a href=\"https://github.com/D0M3N1C0X/engagement-survey-analytics\">read-out's</a>, checked against its Python on every change. Built by Domenico Perroni.",
    xSummary: "Summary", xDims: "Dimensions", xDrivers: "Drivers", xTeams: "Teams", xMeasure: "Measure", xValue: "Value", fileOut: "survey-check",
  },
  it: {
    brand: "Sondaggio di engagement", eyebrow: "Analisi del sondaggio · dall'export del tuo sondaggio",
    title: "Cosa dice il tuo sondaggio, e cosa lo muove?",
    lead: "Carica le risposte, una riga per persona. Ottieni il punteggio favorevole di ogni dimensione con un intervallo onesto, l'eNPS, cosa guida l'engagement e i risultati per team, con ogni gruppo sotto i cinque rispondenti nascosto.",
    privacy: "Il file resta su questo computer: lo legge questa pagina e non va da nessuna parte. Scollegati dalla rete dopo aver aperto la pagina: funziona lo stesso.",
    step1: "Le risposte al sondaggio", step1sub: "Un export Excel o CSV con una riga per persona: una colonna del team o reparto e le domande da 1 a 5. Il file del questionario (domanda, dimensione, tipo) è facoltativo e ti evita di dare i nomi alle dimensioni.",
    dropA: "Risposte", dropQ: "Questionario (facoltativo)", dropHint: ".xlsx o .csv", sample: "Prova con l'esempio: 3.800 invitati",
    step2: "Controlla le colonne", rGroup: "Team o reparto *", rResp: "Ha risposto (1/0), se ci sono anche i non rispondenti", rEnps: "Domanda eNPS (0-10)",
    rOutcome: "Quale dimensione è l'engagement? *", itemsSub: "Le domande da 1 a 5 e la dimensione di ciascuna. Cancella il nome per escludere una domanda.",
    none: "— nessuna —", col: "Colonna", dim: "Dimensione", run: "Mostra i risultati",
    errRead: "Il file non si legge: {msg}", errGroup: "Scegli la colonna del team o reparto.", errOutcome: "Scegli quale dimensione è l'engagement.",
    errItems: "Non ho trovato domande con punteggi da 1 a 5.", errDims: "Accanto all'engagement serve almeno un'altra dimensione.",
    kResp: "Tasso di risposta", kN: "Rispondenti", kEng: "Engagement", kEnps: "eNPS",
    dimTitle: "Punteggi per dimensione", dimSub: "La quota di risposte favorevoli (4 o 5) di ogni persona, mediata sulle persone. L'intervallo ricampiona team interi, perché chi lavora insieme risponde in modo simile.",
    dDim: "Dimensione", dScore: "Favorevole", dCi: "Intervallo 95%", dN: "Persone",
    drvTitle: "Cosa guida l'engagement", drvSub: "{n} persone che hanno risposto a tutte le dimensioni; insieme spiegano il {r2} della variazione dell'engagement.",
    drvNone: "Non calcolato: servono almeno 50 persone che abbiano risposto a tutte le dimensioni, in cinque o più team.",
    drvNote: "Pesi relativi (metodo di Johnson): la quota di variazione dell'engagement spiegata da ciascuna dimensione. Le dimensioni si muovono insieme, quindi è il modo onesto di ordinarle; dice dove guardare, non cosa causa cosa.",
    wDim: "Dimensione", wShare: "Quota della variazione spiegata",
    grpTitle: "Per team", grpSub: "Punteggi favorevoli per team. I team sotto i cinque rispondenti non sono mai mostrati, nemmeno il numero di rispondenti.",
    gTeam: "Team", gN: "Rispondenti", hidden: "meno di {n}: non mostrato", engagement: "Engagement",
    download: "Scarica i risultati (Excel)", print: "Stampa",
    foot: "I calcoli sono gli stessi del <a href=\"https://github.com/D0M3N1C0X/engagement-survey-analytics\">rapporto</a>, verificati contro il suo Python a ogni modifica. Realizzato da Domenico Perroni.",
    xSummary: "Sintesi", xDims: "Dimensioni", xDrivers: "Fattori", xTeams: "Team", xMeasure: "Misura", xValue: "Valore", fileOut: "analisi-sondaggio",
  },
};
const i18n = createI18n(T, "en");
const $ = (id) => document.getElementById(id);
const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
let answers = null, questionnaire = null, itemDims = {}, result = null, dims = [], outcomeName = null;
const msg = (id, t) => { const el = $(id); el.textContent = t || ""; el.classList.toggle("is-shown", !!t); };
const still = matchMedia("(prefers-reduced-motion: reduce)").matches;
const reveal = (id) => $(id).scrollIntoView({ behavior: still ? "auto" : "smooth", block: "start" });

const isScale = (h) => {
  let n = 0;
  for (const r of answers.rows.slice(0, 500)) {
    const v = String(r[h] ?? "").trim();
    if (!v) continue;
    if (!/^[1-5]$/.test(v)) return false;
    n++;
  }
  return n > 0;
};
const prefix = (h) => (String(h).match(/^([A-Za-z]+)[_\s.-]?\d/) || [null, null])[1];
const guess = (headers, names) => headers.find((h) => names.includes(h.toLowerCase().replace(/[^a-z]/g, ""))) || "";

function setupColumns() {
  const headers = answers.headers;
  const items = headers.filter(isScale);
  itemDims = {};
  const qMap = {};
  if (questionnaire) for (const r of questionnaire.rows) {
    const id = String(r.item_id ?? r.item ?? r.id ?? "").trim(), dim = String(r.dimension ?? r.dimensione ?? "").trim();
    if (id && dim) qMap[id] = dim;
  }
  for (const h of items) itemDims[h] = qMap[h] || prefix(h) || h;
  const opts = (sel) => `<option value="">${esc(i18n.t("none"))}</option>` + headers.map((h) => `<option${h === sel ? " selected" : ""}>${esc(h)}</option>`).join("");
  $("r-group").innerHTML = opts(guess(headers, ["teamid", "team", "department", "reparto", "dept", "group"]));
  $("r-resp").innerHTML = opts(guess(headers, ["responded", "risposto", "response"]));
  $("r-enps").innerHTML = opts(guess(headers, ["enps", "nps"]));
  $("tab-items").innerHTML = `<thead><tr><th>${i18n.t("col")}</th><th>${i18n.t("dim")}</th></tr></thead><tbody>` +
    items.map((h) => `<tr><td>${esc(h)}</td><td><input data-item="${esc(h)}" value="${esc(itemDims[h])}" list="dimlist"></td></tr>`).join("") + "</tbody>";
  $("tab-items").querySelectorAll("input").forEach((el) => el.addEventListener("input", () => { itemDims[el.dataset.item] = el.value.trim(); drawOutcome(); }));
  drawOutcome();
  $("colonne").style.display = "block";
  reveal("colonne");
}
function drawOutcome() {
  const names = [...new Set(Object.values(itemDims).filter(Boolean))];
  const current = $("r-outcome").value || names.find((n) => /engag|eng$|outcome/i.test(n)) || "";
  $("r-outcome").innerHTML = `<option value="">${esc(i18n.t("none"))}</option>` + names.map((n) => `<option${n === current ? " selected" : ""}>${esc(n)}</option>`).join("");
}

async function load(file, which) {
  msg("errore", "");
  try {
    const t = await readTable(file);
    if (which === "q") { questionnaire = t; $("name-q").textContent = file.name; $("drop-q").classList.add("is-done"); if (answers) setupColumns(); return; }
    answers = t; $("name-a").textContent = file.name; $("drop-a").classList.add("is-done"); setupColumns();
  } catch (e) { msg("errore", i18n.t("errRead", { msg: e.message })); }
}

function run() {
  msg("avviso", "");
  const group = $("r-group").value, resp = $("r-resp").value, enps = $("r-enps").value;
  outcomeName = $("r-outcome").value;
  if (!group) return msg("avviso", i18n.t("errGroup"));
  if (!Object.keys(itemDims).length) return msg("avviso", i18n.t("errItems"));
  if (!outcomeName) return msg("avviso", i18n.t("errOutcome"));
  const byDim = new Map();
  for (const [item, d] of Object.entries(itemDims)) if (d) { if (!byDim.has(d)) byDim.set(d, []); byDim.get(d).push(item); }
  const outcome = byDim.get(outcomeName) || [];
  dims = [...byDim].filter(([d]) => d !== outcomeName);
  if (!dims.length) return msg("avviso", i18n.t("errDims"));
  const items = [...dims.flatMap(([, i]) => i), ...outcome];
  const rows = answers.rows.map((r) => {
    const vals = Object.fromEntries(items.map((i) => { const v = String(r[i] ?? "").trim(); return [i, /^[1-5]$/.test(v) ? Number(v) : null]; }));
    const responded = resp ? /^(1|yes|si|sì|true|y)$/i.test(String(r[resp]).trim()) : true;
    const e = enps ? String(r[enps] ?? "").trim() : "";
    return { group: String(r[group] ?? "").trim() || "—", responded, enps: /^(10|[0-9])$/.test(e) ? Number(e) : null, items: vals };
  });
  result = analyse(rows, dims, outcome);
  draw();
  $("risultati").style.display = "block";
  reveal("risultati");
}

const pct = (x, d = 0) => (x == null ? "–" : i18n.percent(x, d));
function draw() {
  const r = result;
  $("kpis").innerHTML = [[i18n.t("kResp"), pct(r.response_rate, 1)], [i18n.t("kN"), i18n.number(r.respondents)],
    [i18n.t("kEng"), pct(r.engagement.score)], [i18n.t("kEnps"), r.enps ? i18n.number(r.enps.score) : "–"]]
    .map(([k, v]) => `<div class="s-kpi"><div class="k">${esc(k)}</div><div class="v">${esc(v)}</div></div>`).join("");
  const rowsDim = [{ dimension: outcomeName, ...r.engagement }, ...r.dimensions];
  $("tab-dim").innerHTML = `<thead><tr><th>${i18n.t("dDim")}</th><th class="num">${i18n.t("dScore")}</th><th class="num">${i18n.t("dCi")}</th><th class="num">${i18n.t("dN")}</th><th></th></tr></thead><tbody>` +
    rowsDim.map((d, k) => `<tr><td>${k === 0 ? "<strong>" : ""}${esc(d.dimension)}${k === 0 ? "</strong>" : ""}</td><td class="num">${pct(d.score)}</td>
      <td class="num">${d.ci ? `${pct(d.ci[0])}–${pct(d.ci[1])}` : "–"}</td><td class="num">${i18n.number(d.people)}</td>
      <td style="width:28%"><span class="bar" style="width:${Math.round(100 * (d.score || 0))}%"></span></td></tr>`).join("") + "</tbody>";
  if (r.drivers) {
    $("drv-sub").textContent = i18n.t("drvSub", { n: i18n.number(r.drivers.n), r2: pct(r.drivers.r2) });
    $("tab-drv").innerHTML = `<thead><tr><th>${i18n.t("wDim")}</th><th class="num">${i18n.t("wShare")}</th><th></th></tr></thead><tbody>` +
      Object.entries(r.drivers.weights).sort((a, b) => b[1] - a[1]).map(([d, w]) => `<tr><td>${esc(d)}</td><td class="num">${pct(w)}</td>
        <td style="width:40%"><span class="bar" style="width:${Math.round(100 * w)}%"></span></td></tr>`).join("") + "</tbody>";
  } else { $("drv-sub").textContent = i18n.t("drvNone"); $("tab-drv").innerHTML = ""; }
  const names = ["engagement", ...dims.map(([d]) => d)];
  $("tab-grp").innerHTML = `<thead><tr><th>${i18n.t("gTeam")}</th><th class="num">${i18n.t("gN")}</th>${names.map((n) => `<th class="num">${esc(n === "engagement" ? i18n.t("engagement") : n)}</th>`).join("")}</tr></thead><tbody>` +
    r.groups.map((g) => g.respondents == null
      ? `<tr><td>${esc(g.group)}</td><td class="muted-cell" colspan="${names.length + 1}">${esc(i18n.t("hidden", { n: MIN_GROUP }))}</td></tr>`
      : `<tr><td>${esc(g.group)}</td><td class="num">${g.respondents}</td>${names.map((n) => `<td class="num">${pct(g[n])}</td>`).join("")}</tr>`).join("") + "</tbody>";
}

function exportXlsx() {
  const r = result, t = i18n.t, names = ["engagement", ...dims.map(([d]) => d)];
  const sheets = [
    { name: t("xSummary"), widths: [30, 14], rows: [[t("xMeasure"), t("xValue")], [t("kResp"), r.response_rate], [t("kN"), r.respondents],
      [t("kEng"), r.engagement.score], [t("kEnps"), r.enps ? r.enps.score : null]] },
    { name: t("xDims"), widths: [30, 12, 12, 12, 10], rows: [[t("dDim"), t("dScore"), "low", "high", t("dN")],
      ...[{ dimension: outcomeName, ...r.engagement }, ...r.dimensions].map((d) => [d.dimension, d.score, d.ci?.[0] ?? null, d.ci?.[1] ?? null, d.people])] },
    { name: t("xTeams"), widths: [24, 12, ...names.map(() => 14)], rows: [[t("gTeam"), t("gN"), ...names],
      ...r.groups.map((g) => g.respondents == null ? [g.group, t("hidden", { n: MIN_GROUP })] : [g.group, g.respondents, ...names.map((n) => g[n])])] },
  ];
  if (r.drivers) sheets.splice(2, 0, { name: t("xDrivers"), widths: [30, 16], rows: [[t("wDim"), t("wShare")], ...Object.entries(r.drivers.weights)] });
  download(writeXlsx(sheets), `${t("fileOut")}.xlsx`, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet");
}

$("file-a").addEventListener("change", (e) => e.target.files[0] && load(e.target.files[0], "a"));
$("file-q").addEventListener("change", (e) => e.target.files[0] && load(e.target.files[0], "q"));
for (const [id, w] of [["drop-a", "a"], ["drop-q", "q"]]) {
  const el = $(id);
  el.addEventListener("dragover", (e) => { e.preventDefault(); el.classList.add("is-over"); });
  el.addEventListener("dragleave", () => el.classList.remove("is-over"));
  el.addEventListener("drop", (e) => { e.preventDefault(); el.classList.remove("is-over"); if (e.dataTransfer.files[0]) load(e.dataTransfer.files[0], w); });
}
$("esempio").addEventListener("click", async () => {
  const [a, q] = await Promise.all(["sample_survey_responses.csv", "sample_survey_instrument.csv"].map((f) => fetch(f)));
  if (!a.ok || !q.ok) return msg("errore", i18n.t("errRead", { msg: a.status }));
  await load(new File([await q.text()], "survey_instrument.csv"), "q");
  await load(new File([await a.text()], "survey_responses.csv"), "a");
  $("r-outcome").value = "Engagement (outcome)";
});
$("calcola").addEventListener("click", run);
$("scarica").addEventListener("click", exportXlsx);
$("stampa").addEventListener("click", () => window.print());
i18n.apply();
i18n.onChange(() => { if (answers) { const sel = ["r-group", "r-resp", "r-enps"].map((i) => $(i).value), o = $("r-outcome").value;
  setupColumns(); ["r-group", "r-resp", "r-enps"].forEach((i, k) => ($(i).value = sel[k])); $("r-outcome").value = o; } if (result) draw(); });
