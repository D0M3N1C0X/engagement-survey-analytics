"""
Build dashboard.html - the interactive read-out, in one self-contained file.

Everything the page needs is embedded: the respondent-level data as compact
integer arrays, the tagged verbatims, and the JavaScript that recomputes every
number when a filter changes. No server, no build step, no libraries - open the
file and it works.

    python3 src/build_dashboard.py                    -> dashboard.html
    python3 src/build_dashboard.py --fragment [PATH]  -> body-only variant

The confidentiality rule is enforced in the browser as well as in the report:
filter down to fewer than five respondents and the page refuses to show scores
rather than quietly displaying them.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import textlib as T
from surveylib import (DIMENSION_ORDER, FIELD_WINDOW, MIN_GROUP, ROOT, SEGMENTS,
                       SURVEY_NAME, driver_items, load_comments, load_instrument,
                       load_responses, outcome_items)

TITLE = "Voice 2026 Survey Explorer"
QUESTIONS = ["what_to_change", "what_works"]


def build_payload() -> dict:
    rows = load_responses()
    instrument = load_instrument()
    items_by_dim = driver_items(instrument)
    outcome = outcome_items(instrument)

    levels = {key: sorted({r[key] for r in rows}) for key in SEGMENTS}
    index = {key: {value: i for i, value in enumerate(values)} for key, values in levels.items()}

    people = []
    person_index = {}
    for i, row in enumerate(rows):
        person_index[row["response_id"]] = i
        record = [index[key][row[key]] for key in SEGMENTS]
        record.append(1 if row["responded"] else 0)

        if row["responded"]:
            answers = [row[item] for item in outcome if row.get(item)]
            record += [sum(1 for a in answers if a >= 4), len(answers)]
            record.append(row["enps"] if row["enps"] is not None else -1)
            for dim in DIMENSION_ORDER:
                dim_answers = [row[item] for item in items_by_dim[dim] if row.get(item)]
                record += [sum(1 for a in dim_answers if a >= 4), len(dim_answers)]
        else:
            record += [0, 0, -1] + [0, 0] * len(DIMENSION_ORDER)
        people.append(record)

    themes = list(T.THEME_LEXICON)
    theme_index = {theme: i for i, theme in enumerate(themes)}

    comments = []
    for comment in load_comments():
        text, _redacted = T.redact(comment["comment_text"])
        tags = [theme_index[t] for t in T.tag_themes(text)]
        comments.append([person_index[comment["response_id"]],
                         QUESTIONS.index(comment["question"]),
                         round(T.sentiment(text), 2), tags, text])

    return {
        "meta": {
            "survey": SURVEY_NAME,
            "field": FIELD_WINDOW,
            "invited": len(rows),
            "responded": sum(1 for r in rows if r["responded"]),
            "minGroup": MIN_GROUP,
        },
        "segmentKeys": SEGMENTS,
        "segmentLabels": {"department": "Department", "country": "Country",
                          "job_level": "Level", "tenure_band": "Tenure",
                          "work_model": "Work model"},
        "segments": levels,
        "dimensions": DIMENSION_ORDER,
        "themes": themes,
        "questions": ["What should change", "What works well"],
        "people": people,
        "comments": comments,
    }


STYLE = """
<style>
:root{
  color-scheme: light;
  --bg:#f7f7f5; --surface:#fcfcfb; --raised:#ffffff;
  --ink:#14161a; --secondary:#52514e; --muted:#7a7975;
  --line:#e4e4e0; --line-strong:#d2d2cc;
  --blue:#2a78d6; --orange:#eb6834; --aqua:#1baf7a; --red:#e34948; --neutral:#c9c8c3;
  --good:#1baf7a; --warn:#eb6834;
  --shadow:0 1px 2px rgba(20,22,26,.05), 0 6px 20px rgba(20,22,26,.06);
}
@media (prefers-color-scheme: dark){
  :root:not([data-theme="light"]){
    color-scheme: dark;
    --bg:#121211; --surface:#1a1a19; --raised:#212120;
    --ink:#f4f4f2; --secondary:#c3c2b7; --muted:#95948c;
    --line:#2c2c2a; --line-strong:#3d3d3a;
    --blue:#3987e5; --orange:#d95926; --aqua:#199e70; --red:#e66767; --neutral:#4a4a46;
    --good:#199e70; --warn:#d95926;
    --shadow:0 1px 2px rgba(0,0,0,.4), 0 8px 24px rgba(0,0,0,.35);
  }
}
:root[data-theme="dark"]{
  color-scheme: dark;
  --bg:#121211; --surface:#1a1a19; --raised:#212120;
  --ink:#f4f4f2; --secondary:#c3c2b7; --muted:#95948c;
  --line:#2c2c2a; --line-strong:#3d3d3a;
  --blue:#3987e5; --orange:#d95926; --aqua:#199e70; --red:#e66767; --neutral:#4a4a46;
  --good:#199e70; --warn:#d95926;
  --shadow:0 1px 2px rgba(0,0,0,.4), 0 8px 24px rgba(0,0,0,.35);
}

