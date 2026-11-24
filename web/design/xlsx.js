// strumenti-design 1.1.1 · xlsx.js
// Reads and writes .xlsx files in the browser with no library: an .xlsx is a zip of XML files, and the browser
// already knows how to inflate zip entries (DecompressionStream "deflate-raw"). Nothing is sent anywhere.
//
//   readXlsx(arrayBuffer)  -> [{ name, rows: [[cell, ...], ...] }]   one entry per sheet, in workbook order
//   writeXlsx(sheets)      -> Uint8Array of a valid .xlsx            sheets: [{ name, rows, widths?, header? }]
//
// Cells come back as numbers, booleans or strings; cells formatted as dates come back as "YYYY-MM-DD". Formulas
// return their cached value when the file was saved by Excel, LibreOffice or Google Sheets.

const td = new TextDecoder();
const te = new TextEncoder();

// ---- zip ------------------------------------------------------------------------------------------
async function inflate(bytes) {
  const stream = new Blob([bytes]).stream().pipeThrough(new DecompressionStream("deflate-raw"));
  return new Uint8Array(await new Response(stream).arrayBuffer());
}

async function unzip(buffer) {
  const b = new Uint8Array(buffer);
  const v = new DataView(b.buffer, b.byteOffset, b.byteLength);
  let eocd = -1;
  for (let i = b.length - 22; i >= Math.max(0, b.length - 65557); i--) {
    if (v.getUint32(i, true) === 0x06054b50) { eocd = i; break; }
  }
  if (eocd < 0) throw new Error("not a zip file");
  const count = v.getUint16(eocd + 10, true);
  let p = v.getUint32(eocd + 16, true);
  const files = {};
  for (let k = 0; k < count; k++) {
    if (v.getUint32(p, true) !== 0x02014b50) throw new Error("damaged zip directory");
    const method = v.getUint16(p + 10, true);
    const size = v.getUint32(p + 20, true);
    const nameLen = v.getUint16(p + 28, true), extraLen = v.getUint16(p + 30, true), commentLen = v.getUint16(p + 32, true);
    const local = v.getUint32(p + 42, true);
    const name = td.decode(b.subarray(p + 46, p + 46 + nameLen));
    const start = local + 30 + v.getUint16(local + 26, true) + v.getUint16(local + 28, true);
    const data = b.subarray(start, start + size);
    files[name] = method === 0 ? data : method === 8 ? await inflate(data) : null;
    p += 46 + nameLen + extraLen + commentLen;
  }
  return files;
}

const CRC = new Uint32Array(256).map((_, n) => {
  let c = n;
  for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
  return c >>> 0;
});
function crc32(bytes) {
  let c = 0xffffffff;
  for (const x of bytes) c = CRC[(c ^ x) & 0xff] ^ (c >>> 8);
  return (c ^ 0xffffffff) >>> 0;
}

// Stored (uncompressed) zip with a fixed date, so the same content gives the same bytes.
function zip(entries) {
  const parts = [], dir = [];
  let offset = 0;
  const DATE = ((2026 - 1980) << 9) | (1 << 5) | 1, TIME = 0;
  for (const [name, text] of entries) {
    const data = typeof text === "string" ? te.encode(text) : text;
    const nameBytes = te.encode(name);
    const crc = crc32(data);
    const h = new DataView(new ArrayBuffer(30));
    h.setUint32(0, 0x04034b50, true); h.setUint16(4, 20, true); h.setUint16(8, 0, true);
    h.setUint16(10, TIME, true); h.setUint16(12, DATE, true); h.setUint32(14, crc, true);
    h.setUint32(18, data.length, true); h.setUint32(22, data.length, true); h.setUint16(26, nameBytes.length, true);
    parts.push(new Uint8Array(h.buffer), nameBytes, data);
    const c = new DataView(new ArrayBuffer(46));
    c.setUint32(0, 0x02014b50, true); c.setUint16(4, 20, true); c.setUint16(6, 20, true);
    c.setUint16(12, TIME, true); c.setUint16(14, DATE, true); c.setUint32(16, crc, true);
    c.setUint32(20, data.length, true); c.setUint32(24, data.length, true); c.setUint16(28, nameBytes.length, true);
    c.setUint32(42, offset, true);
    dir.push(new Uint8Array(c.buffer), nameBytes);
    offset += 30 + nameBytes.length + data.length;
  }
  const dirSize = dir.reduce((s, x) => s + x.length, 0);
  const e = new DataView(new ArrayBuffer(22));
  e.setUint32(0, 0x06054b50, true); e.setUint16(8, entries.length, true); e.setUint16(10, entries.length, true);
  e.setUint32(12, dirSize, true); e.setUint32(16, offset, true);
  const all = [...parts, ...dir, new Uint8Array(e.buffer)];
  const out = new Uint8Array(all.reduce((s, x) => s + x.length, 0));
  let p = 0;
  for (const x of all) { out.set(x, p); p += x.length; }
  return out;
}

