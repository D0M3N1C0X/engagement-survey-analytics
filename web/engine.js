// The survey check's calculations, the same as src/tool_reference.py (tests/js/check_engine.mjs recomputes every
// Python case and fails at the first difference). Runs in the page; the file is sent nowhere.
//
//   analyse(rows, dims, outcome)   rows: {group, responded, enps, items: {item: 1-5 | null}}
//                                  dims: [[dimension, [items]], ...] in display order; outcome: [items]

export const MIN_GROUP = 5;
const REPS = 1000, SEED = 31, MIN_DRIVER_RESPONDENTS = 50, MIN_DRIVER_GROUPS = 5;

export function bootstrap(values, clusters) {
  if (!values.length) return null;
  if (values.length === 1) return [values[0], values[0]];
  let state = SEED >>> 0;
  const index = (n) => { state ^= state << 13; state >>>= 0; state ^= state >>> 17; state ^= state << 5; state >>>= 0; return state % n; };
  const groups = new Map();
  values.forEach((v, i) => { if (!groups.has(clusters[i])) groups.set(clusters[i], []); groups.get(clusters[i]).push(v); });
  const draws = [];
  if (groups.size > 1) {
    const members = [...groups.values()];
    for (let r = 0; r < REPS; r++) {
      let total = 0, count = 0;
      for (let i = 0; i < members.length; i++) for (const v of members[index(members.length)]) { total += v; count++; }
      draws.push(total / count);
    }
  } else {
    for (let r = 0; r < REPS; r++) { let total = 0; for (let i = 0; i < values.length; i++) total += values[index(values.length)]; draws.push(total / values.length); }
  }
  draws.sort((a, b) => a - b);
  return [draws[Math.floor(0.025 * (REPS - 1))], draws[Math.ceil(0.975 * (REPS - 1))]];
}

const mean = (xs) => xs.reduce((s, v) => s + v, 0) / xs.length;
const answers = (r, items) => items.map((i) => r.items[i]).filter((v) => v != null && v !== 0);
const share = (a) => (a.length ? a.filter((v) => v >= 4).length / a.length : null);

// ---------------------------------------------------------------- Johnson's relative weights (statlib.py)
function zscores(xs) {
  const m = mean(xs), sd = Math.sqrt(xs.reduce((s, v) => s + (v - m) ** 2, 0) / (xs.length - 1));
  return xs.map((v) => (sd ? (v - m) / sd : 0));
}
function pearson(xs, ys) {
  const mx = mean(xs), my = mean(ys);
  let num = 0, sx = 0, sy = 0;
  for (let i = 0; i < xs.length; i++) { num += (xs[i] - mx) * (ys[i] - my); sx += (xs[i] - mx) ** 2; sy += (ys[i] - my) ** 2; }
  const den = Math.sqrt(sx * sy);
  return den ? num / den : NaN;
}
function invert(m) {
  const n = m.length, a = m.map((row, i) => [...row, ...row.map((_, j) => (i === j ? 1 : 0))]);
  for (let col = 0; col < n; col++) {
    let p = col;
    for (let r = col + 1; r < n; r++) if (Math.abs(a[r][col]) > Math.abs(a[p][col])) p = r;
    if (Math.abs(a[p][col]) < 1e-12) throw new Error("singular matrix");
    [a[col], a[p]] = [a[p], a[col]];
    const div = a[col][col];
    a[col] = a[col].map((v) => v / div);
    for (let r = 0; r < n; r++) if (r !== col && a[r][col]) { const f = a[r][col]; a[r] = a[r].map((v, j) => v - f * a[col][j]); }
  }
  return a.map((row) => row.slice(n));
}
function jacobi(matrix, sweeps = 100) {
  const n = matrix.length, a = matrix.map((r) => [...r]);
  const v = Array.from({ length: n }, (_, i) => Array.from({ length: n }, (_, j) => (i === j ? 1 : 0)));
  for (let s = 0; s < sweeps; s++) {
    let off = 0;
    for (let i = 0; i < n; i++) for (let j = 0; j < n; j++) if (i !== j) off += a[i][j] ** 2;
    if (Math.sqrt(off) < 1e-12) break;
    for (let p = 0; p < n - 1; p++) for (let q = p + 1; q < n; q++) {
      if (Math.abs(a[p][q]) < 1e-15) continue;
      const theta = (a[q][q] - a[p][p]) / (2 * a[p][q]);
      const t = Math.sign(theta || 1) / (Math.abs(theta) + Math.sqrt(theta * theta + 1));
      const c = 1 / Math.sqrt(t * t + 1), sn = t * c;
      for (let k = 0; k < n; k++) { const kp = a[k][p], kq = a[k][q]; a[k][p] = c * kp - sn * kq; a[k][q] = sn * kp + c * kq; }
      for (let k = 0; k < n; k++) { const pk = a[p][k], qk = a[q][k]; a[p][k] = c * pk - sn * qk; a[q][k] = sn * pk + c * qk; }
      for (let k = 0; k < n; k++) { const kp = v[k][p], kq = v[k][q]; v[k][p] = c * kp - sn * kq; v[k][q] = sn * kp + c * kq; }
    }
  }
  return [a.map((r, i) => r[i]), v];
}
const matmul = (a, b) => a.map((row) => b[0].map((_, j) => row.reduce((s, x, k) => s + x * b[k][j], 0)));
export function relativeWeights(predictors, outcome) {
  const X = predictors.map(zscores), y = zscores(outcome), k = X.length;
  const corr = X.map((xi) => X.map((xj) => pearson(xi, xj))), rxy = X.map((xi) => pearson(xi, y));
  let [values, vectors] = jacobi(corr);
  values = values.map((v) => Math.max(v, 1e-9));
  const sq = values.map((v, i) => values.map((_, j) => (i === j ? Math.sqrt(v) : 0)));
  const delta = matmul(matmul(vectors, sq), vectors[0].map((_, j) => vectors.map((row) => row[j])));
  const inv = invert(delta);
  const beta = inv.map((row) => row.reduce((s, v, j) => s + v * rxy[j], 0));
  const raw = delta.map((row) => row.reduce((s, d, j) => s + d * d * beta[j] * beta[j], 0));
  const r2 = raw.reduce((s, v) => s + v, 0);
  return [r2 ? raw.map((w) => w / r2) : raw.map(() => 0), r2];
}