*{box-sizing:border-box}
body{
  margin:0; background:var(--bg); color:var(--ink);
  font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;
  font-size:15px; line-height:1.55; -webkit-font-smoothing:antialiased;
}
.wrap{max-width:1180px; margin:0 auto; padding:clamp(1rem,3vw,2.5rem) clamp(1rem,3vw,2rem) 4rem}

header.masthead{border-bottom:1px solid var(--line-strong); padding-bottom:1.25rem; margin-bottom:1.5rem}
.eyebrow{font-size:.72rem; letter-spacing:.14em; text-transform:uppercase; color:var(--muted); font-weight:600}
h1{font-size:clamp(1.5rem,3.2vw,2.1rem); margin:.35rem 0 .3rem; letter-spacing:-.015em}
.sub{color:var(--secondary); font-size:.95rem; margin:0}

.controls{
  display:flex; flex-wrap:wrap; gap:.75rem; align-items:flex-end;
  background:var(--surface); border:1px solid var(--line); border-radius:10px;
  padding:.9rem 1rem; margin-bottom:1.25rem
}
.control{display:flex; flex-direction:column; gap:.3rem; min-width:9.5rem; flex:1 1 9.5rem}
.control label{font-size:.7rem; letter-spacing:.08em; text-transform:uppercase; color:var(--muted); font-weight:600}
select, button{
  font:inherit; font-size:.9rem; color:var(--ink); background:var(--raised);
  border:1px solid var(--line-strong); border-radius:7px; padding:.45rem .6rem
}
select:focus-visible, button:focus-visible{outline:2px solid var(--blue); outline-offset:2px}
button.reset{cursor:pointer; align-self:flex-end; padding:.5rem .9rem}
button.reset:hover{border-color:var(--blue); color:var(--blue)}

.tiles{display:grid; grid-template-columns:repeat(auto-fit,minmax(190px,1fr)); gap:.9rem; margin-bottom:1.25rem}
.tile{background:var(--surface); border:1px solid var(--line); border-radius:10px; padding:.9rem 1rem}
.tile .label{font-size:.7rem; letter-spacing:.08em; text-transform:uppercase; color:var(--muted); font-weight:600}
.tile .value{font-size:2rem; font-weight:650; letter-spacing:-.02em; margin:.15rem 0 .1rem; font-variant-numeric:tabular-nums}
.tile .note{font-size:.8rem; color:var(--secondary)}
.tile .delta{font-size:.78rem; font-weight:600}
.up{color:var(--good)} .down{color:var(--warn)}

.grid{display:grid; grid-template-columns:1.35fr 1fr; gap:1rem; align-items:start}
@media (max-width:900px){ .grid{grid-template-columns:1fr} }

.panel{background:var(--surface); border:1px solid var(--line); border-radius:10px; padding:1rem 1.1rem 1.15rem; margin-bottom:1rem}
.panel h2{font-size:1rem; margin:0 0 .15rem; letter-spacing:-.01em}
.panel p.hint{margin:0 0 .9rem; font-size:.82rem; color:var(--muted)}
.panel .head{display:flex; justify-content:space-between; align-items:baseline; gap:1rem}
.linkish{background:none; border:none; color:var(--blue); cursor:pointer; font-size:.8rem; padding:0; text-decoration:underline}

