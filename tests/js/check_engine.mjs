// Recomputes with web/engine.js every case src/tool_reference.py computed, and fails at the first difference.
import { readFileSync } from "node:fs";
import { analyse } from "../../web/engine.js";
import { parseCsv } from "../../web/design/table.js";

const root = new URL("../../", import.meta.url);
const V = JSON.parse(readFileSync(new URL("tests/fixtures/tool_vectors.json", root)));
let checks = 0, failures = 0;
const fail = (w) => { failures++; if (failures <= 25) console.error("difference:", w); };
function compare(a, b, path) {
  if (b === null || typeof b !== "object") {
    checks++;
    if (typeof b === "number" && typeof a === "number") { if (Math.abs(a - b) > 1e-9 * Math.max(1, Math.abs(b))) fail(`${path}: ${a} vs ${b}`); }
    else if (a !== b) fail(`${path}: ${JSON.stringify(a)} vs ${JSON.stringify(b)}`);
    return;
  }
  if (a === null || typeof a !== "object") { checks++; fail(`${path}: ${JSON.stringify(a)} vs object`); return; }
  for (const k of new Set([...Object.keys(a), ...Object.keys(b)])) compare(a[k], b[k], `${path}.${k}`);
}
for (const c of V.cases) {
  let rows = c.rows;
  if (c.source) {
    const items = [...c.dims.flatMap(([, i]) => i), ...c.outcome];
    rows = parseCsv(readFileSync(new URL("data/survey_responses.csv", root), "utf8")).rows.map((r) => ({
      group: r.team_id, responded: r.responded === "1", enps: r.enps === "" ? null : Number(r.enps),
      items: Object.fromEntries(items.map((i) => [i, r[i] === "" ? null : Number(r[i])])) }));
  }
  compare(analyse(rows, c.dims, c.outcome), c.result, c.name);
}
console.log(`${checks - failures} of ${checks} values agree with Python in ${V.cases.length} cases`);
process.exit(failures ? 1 : 0);