// ---------------------------------------------------------------- the analysis
export function analyse(rows, dims, outcome) {
  const resp = rows.filter((r) => r.responded);
  const out = { invited: rows.length, respondents: resp.length, response_rate: rows.length ? resp.length / rows.length : null };
  const scored = (items) => {
    const vals = [], clus = [];
    for (const r of resp) { const s = share(answers(r, items)); if (s != null) { vals.push(s); clus.push(r.group); } }
    return [vals, clus];
  };
  const [ev, ec] = scored(outcome);
  out.engagement = { score: ev.length ? mean(ev) : null, people: ev.length, ci: bootstrap(ev, ec) };
  out.dimensions = dims.map(([d, items]) => { const [v, c] = scored(items); return { dimension: d, score: v.length ? mean(v) : null, people: v.length, ci: bootstrap(v, c) }; });
  const rated = resp.map((r) => r.enps).filter((e) => e != null);
  out.enps = null;
  if (rated.length) {
    const pro = rated.filter((e) => e >= 9).length, det = rated.filter((e) => e <= 6).length;
    out.enps = { score: (pro - det) / rated.length * 100, rated: rated.length, promoters: pro, detractors: det };
  }
  out.groups = [...new Set(rows.map((r) => r.group))].sort((a, b) => (a < b ? -1 : a > b ? 1 : 0)).map((g) => {
    const members = resp.filter((r) => r.group === g), invited = rows.filter((r) => r.group === g).length;
    if (members.length < MIN_GROUP) return { group: g, invited, respondents: null };
    const entry = { group: g, invited, respondents: members.length };
    for (const [name, items] of [["engagement", outcome], ...dims]) {
      const s = members.map((r) => share(answers(r, items))).filter((x) => x != null);
      entry[name] = s.length ? mean(s) : null;
    }
    return entry;
  });
  const cols = dims.map(() => []), y = [], groups = [];
  for (const r of resp) {
    const means = dims.map(([, items]) => { const a = answers(r, items); return a.length ? a.reduce((s, v) => s + v, 0) / a.length : null; });
    const e = answers(r, outcome);
    if (means.includes(null) || !e.length) continue;
    means.forEach((m, k) => cols[k].push(m));
    y.push(e.reduce((s, v) => s + v, 0) / e.length);
    groups.push(r.group);
  }
  out.drivers = null;
  if (y.length >= MIN_DRIVER_RESPONDENTS && new Set(groups).size >= MIN_DRIVER_GROUPS && dims.length >= 2) {
    try {
      const [w, r2] = relativeWeights(cols, y);
      out.drivers = { n: y.length, r2, weights: Object.fromEntries(dims.map(([d], k) => [d, w[k]])) };
    } catch { out.drivers = null; }
  }
  return out;
}