.dim-chart{display:flex; flex-direction:column; gap:.3rem}
.dim-row{display:grid; grid-template-columns:minmax(6.5rem,10.5rem) 1fr 2.6rem; gap:.6rem; align-items:center}
.dim-row:hover .dim-fill{filter:brightness(1.07)}
.dim-name{font-size:.83rem; color:var(--ink); line-height:1.25}
.dim-track{position:relative; height:16px; background:var(--line); border-radius:5px}
.dim-fill{position:absolute; inset:0 auto 0 0; border-radius:5px}
.dim-marker{position:absolute; top:-3px; bottom:-3px; width:2px; background:var(--secondary); border-radius:1px}
.dim-value{font-size:.8rem; font-weight:600; color:var(--secondary); text-align:right; font-variant-numeric:tabular-nums}
.dim-row.axis{margin-top:.15rem}
.dim-track.ticks{background:none; height:1rem}
.dim-track.ticks .tick{position:absolute; top:0; transform:translateX(-50%); font-size:.68rem; color:var(--muted)}
.dim-track.ticks .tick:first-child{transform:none}
.dim-track.ticks .tick:last-child{transform:translateX(-100%)}

.enps-score{font-size:2rem; font-weight:650; letter-spacing:-.02em; display:flex; align-items:baseline; gap:.5rem; font-variant-numeric:tabular-nums}
.enps-score span{font-size:.78rem; font-weight:400; color:var(--muted); letter-spacing:0}
.enps-bar{display:flex; gap:2px; margin:.6rem 0 .5rem; height:26px}
.enps-seg{display:flex; align-items:center; justify-content:center; border-radius:4px; color:#fff;
          font-size:.75rem; font-weight:600; overflow:hidden}
.enps-legend{display:flex; gap:1rem; flex-wrap:wrap}
.enps-key{display:flex; align-items:center; gap:.35rem; font-size:.78rem; color:var(--secondary)}

table{border-collapse:collapse; width:100%; font-size:.85rem; font-variant-numeric:tabular-nums; margin-top:.5rem}
th,td{text-align:left; padding:.4rem .5rem; border-bottom:1px solid var(--line)}
th{font-size:.68rem; letter-spacing:.07em; text-transform:uppercase; color:var(--muted); font-weight:600}
td.r,th.r{text-align:right}

.themes{display:flex; flex-direction:column; gap:.35rem}
.theme-row{
  display:grid; grid-template-columns:1fr auto; gap:.6rem; align-items:center;
  background:none; border:1px solid transparent; border-radius:7px; padding:.35rem .5rem;
  cursor:pointer; text-align:left; font:inherit; color:var(--ink); width:100%
}
.theme-row:hover{border-color:var(--line-strong); background:var(--raised)}
.theme-row[aria-pressed="true"]{border-color:var(--blue); background:var(--raised)}
.theme-name{font-size:.86rem; display:flex; align-items:center; gap:.45rem}
.dot{width:9px; height:9px; border-radius:50%; flex:none}
.theme-meter{height:6px; border-radius:3px; background:var(--line); margin-top:.3rem; overflow:hidden}
.theme-meter span{display:block; height:100%; border-radius:3px}
.theme-count{font-size:.8rem; color:var(--secondary); white-space:nowrap; font-variant-numeric:tabular-nums}

.verbatims{display:flex; flex-direction:column; gap:.7rem; max-height:30rem; overflow-y:auto; padding-right:.3rem}
.verbatim{border-left:3px solid var(--line-strong); padding:.15rem 0 .15rem .75rem}
.verbatim p{margin:0 0 .2rem; font-size:.88rem}
.verbatim .who{font-size:.74rem; color:var(--muted)}
.verbatim.negative{border-left-color:var(--red)}
.verbatim.positive{border-left-color:var(--blue)}

