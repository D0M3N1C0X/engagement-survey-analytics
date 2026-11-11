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
from surveylib import (DIMENSION_ORDER, FIELD_WINDOW, MIN_GROUP, OUTPUT, PRIVATE_MODE, ROOT, SEGMENTS,
                       SURVEY_NAME, driver_items, load_comments, load_instrument,
                       load_responses, outcome_items)

TITLE = "Voice 2026 Survey Explorer"
QUESTIONS = ["what_to_change", "what_works"]


def build_payload() -> dict:
    rows = load_responses()
    instrument = load_instrument()
    items_by_dim = driver_items(instrument)
    outcome = outcome_items(instrument)

    levels = {}
    value_map = {}
    for key in SEGMENTS:
        raw_values = sorted({r[key] for r in rows})
        if PRIVATE_MODE:
            respondent_counts = {
                value: sum(1 for row in rows if row[key] == value and row["responded"])
                for value in raw_values
            }
            common = [value for value in raw_values if respondent_counts[value] >= MIN_GROUP]
            rare = [value for value in raw_values if respondent_counts[value] < MIN_GROUP]
            labels = common + (["Suppressed categories"] if rare else [])
            value_map[key] = {value: value if value in common else "Suppressed categories"
                              for value in raw_values}
            levels[key] = labels
        else:
            value_map[key] = {value: value for value in raw_values}
            levels[key] = raw_values
    index = {key: {value: i for i, value in enumerate(values)} for key, values in levels.items()}
    team_levels = sorted({row["team_id"] for row in rows})
    team_index = {team_id: i for i, team_id in enumerate(team_levels)}

    people = []
    person_index = {}
    for i, row in enumerate(rows):
        person_index[row["response_id"]] = i
        record = [index[key][value_map[key][row[key]]] for key in SEGMENTS]
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
        record.append(team_index[row["team_id"]])
        people.append(record)

    themes = list(T.THEME_LEXICON)
    theme_index = {theme: i for i, theme in enumerate(themes)}

    comments = []
    if not PRIVATE_MODE:
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
            "private": PRIVATE_MODE,
            "teamClusters": len(team_levels),
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
  --bg:#f5f5f7; --surface:#ffffff; --raised:#ffffff;
  --ink:#1d1d1f; --secondary:#424245; --muted:#6e6e73;
  --line:#e8e8ed; --line-strong:#d2d2d7;
  --blue:#0071e3; --orange:#ff9500; --aqua:#1baf7a; --red:#d70015; --neutral:#d2d2d7;
  --on-blue:#ffffff; --on-red:#ffffff; --on-neutral:#1d1d1f;
  --good:#1baf7a; --warn:#ff9500;
  --shadow:0 1px 2px rgba(20,22,26,.05), 0 6px 20px rgba(20,22,26,.06);
}
@media (prefers-color-scheme: dark){
  :root:not([data-theme="light"]){
    color-scheme: dark;
    --bg:#000000; --surface:#15171c; --raised:#1d2027;
    --ink:#f5f5f7; --secondary:#c7c9d1; --muted:#8b8f9a;
    --line:#23262e; --line-strong:#343844;
    --blue:#4f8cff; --orange:#ff9f0a; --aqua:#2bc48b; --red:#ff6961; --neutral:#4a4e59;
    --on-blue:#000000; --on-red:#000000; --on-neutral:#ffffff;
    --good:#2bc48b; --warn:#ff9f0a;
    --shadow:0 1px 2px rgba(0,0,0,.4), 0 8px 24px rgba(0,0,0,.35);
  }
}
:root[data-theme="dark"]{
  color-scheme: dark;
  --bg:#000000; --surface:#15171c; --raised:#1d2027;
  --ink:#f5f5f7; --secondary:#c7c9d1; --muted:#8b8f9a;
  --line:#23262e; --line-strong:#343844;
  --blue:#4f8cff; --orange:#ff9f0a; --aqua:#2bc48b; --red:#ff6961; --neutral:#4a4e59;
  --on-blue:#000000; --on-red:#000000; --on-neutral:#ffffff;
  --good:#2bc48b; --warn:#ff9f0a;
  --shadow:0 1px 2px rgba(0,0,0,.4), 0 8px 24px rgba(0,0,0,.35);
}