// ---- reading ----------------------------------------------------------------------------------------
const ENTITY = { amp: "&", lt: "<", gt: ">", quot: '"', apos: "'" };
const unescapeXml = (s) => s.replace(/&(#x[0-9a-f]+|#\d+|\w+);/gi, (m, e) =>
  e[0] === "#" ? String.fromCodePoint(e[1].toLowerCase() === "x" ? parseInt(e.slice(2), 16) : parseInt(e.slice(1), 10))
    : ENTITY[e] ?? m);
const attr = (tag, name) => { const m = tag.match(new RegExp(`\\s${name}="([^"]*)"`)); return m ? unescapeXml(m[1]) : null; };
const textOf = (xml) => [...xml.matchAll(/<t(?:\s[^>]*)?>([\s\S]*?)<\/t>/g)].map((m) => unescapeXml(m[1])).join("");

// Built-in number formats that Excel shows as dates (ECMA-376, 18.8.30), and custom formats with date parts.
const DATE_IDS = new Set([14, 15, 16, 17, 18, 19, 20, 21, 22, 27, 30, 36, 45, 46, 47, 50, 57]);
function isDateFormat(code) {
  const s = code.replace(/"[^"]*"|\[[^\]]*\]|\\./g, "");
  return /[dmy]/i.test(s) && !/^general$/i.test(s.trim());
}

function columnIndex(ref) {
  let n = 0;
  for (const ch of ref.match(/^[A-Z]+/)[0]) n = n * 26 + ch.charCodeAt(0) - 64;
  return n - 1;
}

function serialToIso(serial, date1904) {
  const base = date1904 ? Date.UTC(1904, 0, 1) : Date.UTC(1899, 11, 30);
  return new Date(base + Math.round(serial * 86400) * 1000).toISOString().slice(0, 10);
}

export async function readXlsx(buffer) {
  const files = await unzip(buffer);
  const get = (n) => (files[n] ? td.decode(files[n]) : "");
  const workbook = get("xl/workbook.xml");
  if (!workbook) throw new Error("not an .xlsx file");
  const date1904 = /<workbookPr[^>]*date1904="(1|true)"/.test(workbook);
  const rels = Object.fromEntries([...get("xl/_rels/workbook.xml.rels").matchAll(/<Relationship\b[^>]*>/g)]
    .map(([t]) => [attr(t, "Id"), attr(t, "Target")]));
  const shared = [...get("xl/sharedStrings.xml").matchAll(/<si>([\s\S]*?)<\/si>/g)].map((m) => textOf(m[1]));
  const styles = get("xl/styles.xml");
  const custom = Object.fromEntries([...styles.matchAll(/<numFmt\b[^>]*>/g)]
    .map(([t]) => [Number(attr(t, "numFmtId")), attr(t, "formatCode") || ""]));
  const xfs = (styles.match(/<cellXfs[^>]*>([\s\S]*?)<\/cellXfs>/) || ["", ""])[1];
  const dateStyle = [...xfs.matchAll(/<xf\b[^>]*>/g)].map(([t]) => {
    const id = Number(attr(t, "numFmtId") || 0);
    return DATE_IDS.has(id) || (id in custom && isDateFormat(custom[id]));
  });
  const sheets = [];
  for (const [t] of workbook.matchAll(/<sheet\b[^>]*>/g)) {
    const target = rels[attr(t, "r:id")] || "";
    const path = target.startsWith("/") ? target.slice(1) : `xl/${target.replace(/^\.\//, "")}`;
    const xml = get(path);
    const rows = [];
    for (const [rowTag, rowXml] of xml.matchAll(/<row\b[^>]*?(?:\/>|>([\s\S]*?)<\/row>)/g)) {
      // rows can skip numbers (empty rows are not written): put each one at its own row number
      const at = Number(attr(rowTag.match(/<row\b[^>]*>/)[0], "r")) || rows.length + 1;
      while (rows.length < at - 1) rows.push([]);
      const row = [];
      for (const m of (rowXml || "").matchAll(/<c\b([^>]*?)(?:\/>|>([\s\S]*?)<\/c>)/g)) {
        const a = m[1], inner = m[2] || "";
        const ref = attr(`<c ${a}>`, "r");
        const type = attr(`<c ${a}>`, "t") || "n";
        const style = Number(attr(`<c ${a}>`, "s") || 0);
        const raw = (inner.match(/<v>([\s\S]*?)<\/v>/) || [])[1];
        let value = "";
        if (type === "s") value = shared[Number(raw)] ?? "";
        else if (type === "inlineStr") value = textOf(inner);
        else if (type === "str" || type === "e") value = raw === undefined ? "" : unescapeXml(raw);
        else if (type === "b") value = raw === "1";
        else if (type === "d") value = raw === undefined ? "" : String(raw).slice(0, 10);   // ISO date cell
        else if (raw !== undefined) {
          const n = Number(raw);
          value = dateStyle[style] ? serialToIso(n, date1904) : n;
        }
        const col = ref ? columnIndex(ref) : row.length;
        while (row.length < col) row.push("");
        row[col] = value;
      }
      rows.push(row);
    }
    sheets.push({ name: attr(t, "name"), rows });
  }
  return sheets;
}

// ---- writing ----------------------------------------------------------------------------------------
const escapeXml = (s) => String(s).replace(/[<>&"]/g, (c) => ({ "<": "&lt;", ">": "&gt;", "&": "&amp;", '"': "&quot;" })[c])
  .replace(/[\u0000-\u0008\u000b\u000c\u000e-\u001f]/g, "");
const columnName = (i) => { let s = ""; for (i += 1; i > 0; i = Math.floor((i - 1) / 26)) s = String.fromCharCode(65 + ((i - 1) % 26)) + s; return s; };

// styles: 0 plain, 1 bold header with a light fill, 2 number with two decimals, 3 date
const STYLES = `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><numFmts count="1"><numFmt numFmtId="164" formatCode="#,##0.00"/></numFmts><fonts count="2"><font><sz val="11"/><name val="Calibri"/></font><font><b/><sz val="11"/><name val="Calibri"/></font></fonts><fills count="3"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill><fill><patternFill patternType="solid"><fgColor rgb="FFF2F2F7"/></patternFill></fill></fills><borders count="1"><border/></borders><cellStyleXfs count="1"><xf/></cellStyleXfs><cellXfs count="4"><xf/><xf fontId="1" fillId="2" applyFont="1" applyFill="1"/><xf numFmtId="164" applyNumberFormat="1"/><xf numFmtId="14" applyNumberFormat="1"/></cellXfs><cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles></styleSheet>`;

function sheetXml({ rows, widths = [], header = true }) {
  const isoDate = /^\d{4}-\d{2}-\d{2}$/;
  const cols = widths.length
    ? `<cols>${widths.map((w, i) => `<col min="${i + 1}" max="${i + 1}" width="${w}" customWidth="1"/>`).join("")}</cols>` : "";
  const body = rows.map((row, r) => `<row r="${r + 1}">${row.map((v, c) => {
    const ref = `${columnName(c)}${r + 1}`;
    if (v === null || v === undefined || v === "") return "";
    if (header && r === 0) return `<c r="${ref}" s="1" t="inlineStr"><is><t>${escapeXml(v)}</t></is></c>`;
    if (typeof v === "number" && Number.isFinite(v)) return `<c r="${ref}"${Number.isInteger(v) ? "" : ' s="2"'}><v>${v}</v></c>`;
    if (typeof v === "boolean") return `<c r="${ref}" t="b"><v>${v ? 1 : 0}</v></c>`;
    if (typeof v === "string" && isoDate.test(v)) {
      const serial = (Date.UTC(+v.slice(0, 4), +v.slice(5, 7) - 1, +v.slice(8, 10)) - Date.UTC(1899, 11, 30)) / 86400000;
      return `<c r="${ref}" s="3"><v>${serial}</v></c>`;
    }
    return `<c r="${ref}" t="inlineStr"><is><t xml:space="preserve">${escapeXml(v)}</t></is></c>`;
  }).join("")}</row>`).join("");
  const last = `${columnName(Math.max(0, ...rows.map((r) => r.length)) - 1)}${rows.length}`;
  const freeze = header ? `<sheetViews><sheetView workbookViewId="0"><pane ySplit="1" topLeftCell="A2" activePane="bottomLeft" state="frozen"/></sheetView></sheetViews>` : "";
  const filter = header && rows.length > 1 ? `<autoFilter ref="A1:${last}"/>` : "";
  return `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">${freeze}${cols}<sheetData>${body}</sheetData>${filter}</worksheet>`;
}

export function writeXlsx(sheets) {
  const safe = sheets.map((s, i) => ({ ...s, name: escapeXml(String(s.name || `Sheet${i + 1}`).replace(/[\\/?*[\]:]/g, " ").slice(0, 31)) }));
  const entries = [
    ["[Content_Types].xml", `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>${safe.map((_, i) => `<Override PartName="/xl/worksheets/sheet${i + 1}.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>`).join("")}</Types>`],
    ["_rels/.rels", `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>`],
    ["xl/workbook.xml", `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets>${safe.map((s, i) => `<sheet name="${s.name}" sheetId="${i + 1}" r:id="rId${i + 1}"/>`).join("")}</sheets></workbook>`],
    ["xl/_rels/workbook.xml.rels", `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">${safe.map((_, i) => `<Relationship Id="rId${i + 1}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet${i + 1}.xml"/>`).join("")}<Relationship Id="rId${safe.length + 1}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/></Relationships>`],
    ["xl/styles.xml", STYLES],
    ...safe.map((s, i) => [`xl/worksheets/sheet${i + 1}.xml`, sheetXml(s)]),
  ];
  return zip(entries);
}