.suppressed{
  background:var(--raised); border:1px dashed var(--line-strong); border-radius:10px;
  padding:1.5rem; text-align:center; color:var(--secondary); font-size:.9rem
}
.tooltip{
  position:fixed; pointer-events:none; opacity:0; transition:opacity .12s;
  background:var(--ink); color:var(--bg); font-size:.78rem; line-height:1.4;
  padding:.4rem .55rem; border-radius:6px; box-shadow:var(--shadow); z-index:20; max-width:15rem
}
footer{margin-top:1.5rem; font-size:.78rem; color:var(--muted); border-top:1px solid var(--line); padding-top:.9rem}
.hidden{display:none}
</style>
"""

BODY = """
<div class="wrap">
  <header class="masthead">
    <p class="eyebrow" id="eyebrow"></p>
    <h1>Employee engagement, by whoever you need to look at</h1>
    <p class="sub">Filter the survey and every number below recomputes. Scores are hidden
      for any group smaller than <span id="min-group"></span> respondents.</p>
  </header>

  <section class="controls" id="controls" aria-label="Filters"></section>

  <section class="tiles" id="tiles" aria-live="polite"></section>

  <div id="suppressed" class="suppressed hidden"></div>

  <div id="content">
    <div class="grid">
      <div>
        <section class="panel">
          <div class="head">
            <div>
              <h2>Favourable score by dimension</h2>
              <p class="hint">Bars are the selected group; the marker is the company score.</p>
            </div>
            <button class="linkish" id="toggle-table" aria-expanded="false">Show table</button>
          </div>
          <div id="dimension-chart"></div>
          <div id="dimension-table" class="hidden"></div>
        </section>

        <section class="panel">
          <h2>What people wrote</h2>
          <p class="hint">Verbatims from the selected group. Choose a theme to narrow them.</p>
          <div id="verbatims" class="verbatims"></div>
        </section>
      </div>

      <div>
        <section class="panel">
          <h2>eNPS</h2>
          <p class="hint">Promoters (9-10) minus detractors (0-6).</p>
          <div id="enps-chart"></div>
        </section>

        <section class="panel">
          <h2>Themes in the free text</h2>
          <p class="hint">Bar length is volume, colour is tone. Click to filter the verbatims.</p>
          <div class="themes" id="themes"></div>
        </section>
      </div>
    </div>
  </div>

  <footer>
    Synthetic data, generated with a fixed seed - no real employee responses. Built by
    <code>python3 src/build_dashboard.py</code>; every figure recomputes in the browser from
    the embedded response-level data.
  </footer>
</div>
<div class="tooltip" id="tooltip" role="status"></div>
"""

SCRIPT = r"""
<script>
const DATA = __PAYLOAD__;
const SEG = DATA.segmentKeys;
const NDIM = DATA.dimensions.length;
const OFFSET = {seg: 0, responded: SEG.length, engK: SEG.length + 1, engN: SEG.length + 2,
                enps: SEG.length + 3, dims: SEG.length + 4};
const state = {filters: {}, theme: null};
const tooltip = document.getElementById('tooltip');

const css = name => getComputedStyle(document.documentElement).getPropertyValue(name).trim();
const pct = (x, d = 0) => (x * 100).toFixed(d) + '%';

function wilson(k, n, z = 1.96) {
  if (!n) return [NaN, NaN];
  const p = k / n, d = 1 + z * z / n;
  const centre = (p + z * z / (2 * n)) / d;
  const margin = z * Math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d;
  return [Math.max(0, centre - margin), Math.min(1, centre + margin)];
}

function matches(person) {
  return SEG.every((key, i) => {
    const wanted = state.filters[key];
    return wanted === undefined || wanted === null || person[i] === wanted;
  });
}

function summarise(people) {
  const respondents = people.filter(p => p[OFFSET.responded] === 1);
  const out = {invited: people.length, n: respondents.length, dims: [], enps: null};
  let engK = 0, engN = 0, promoters = 0, passives = 0, detractors = 0, rated = 0;
  for (const p of respondents) {
    engK += p[OFFSET.engK]; engN += p[OFFSET.engN];
    const score = p[OFFSET.enps];
    if (score >= 0) { rated++; if (score >= 9) promoters++; else if (score >= 7) passives++; else detractors++; }
  }
  out.engagement = engN ? engK / engN : NaN;
  out.engagementCI = wilson(engK, engN);
  out.enps = rated ? {score: (promoters - detractors) / rated * 100, promoters, passives, detractors, rated} : null;
  for (let d = 0; d < NDIM; d++) {
    let k = 0, n = 0;
    for (const p of respondents) { k += p[OFFSET.dims + d * 2]; n += p[OFFSET.dims + d * 2 + 1]; }
    out.dims.push({name: DATA.dimensions[d], favourable: n ? k / n : NaN, k, n, ci: wilson(k, n)});
  }
  return out;
}

const COMPANY = summarise(DATA.people);

function commentsFor(indices) {
  const set = new Set(indices);
  return DATA.comments.filter(c => set.has(c[0]));
}