*{box-sizing:border-box}
body{
  margin:0; background:var(--bg); color:var(--ink);
  font-family:-apple-system,BlinkMacSystemFont,"SF Pro Text","Inter","Segoe UI",Roboto,"Helvetica Neue",Arial,sans-serif;
  font-size:15px; line-height:1.55; -webkit-font-smoothing:antialiased;
}
.wrap{max-width:1180px; margin:0 auto; padding:clamp(1rem,3vw,2.5rem) clamp(1rem,3vw,2rem) 4rem}

header.masthead{border-bottom:1px solid var(--line-strong); padding-bottom:1.25rem; margin-bottom:1.5rem}
.masthead-top{display:flex; justify-content:space-between; align-items:center; gap:1rem}
.theme-toggle{cursor:pointer; white-space:nowrap}
.privacy-banner{margin:0 0 1.25rem; padding:.8rem 1rem; border:1px solid var(--warn); border-radius:9px;
  color:var(--secondary); background:var(--surface); font-size:.84rem}
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
.verbatim-tools{display:flex; align-items:center; gap:.6rem; margin:0 0 .7rem; color:var(--muted); font-size:.8rem}
.verbatim-tools select{max-width:14rem}
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
    <div class="masthead-top">
      <p class="eyebrow" id="eyebrow"></p>
      <button type="button" class="theme-toggle" id="theme-toggle" aria-label="Change colour theme">Theme: system</button>
    </div>
    <h1>Explore employee experience across the organisation</h1>
    <p class="sub">Filter the survey and every number below recomputes. Scores are hidden
      for any group smaller than <span id="min-group"></span> respondents.</p>
  </header>

  <div class="privacy-banner hidden" id="privacy-banner" role="note">
    <strong>Local confidential output.</strong> This HTML embeds respondent-level survey scores and segment values so its filters work offline. It contains no free-text comments and sends no data over the network. Keep it in an approved, access-controlled location; do not publish or email it.
  </div>

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
          <p class="hint" id="verbatim-hint">Comments from the selected group. Choose a theme to narrow them.</p>
          <div class="verbatim-tools" id="verbatim-tools">
            <label for="verbatim-sort">Sort</label>
            <select id="verbatim-sort">
              <option value="balanced">Balanced sample</option>
              <option value="critical">Most critical first</option>
              <option value="positive">Most positive first</option>
            </select>
          </div>
          <div id="verbatims" class="verbatims" tabindex="0" role="region" aria-label="Verbatims"></div>
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

  <footer id="footer-note"></footer>
</div>
<div class="tooltip" id="tooltip" role="status"></div>
"""

SCRIPT = r"""
<script>
const DATA = __PAYLOAD__;
const SEG = DATA.segmentKeys;
const NDIM = DATA.dimensions.length;
const OFFSET = {seg: 0, responded: SEG.length, engK: SEG.length + 1, engN: SEG.length + 2,
                enps: SEG.length + 3, dims: SEG.length + 4,
                team: SEG.length + 4 + NDIM * 2};
const state = {filters: {}, theme: null};
const tooltip = document.getElementById('tooltip');
let verbatimSort = 'balanced';

const css = name => getComputedStyle(document.documentElement).getPropertyValue(name).trim();
const pct = (x, d = 0) => (x * 100).toFixed(d) + '%';

