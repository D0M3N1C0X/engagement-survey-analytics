// strumenti-design 1.1.1 · i18n.js
// Italian and English in the same page. Text lives in two dictionaries; elements carry data-i18n="key" (text) or
// data-i18n-attr="attribute:key" (for aria-label, placeholder, title). The choice is remembered on this device.
//
//   const i18n = createI18n({ it: {...}, en: {...} }, "it");
//   i18n.t("key", { n: 3 })   i18n.lang   i18n.set("en")   i18n.onChange(fn)
//   i18n.number(x, digits)    i18n.money(x)    i18n.percent(x, digits)

const KEY = "strumenti.lingua";

export function createI18n(dicts, fallback = "it") {
  let lang = fallback;
  try {
    const stored = localStorage.getItem(KEY);
    const asked = new URLSearchParams(location.search).get("lang");
    lang = [asked, stored].find((l) => l && dicts[l]) || fallback;
  } catch { /* storage blocked */ }
  const listeners = [];
  const locale = () => (lang === "it" ? "it-IT" : "en-GB");
  const t = (key, vars = {}) => String(dicts[lang]?.[key] ?? dicts[fallback]?.[key] ?? key)
    .replace(/\{(\w+)\}/g, (_, k) => (k in vars ? vars[k] : `{${k}}`));
  function apply(root = document) {
    document.documentElement.lang = lang;
    root.querySelectorAll("[data-i18n]").forEach((el) => { el.textContent = t(el.dataset.i18n); });
    root.querySelectorAll("[data-i18n-html]").forEach((el) => { el.innerHTML = t(el.dataset.i18nHtml); });
    root.querySelectorAll("[data-i18n-attr]").forEach((el) => {
      for (const pair of el.dataset.i18nAttr.split(";")) {
        const [attr, key] = pair.split(":").map((s) => s.trim());
        if (attr && key) el.setAttribute(attr, t(key));
      }
    });
    root.querySelectorAll("[data-lang-switch] button").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.lang === lang)));
  }
  function set(next) {
    if (!dicts[next] || next === lang) return;
    lang = next;
    try { localStorage.setItem(KEY, lang); } catch { /* fine */ }
    apply();
    listeners.forEach((fn) => fn(lang));
  }
  document.querySelectorAll("[data-lang-switch] button").forEach((b) => b.addEventListener("click", () => set(b.dataset.lang)));
  const fmt = (x, o) => new Intl.NumberFormat(locale(), { useGrouping: "always", ...o }).format(x);
  return {
    get lang() { return lang; }, t, set, apply,
    onChange: (fn) => listeners.push(fn),
    number: (x, d = 0) => fmt(x, { minimumFractionDigits: d, maximumFractionDigits: d }),
    money: (x, d = 2) => {
      const n = fmt(Math.abs(x), { minimumFractionDigits: d, maximumFractionDigits: d });
      return `${x < 0 ? "−" : ""}${lang === "it" ? `${n} €` : `€${n}`}`;
    },
    percent: (x, d = 1) => fmt(x, { style: "percent", minimumFractionDigits: d, maximumFractionDigits: d }),
  };
}