/* ---------- charts ---------- */

function dimensionChart(current) {
  const rows = current.dims.map((d, i) => ({...d, company: COMPANY.dims[i].favourable}))
                          .sort((a, b) => b.favourable - a.favourable);
  const bars = rows.map(row => {
    const delta = row.favourable - row.company;
    const colour = delta < -0.05 ? 'var(--orange)' : 'var(--blue)';
    const tip = `${row.n.toLocaleString('en-GB')} answers · 95% CI ${pct(row.ci[0])}–${pct(row.ci[1])} · company ${pct(row.company)}`;
    return `<div class="dim-row" data-tip="${tip}">
      <span class="dim-name">${row.name}</span>
      <span class="dim-track">
        <span class="dim-fill" style="width:${(row.favourable * 100).toFixed(1)}%;background:${colour}"></span>
        <span class="dim-marker" style="left:${(row.company * 100).toFixed(1)}%" title="company ${pct(row.company)}"></span>
      </span>
      <span class="dim-value">${pct(row.favourable)}</span>
    </div>`;
  }).join('');
  const ticks = [0, 25, 50, 75, 100].map(t =>
    `<span class="tick" style="left:${t}%">${t}%</span>`).join('');
  return `<div class="dim-chart">${bars}
    <div class="dim-row axis"><span></span><span class="dim-track ticks">${ticks}</span><span></span></div>
  </div>`;
}

function dimensionTable(current) {
  const rows = current.dims.map((d, i) => ({...d, company: COMPANY.dims[i].favourable}))
                          .sort((a, b) => b.favourable - a.favourable);
  return `<table><thead><tr><th>Dimension</th><th class="r">Favourable</th>
    <th class="r">95% CI</th><th class="r">Company</th><th class="r">Gap</th></tr></thead><tbody>` +
    rows.map(r => `<tr><td>${r.name}</td><td class="r">${pct(r.favourable)}</td>
      <td class="r">${pct(r.ci[0])}–${pct(r.ci[1])}</td><td class="r">${pct(r.company)}</td>
      <td class="r">${((r.favourable - r.company) * 100).toFixed(1)} pp</td></tr>`).join('') +
    '</tbody></table>';
}

function enpsChart(current) {
  const e = current.enps;
  if (!e) return '<p class="hint">No rated responses in this group.</p>';
  const parts = [
    {label: 'Detractors', value: e.detractors / e.rated, colour: 'var(--red)'},
    {label: 'Passives', value: e.passives / e.rated, colour: 'var(--neutral)'},
    {label: 'Promoters', value: e.promoters / e.rated, colour: 'var(--blue)'},
  ];
  const segments = parts.map(part => `
    <span class="enps-seg" style="width:${(part.value * 100).toFixed(1)}%;background:${part.colour}"
          data-tip="${part.label}: ${pct(part.value)} (${Math.round(part.value * e.rated).toLocaleString('en-GB')} people)">
      ${part.value > 0.12 ? pct(part.value) : ''}</span>`).join('');
  const legend = parts.map(part =>
    `<span class="enps-key"><span class="dot" style="background:${part.colour}"></span>${part.label}</span>`).join('');
  return `<div class="enps">
      <div class="enps-score">${e.score >= 0 ? '+' : ''}${e.score.toFixed(0)}
        <span>eNPS · ${e.rated.toLocaleString('en-GB')} rated responses</span></div>
      <div class="enps-bar">${segments}</div>
      <div class="enps-legend">${legend}</div>
    </div>`;
}

function sentimentColour(score) {
  if (score > 0.15) return css('--blue');
  if (score < -0.15) return css('--red');
  return css('--neutral');
}

function renderThemes(comments) {
  const counts = new Array(DATA.themes.length).fill(0);
  const sentiment = new Array(DATA.themes.length).fill(0);
  for (const c of comments) for (const t of c[3]) { counts[t]++; sentiment[t] += c[2]; }
  const max = Math.max(1, ...counts);
  const rows = DATA.themes.map((name, i) => ({name, i, count: counts[i],
                                              tone: counts[i] ? sentiment[i] / counts[i] : 0}))
                          .filter(r => r.count > 0)
                          .sort((a, b) => b.count - a.count);
  if (!rows.length) return '<p class="hint">Nobody in this group left a comment.</p>';
  return rows.map(r => `
    <button class="theme-row" aria-pressed="${state.theme === r.i}" data-theme="${r.i}">
      <span>
        <span class="theme-name"><span class="dot" style="background:${sentimentColour(r.tone)}"></span>${r.name}</span>
        <span class="theme-meter"><span style="width:${(r.count / max * 100).toFixed(1)}%; background:${sentimentColour(r.tone)}"></span></span>
      </span>
      <span class="theme-count">${r.count} · ${r.tone >= 0 ? '+' : ''}${r.tone.toFixed(2)}</span>
    </button>`).join('');
}