function bootstrapMeanInterval(values, clusters = null, reps = 1000, seed = 31) {
  if (!values.length) return [NaN, NaN];
  if (values.length === 1) return [values[0], values[0]];
  if (clusters && clusters.length !== values.length) throw new Error('Bootstrap cluster labels do not match values');
  let state = seed >>> 0;
  const randomIndex = n => {
    state ^= state << 13; state ^= state >>> 17; state ^= state << 5;
    return (state >>> 0) % n;
  };
  const draws = [];
  const clusterMap = new Map();
  if (clusters) values.forEach((value, i) => {
    if (!clusterMap.has(clusters[i])) clusterMap.set(clusters[i], []);
    clusterMap.get(clusters[i]).push(value);
  });
  if (clusterMap.size > 1) {
    const groups = Array.from(clusterMap.values());
    for (let r = 0; r < reps; r++) {
      let total = 0, count = 0;
      for (let i = 0; i < groups.length; i++) {
        const group = groups[randomIndex(groups.length)];
        for (const value of group) { total += value; count++; }
      }
      draws.push(total / count);
    }
  } else {
    for (let r = 0; r < reps; r++) {
      let total = 0;
      for (let i = 0; i < values.length; i++) total += values[randomIndex(values.length)];
      draws.push(total / values.length);
    }
  }
  draws.sort((a, b) => a - b);
  return [draws[Math.floor(0.025 * (reps - 1))], draws[Math.ceil(0.975 * (reps - 1))]];
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
  const engagementValues = [], engagementClusters = [];
  let promoters = 0, passives = 0, detractors = 0, rated = 0;
  for (const p of respondents) {
    if (p[OFFSET.engN]) {
      engagementValues.push(p[OFFSET.engK] / p[OFFSET.engN]);
      engagementClusters.push(p[OFFSET.team]);
    }
    const score = p[OFFSET.enps];
    if (score >= 0) { rated++; if (score >= 9) promoters++; else if (score >= 7) passives++; else detractors++; }
  }
  out.engagement = engagementValues.length
    ? engagementValues.reduce((a, b) => a + b, 0) / engagementValues.length : NaN;
  out.engagementCI = bootstrapMeanInterval(engagementValues, engagementClusters);
  out.enps = rated ? {score: (promoters - detractors) / rated * 100, promoters, passives, detractors, rated} : null;
  for (let d = 0; d < NDIM; d++) {
    let k = 0, n = 0;
    const shares = [], clusters = [];
    for (const p of respondents) {
      const favourable = p[OFFSET.dims + d * 2], answers = p[OFFSET.dims + d * 2 + 1];
      k += favourable; n += answers;
      if (answers) { shares.push(favourable / answers); clusters.push(p[OFFSET.team]); }
    }
    const rate = shares.length ? shares.reduce((a, b) => a + b, 0) / shares.length : NaN;
    out.dims.push({name: DATA.dimensions[d], favourable: rate, k, n,
                   people: shares.length, ci: bootstrapMeanInterval(shares, clusters)});
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
                          .sort((a, b) => (b.people >= DATA.meta.minGroup ? b.favourable : -Infinity)
                                       - (a.people >= DATA.meta.minGroup ? a.favourable : -Infinity));
  const bars = rows.map(row => {
    if (row.people < DATA.meta.minGroup) return `<div class="dim-row"><span class="dim-name">${row.name}</span><span class="dim-track"></span><span class="dim-value">—</span></div>`;
    const delta = row.favourable - row.company;
    const colour = delta < -0.05 ? 'var(--orange)' : 'var(--blue)';
    const tip = `${row.people.toLocaleString('en-GB')} respondents · 95% bootstrap interval ${pct(row.ci[0])}–${pct(row.ci[1])} · company ${pct(row.company)}`;
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
      <th class="r">95% bootstrap interval</th><th class="r">Company</th><th class="r">Gap</th></tr></thead><tbody>` +
    rows.map(r => `<tr><td>${r.name}</td><td class="r">${r.people < DATA.meta.minGroup ? '—' : pct(r.favourable)}</td>
      <td class="r">${r.people < DATA.meta.minGroup ? '—' : `${pct(r.ci[0])}–${pct(r.ci[1])}`}</td>
      <td class="r">${COMPANY.dims[DATA.dimensions.indexOf(r.name)].people < DATA.meta.minGroup ? '—' : pct(r.company)}</td>
      <td class="r">${r.people < DATA.meta.minGroup || COMPANY.dims[DATA.dimensions.indexOf(r.name)].people < DATA.meta.minGroup ? '—' : `${((r.favourable - r.company) * 100).toFixed(1)} pp`}</td></tr>`).join('') +
    '</tbody></table>';
}

function enpsChart(current) {
  const e = current.enps;
  if (!e) return '<p class="hint">No rated responses in this group.</p>';
  if (e.rated < DATA.meta.minGroup) return '<p class="hint">eNPS is hidden below the reporting threshold.</p>';
  const parts = [
    {label: 'Detractors', value: e.detractors / e.rated, colour: 'var(--red)', ink: 'var(--on-red)'},
    {label: 'Passives', value: e.passives / e.rated, colour: 'var(--neutral)', ink: 'var(--on-neutral)'},
    {label: 'Promoters', value: e.promoters / e.rated, colour: 'var(--blue)', ink: 'var(--on-blue)'},
  ];
  const segments = parts.map(part => `
    <span class="enps-seg" style="width:${(part.value * 100).toFixed(1)}%;background:${part.colour};color:${part.ink}"
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
  if (DATA.meta.private) return '<p class="hint">Free-text themes are available in the local aggregate report. The interactive HTML omits comments and respondent-level text tags.</p>';
  const authors = Array.from({length: DATA.themes.length}, () => new Map());
  for (const c of comments) for (const t of c[3]) {
    if (!authors[t].has(c[0])) authors[t].set(c[0], []);
    authors[t].get(c[0]).push(c[2]);
  }
  const counts = authors.map(group => group.size);
  const sentiment = authors.map(group => {
    const values = Array.from(group.values(), xs => xs.reduce((a, b) => a + b, 0) / xs.length);
    return values.length ? values.reduce((a, b) => a + b, 0) / values.length : 0;
  });
  const max = Math.max(1, ...counts);
  const rows = DATA.themes.map((name, i) => ({name, i, count: counts[i],
                                              tone: counts[i] ? sentiment[i] / counts[i] : 0}))
                          .filter(r => r.count >= DATA.meta.minGroup)
                          .sort((a, b) => b.count - a.count);
  if (!rows.length) return '<p class="hint">Nobody in this group left a comment.</p>';
  return rows.map(r => `
    <button class="theme-row" aria-pressed="${state.theme === r.i}" data-theme="${r.i}">
      <span>
        <span class="theme-name"><span class="dot" style="background:${sentimentColour(r.tone)}"></span>${r.name}</span>
        <span class="theme-meter"><span style="width:${(r.count / max * 100).toFixed(1)}%; background:${sentimentColour(r.tone)}"></span></span>
      </span>
        <span class="theme-count">${r.count} people · ${r.tone >= 0 ? '+' : ''}${r.tone.toFixed(2)}</span>
    </button>`).join('');
}

function renderVerbatims(comments) {
  if (DATA.meta.private) return '<p class="hint">Verbatim text is withheld from the local interactive dashboard.</p>';
  let pool = comments;
  if (state.theme !== null) pool = pool.filter(c => c[3].includes(state.theme));
  if (!pool.length) return '<p class="hint">No comments match this selection.</p>';
  const authorCount = new Set(pool.map(c => c[0])).size;
  if (authorCount < DATA.meta.minGroup) return `<p class="hint">Text hidden: fewer than ${DATA.meta.minGroup} distinct respondents contributed.</p>`;
  const byTone = pool.slice().sort((a, b) => a[2] - b[2]);
  let sorted;
  if (verbatimSort === 'critical') sorted = byTone.slice(0, 40);
  else if (verbatimSort === 'positive') sorted = byTone.slice(-40).reverse();
  else {
    sorted = [];
    let low = 0, high = byTone.length - 1;
    while (sorted.length < Math.min(40, byTone.length)) {
      sorted.push(byTone[low++]);
      if (low <= high && sorted.length < 40) sorted.push(byTone[high--]);
    }
  }
  return sorted.map(c => {
    const person = DATA.people[c[0]];
    const where = SEG.map((key, i) => DATA.segments[key][person[i]]);
    const tone = c[2] < -0.15 ? 'negative' : c[2] > 0.15 ? 'positive' : '';
    return `<div class="verbatim ${tone}">
      <p>${escapeHtml(c[4])}</p>
      <span class="who">${DATA.questions[c[1]]} · ${escapeHtml(where[0])}, ${escapeHtml(where[1])} · ${escapeHtml(where[3])} tenure</span>
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
      {label: 'Respondents', value: 'Below threshold',
       note: 'fewer than the minimum reportable group'},
      {label: 'Engagement index', value: '—', note: 'below reporting threshold'},
      {label: 'eNPS', value: '—', note: 'below reporting threshold'},
      {label: 'Lowest scoring', value: '—', note: 'below reporting threshold'},
    ].map(t => `<div class="tile"><div class="label">${t.label}</div>
        <div class="value">${t.value}</div><div class="note">${t.note}</div></div>`).join('');
  }
  const deltaEngagement = current.engagement - COMPANY.engagement;
  const deltaEnps = current.enps && COMPANY.enps && current.enps.rated >= DATA.meta.minGroup
    && COMPANY.enps.rated >= DATA.meta.minGroup ? current.enps.score - COMPANY.enps.score : 0;
  const tiles = [
    {label: 'Respondents', value: current.n.toLocaleString('en-GB'),
     note: `${pct(responseRate, 0)} of ${current.invited.toLocaleString('en-GB')} invited`},
    {label: 'Engagement index', value: pct(current.engagement),
     note: `95% bootstrap interval ${pct(current.engagementCI[0], 1)}–${pct(current.engagementCI[1], 1)}`,
     delta: deltaEngagement},
    {label: 'eNPS', value: current.enps && current.enps.rated >= DATA.meta.minGroup
       ? (current.enps.score >= 0 ? '+' : '') + current.enps.score.toFixed(0) : '—',
     note: current.enps && current.enps.rated >= DATA.meta.minGroup
       ? `${pct(current.enps.detractors / current.enps.rated)} detractors` : 'below reporting threshold',
     delta: deltaEnps / 100},
    {label: 'Lowest scoring', value: lowest(current).short,
     note: Number.isFinite(lowest(current).favourable)
       ? `${pct(lowest(current).favourable)} favourable` : 'below dimension reporting threshold'},
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
  const sorted = current.dims.filter(d => d.people >= DATA.meta.minGroup)
                             .sort((a, b) => a.favourable - b.favourable);
  if (!sorted.length) return {short: '—', favourable: NaN};
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
      `<strong>Results hidden.</strong> This selection is below the reporting threshold of ${DATA.meta.minGroup} respondents.
       Confidentiality is what makes people
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
        ${DATA.segments[key].map((v, i) => `<option value="${i}">${escapeHtml(v)}</option>`).join('')}
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
if (DATA.meta.private) {
  document.getElementById('privacy-banner').classList.remove('hidden');
  document.getElementById('verbatim-tools').classList.add('hidden');
  document.getElementById('verbatim-hint').textContent = 'Free-text is processed only in the aggregate report.';
  document.getElementById('footer-note').textContent = 'Local confidential output. Respondent-level survey values are embedded for offline filtering; free-text comments are omitted. No data is sent over the network.';
} else {
  document.getElementById('footer-note').innerHTML = 'Synthetic data, generated with a fixed seed - no real employee responses. Built by <code>python3 src/build_dashboard.py</code>; figures recompute in the browser from the embedded response-level demo data.';
}
document.getElementById('theme-toggle').addEventListener('click', event => {
  const root = document.documentElement;
  const current = root.dataset.theme || 'system';
  const next = current === 'system' ? 'light' : current === 'light' ? 'dark' : 'system';
  if (next === 'system') delete root.dataset.theme;
  else root.dataset.theme = next;
  event.currentTarget.textContent = `Theme: ${next}`;
});
document.getElementById('verbatim-sort').addEventListener('change', event => {
  verbatimSort = event.target.value;
  render();
});
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
        target = Path(args[0]) if args else (OUTPUT / "dashboard.fragment.html" if PRIVATE_MODE
                                             else ROOT / "dashboard.fragment.html")
        target.write_text(content, encoding="utf-8")
    else:
        target = OUTPUT / "dashboard.html" if PRIVATE_MODE else ROOT / "dashboard.html"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            '<!doctype html><html lang="en"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            f"<title>{TITLE}</title>{STYLE}</head><body>{BODY}{script}</body></html>",
            encoding="utf-8")

    shown = target.relative_to(ROOT) if target.is_relative_to(ROOT) else target
    print(f"     {shown}  ({target.stat().st_size / 1024:.0f} KB)")


if __name__ == "__main__":
    main()