function renderVerbatims(comments) {
  let pool = comments;
  if (state.theme !== null) pool = pool.filter(c => c[3].includes(state.theme));
  if (!pool.length) return '<p class="hint">No comments match this selection.</p>';
  const sorted = pool.slice().sort((a, b) => a[2] - b[2]).slice(0, 40);
  return sorted.map(c => {
    const person = DATA.people[c[0]];
    const where = SEG.map((key, i) => DATA.segments[key][person[i]]);
    const tone = c[2] < -0.15 ? 'negative' : c[2] > 0.15 ? 'positive' : '';
    return `<div class="verbatim ${tone}">
      <p>${escapeHtml(c[4])}</p>
      <span class="who">${DATA.questions[c[1]]} · ${where[0]}, ${where[1]} · ${where[3]} tenure</span>
    </div>`;
  }).join('');
}

function escapeHtml(s) {
  return s.replace(/[&<>"]/g, ch => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;'}[ch]));
}

/* ---------- tiles ---------- */

function renderTiles(current) {
  const responseRate = current.invited ? current.n / current.invited : 0;
  // Below the threshold the tiles must be masked too - hiding the charts but
  // leaving the headline scores on screen would break the same promise.
  if (current.n < DATA.meta.minGroup) {
    return [
      {label: 'Respondents', value: current.n.toLocaleString('en-GB'),
       note: `of ${current.invited.toLocaleString('en-GB')} invited`},
      {label: 'Engagement index', value: '—', note: 'below reporting threshold'},
      {label: 'eNPS', value: '—', note: 'below reporting threshold'},
      {label: 'Lowest scoring', value: '—', note: 'below reporting threshold'},
    ].map(t => `<div class="tile"><div class="label">${t.label}</div>
        <div class="value">${t.value}</div><div class="note">${t.note}</div></div>`).join('');
  }
  const deltaEngagement = current.engagement - COMPANY.engagement;
  const deltaEnps = current.enps && COMPANY.enps ? current.enps.score - COMPANY.enps.score : 0;
  const tiles = [
    {label: 'Respondents', value: current.n.toLocaleString('en-GB'),
     note: `${pct(responseRate, 0)} of ${current.invited.toLocaleString('en-GB')} invited`},
    {label: 'Engagement index', value: pct(current.engagement),
     note: `95% CI ${pct(current.engagementCI[0], 1)}–${pct(current.engagementCI[1], 1)}`,
     delta: deltaEngagement},
    {label: 'eNPS', value: current.enps ? (current.enps.score >= 0 ? '+' : '') + current.enps.score.toFixed(0) : '—',
     note: current.enps ? `${pct(current.enps.detractors / current.enps.rated)} detractors` : '',
     delta: deltaEnps / 100},
    {label: 'Lowest scoring', value: lowest(current).short,
     note: `${pct(lowest(current).favourable)} favourable`},
  ];
  return tiles.map(t => `<div class="tile">
      <div class="label">${t.label}</div>
      <div class="value">${t.value}</div>
      <div class="note">${t.note}
        ${t.delta !== undefined && Math.abs(t.delta) > 0.0005
          ? `<span class="delta ${t.delta > 0 ? 'up' : 'down'}">${t.delta > 0 ? '▲' : '▼'} ${Math.abs(t.delta * 100).toFixed(1)}${t.label === 'eNPS' ? ' pts' : ' pp'} vs company</span>`
          : ''}</div>
    </div>`).join('');
}

function lowest(current) {
  const sorted = current.dims.slice().sort((a, b) => a.favourable - b.favourable);
  const worst = sorted[0];
  return {...worst, short: worst.name.split(' & ')[0]};
}

/* ---------- wiring ---------- */

function render() {
  const indices = [];
  const people = [];
  DATA.people.forEach((p, i) => { if (matches(p)) { people.push(p); indices.push(i); } });
  const current = summarise(people);

  document.getElementById('tiles').innerHTML = renderTiles(current);
  const suppressed = current.n < DATA.meta.minGroup;
  document.getElementById('suppressed').classList.toggle('hidden', !suppressed);
  document.getElementById('content').classList.toggle('hidden', suppressed);
  if (suppressed) {
    document.getElementById('suppressed').innerHTML =
      `<strong>Results hidden.</strong> This selection contains ${current.n} respondent${current.n === 1 ? '' : 's'},
       below the reporting threshold of ${DATA.meta.minGroup}. Confidentiality is what makes people
       answer honestly, so the page will not show scores this small — widen the filter.`;
    return;
  }

  document.getElementById('dimension-chart').innerHTML = dimensionChart(current);
  document.getElementById('dimension-table').innerHTML = dimensionTable(current);
  document.getElementById('enps-chart').innerHTML = enpsChart(current);
  const comments = commentsFor(indices);
  document.getElementById('themes').innerHTML = renderThemes(comments);
  document.getElementById('verbatims').innerHTML = renderVerbatims(comments);
}

function buildControls() {
  const container = document.getElementById('controls');
  container.innerHTML = SEG.map(key => `
    <div class="control">
      <label for="f-${key}">${DATA.segmentLabels[key]}</label>
      <select id="f-${key}" data-key="${key}">
        <option value="">All</option>
        ${DATA.segments[key].map((v, i) => `<option value="${i}">${v}</option>`).join('')}
      </select>
    </div>`).join('') + '<button class="reset" id="reset">Reset filters</button>';

  container.querySelectorAll('select').forEach(select => {
    select.addEventListener('change', () => {
      const value = select.value;
      state.filters[select.dataset.key] = value === '' ? null : Number(value);
      render();
    });
  });
  document.getElementById('reset').addEventListener('click', () => {
    container.querySelectorAll('select').forEach(s => { s.value = ''; });
    state.filters = {}; state.theme = null; render();
  });
}

document.addEventListener('click', event => {
  const themeButton = event.target.closest('.theme-row');
  if (themeButton) {
    const index = Number(themeButton.dataset.theme);
    state.theme = state.theme === index ? null : index;
    render();
  }
  if (event.target.id === 'toggle-table') {
    const table = document.getElementById('dimension-table');
    const open = table.classList.toggle('hidden');
    event.target.textContent = open ? 'Show table' : 'Hide table';
    event.target.setAttribute('aria-expanded', String(!open));
  }
});

document.addEventListener('mousemove', event => {
  const target = event.target.closest('[data-tip]');
  if (!target) { tooltip.style.opacity = 0; return; }
  tooltip.textContent = target.dataset.tip;
  tooltip.style.opacity = 1;
  tooltip.style.left = Math.min(window.innerWidth - 250, event.clientX + 14) + 'px';
  tooltip.style.top = (event.clientY + 16) + 'px';
});

document.getElementById('eyebrow').textContent =
  `${DATA.meta.survey} · ${DATA.meta.field} · ${DATA.meta.responded.toLocaleString('en-GB')} of ${DATA.meta.invited.toLocaleString('en-GB')} responded`;
document.getElementById('min-group').textContent = DATA.meta.minGroup;
buildControls();
render();
</script>
"""


def main() -> None:
    payload = build_payload()
    script = SCRIPT.replace("__PAYLOAD__", json.dumps(payload, separators=(",", ":")))
    content = f"<title>{TITLE}</title>{STYLE}{BODY}{script}"

    fragment = "--fragment" in sys.argv
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if fragment:
        target = Path(args[0]) if args else ROOT / "dashboard.fragment.html"
        target.write_text(content, encoding="utf-8")
    else:
        target = ROOT / "dashboard.html"
        target.write_text(
            '<!doctype html><html lang="en"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            f"<title>{TITLE}</title>{STYLE}</head><body>{BODY}{script}</body></html>",
            encoding="utf-8")

    shown = target.relative_to(ROOT) if target.is_relative_to(ROOT) else target
    print(f"     {shown}  ({target.stat().st_size / 1024:.0f} KB)")


if __name__ == "__main__":
    main()
