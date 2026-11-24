"""
deliverables/engagement_survey.xlsx - the read-out's core figures as live formulas, reconciled with Python.

The pipeline itself stays standard-library only. This builder is the one place with packages (openpyxl to
write the file, excel-twin to keep it byte-stable and to check it), run on its own:

    pip install -r tools/requirements.txt
    python3 tools/build_workbook.py
    excel-twin recalc deliverables/engagement_survey.xlsx build/
    excel-twin check build/engagement_survey.xlsx

Every invitee is a row on the Data sheet; each respondent's favourable share per dimension is a formula
there, and the other sheets average those shares the way the read-out does: dimension scores overall and by
department, response rates, the eNPS, and the team table that sets engagement against resignations. The
Reconciliation sheet holds the Python values and checks each formula against them. Team identifiers appear
because the data is synthetic; a workbook built on a real survey would keep only the department level.
"""

from __future__ import annotations

import sys
from pathlib import Path

from openpyxl import Workbook
from openpyxl.formatting.rule import CellIsRule
from openpyxl.styles import Alignment, Font, PatternFill

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import analysis_turnover as turn  # noqa: E402
from statlib import mean  # noqa: E402
from surveylib import (DIMENSION_ORDER, MIN_GROUP, driver_items, enps, load_instrument, load_responses,  # noqa: E402
                       outcome_items, respondent_favourable)

OUT = ROOT / "deliverables" / "engagement_survey.xlsx"
BLUE, GREEN, INK, MUTED = "0B57D0", "137333", "1D1D1F", "6E6E73"
BASE = ["response_id", "team_id", "department", "responded", "enps"]


def letter(i: int) -> str:
    s, i = "", i + 1
    while i:
        i, rem = divmod(i - 1, 26)
        s = chr(65 + rem) + s
    return s


def put(ws, ref, value, *, bold=False, color=INK, fmt=None, size=11, italic=False):
    c = ws[ref]
    c.value = value
    c.font = Font(bold=bold, color=color, size=size, italic=italic)
    if fmt:
        c.number_format = fmt
    return c


def head(ws, row, labels, start=1):
    for i, text in enumerate(labels):
        c = ws.cell(row=row, column=start + i, value=text)
        c.font = Font(bold=True)
        c.fill = PatternFill("solid", fgColor="F2F2F7")
        c.alignment = Alignment(wrap_text=True, vertical="top")


def widths(ws, spec):
    for col, w in spec.items():
        ws.column_dimensions[col].width = w


def title(ws, text, sub):
    put(ws, "A1", text, bold=True, size=14)
    put(ws, "A2", sub, color=MUTED, italic=True)


class Builder:
    def __init__(self):
        self.rows = load_responses()
        instrument = load_instrument()
        self.dims = {d: driver_items(instrument)[d] for d in DIMENSION_ORDER}
        self.outcome = outcome_items(instrument)
        self.sets = {"Engagement": self.outcome, **self.dims}
        self.items = [i for items in self.sets.values() for i in items]
        self.cols = {name: letter(i) for i, name in enumerate(BASE + self.items + list(self.sets))}
        self.last = len(self.rows) + 1
        self.checks: list[tuple[str, str, object, str]] = []
        self.wb = Workbook()

    def rng(self, name):
        return f"Data!${self.cols[name]}$2:${self.cols[name]}${self.last}"

    def check(self, area, item, value, ref):
        self.checks.append((area, item, value, ref))

    def data(self):
        ws = self.wb.create_sheet("Data")
        head(ws, 1, BASE + self.items + [f"{s} (favourable share)" for s in self.sets])
        for r, row in enumerate(self.rows, start=2):
            values = [row["response_id"], row["team_id"], row["department"], int(row["responded"]), row["enps"]]
            values += [row[i] for i in self.items]
            for i, v in enumerate(values):
                ws.cell(row=r, column=i + 1, value=v).font = Font(color=BLUE)
            for k, (name, items) in enumerate(self.sets.items()):
                first, last = self.cols[items[0]], self.cols[items[-1]]
                rngr = f"{first}{r}:{last}{r}"
                ws.cell(row=r, column=len(BASE) + len(self.items) + k + 1,
                        value=f'=IF(AND(D{r}=1,COUNT({rngr})>0),COUNTIF({rngr},">=4")/COUNT({rngr}),"")')
        ws.freeze_panes = "B2"
        for i in range(len(BASE) + len(self.items) + len(self.sets)):
            ws.column_dimensions[letter(i)].width = 11

    def scores(self):
        ws = self.wb.create_sheet("Scores")
        title(ws, "Favourable scores by dimension and department",
              "Each respondent's share of favourable answers (4 or 5), averaged over respondents.")
        depts = sorted({r["department"] for r in self.rows})
        head(ws, 4, ["Dimension", "Company"] + depts)
        for k, (name, items) in enumerate(self.sets.items()):
            r = 5 + k
            put(ws, f"A{r}", name, bold=name == "Engagement")
            put(ws, f"B{r}", f'=AVERAGE({self.rng(name)})', fmt="0.0%")
            answered = [x for x in self.rows if x["responded"]]
            value = mean([s for x in answered if (s := respondent_favourable(x, items)) is not None])
            self.check("Scores", f"{name}: company", value, f"Scores!B{r}")
            for j, d in enumerate(depts):
                col = letter(2 + j)
                put(ws, f"{col}{r}", f'=AVERAGEIFS({self.rng(name)},{self.rng("department")},{col}$4)', fmt="0.0%")
                v = mean([s for x in answered if x["department"] == d and (s := respondent_favourable(x, items)) is not None])
                self.check("Scores", f"{name}: {d}", v, f"Scores!{col}{r}")
        widths(ws, {"A": 26, "B": 11, **{letter(2 + j): 15 for j in range(len(depts))}})

    def participation(self):
        ws = self.wb.create_sheet("Participation")
        title(ws, "Response rate and eNPS", "Invitees are every row of the Data sheet; respondents have responded = 1.")
        depts = sorted({r["department"] for r in self.rows})
        head(ws, 4, ["Department", "Invited", "Responded", "Response rate"])
        for k, d in enumerate(["Company"] + depts):
            r = 5 + k
            put(ws, f"A{r}", d, bold=d == "Company")
            crit = "" if d == "Company" else f',{self.rng("department")},A{r}'
            put(ws, f"B{r}", f'=COUNTIFS({self.rng("response_id")},"<>"{crit})')
            put(ws, f"C{r}", f'=COUNTIFS({self.rng("responded")},1{crit})')
            put(ws, f"D{r}", f"=C{r}/B{r}", fmt="0.0%")
            group = self.rows if d == "Company" else [x for x in self.rows if x["department"] == d]
            self.check("Participation", f"{d}: response rate", sum(x["responded"] for x in group) / len(group),
                       f"Participation!D{r}")
        r = 6 + len(depts) + 1
        e = self.rng("enps")
        put(ws, f"A{r}", "eNPS", bold=True)
        put(ws, f"B{r}", f'=(COUNTIFS({e},">=9",{self.rng("responded")},1)-COUNTIFS({e},"<=6",{self.rng("responded")},1))'
                         f'/COUNTIFS({e},">=0",{self.rng("responded")},1)*100', fmt="0.0")
        self.check("Participation", "eNPS", enps([x["enps"] for x in self.rows if x["responded"]])["enps"], f"Participation!B{r}")
        widths(ws, {"A": 24, "B": 10, "C": 11, "D": 14})

    def teams(self):
        ws = self.wb.create_sheet("Teams and exits")
        title(ws, "Team engagement against resignations in the twelve months after fieldwork",
              f"Teams with at least {MIN_GROUP} respondents. Quartiles rank teams by engagement, ties broken by team id.")
        frame, _ = turn.team_frame()
        frame = sorted(frame, key=lambda t: t["team_id"])
        n = len(frame)
        head(ws, 4, ["Team", "Respondents", "Engagement", "Headcount", "Resigned", "Rank", "Quartile"])
        first, last = 5, 4 + n
        for k, t in enumerate(frame):
            r = first + k
            put(ws, f"A{r}", t["team_id"])
            put(ws, f"B{r}", f'=COUNTIFS({self.rng("team_id")},A{r},{self.rng("responded")},1)')
            put(ws, f"C{r}", f'=AVERAGEIFS({self.rng("Engagement")},{self.rng("team_id")},A{r})', fmt="0.0%")
            put(ws, f"D{r}", t["headcount"], color=BLUE)
            put(ws, f"E{r}", t["exits"], color=BLUE)
            put(ws, f"F{r}", f'=COUNTIF($C${first}:$C${last},"<"&C{r})+COUNTIFS($C${first}:$C${last},C{r},$A${first}:$A${last},"<"&A{r})+1')
            put(ws, f"G{r}", f"=INT((F{r}-1)*4/{n})+1")
            self.check("Teams", f"{t['team_id']}: engagement", t["engagement"], f"'Teams and exits'!C{r}")
        q = turn.quartiles(frame)
        r0 = last + 3
        head(ws, r0, ["Quartile", "Teams", "Headcount", "Resigned", "Rate"])
        for k, row in enumerate(q):
            r = r0 + 1 + k
            put(ws, f"A{r}", k + 1)
            put(ws, f"B{r}", f"=COUNTIF($G${first}:$G${last},A{r})")
            put(ws, f"C{r}", f"=SUMIFS($D${first}:$D${last},$G${first}:$G${last},A{r})")
            put(ws, f"D{r}", f"=SUMIFS($E${first}:$E${last},$G${first}:$G${last},A{r})")
            put(ws, f"E{r}", f"=D{r}/C{r}", fmt="0.0%")
            self.check("Teams", f"Quartile {k + 1}: resigned", row["exits"], f"'Teams and exits'!D{r}")
            self.check("Teams", f"Quartile {k + 1}: rate", row["rate"], f"'Teams and exits'!E{r}")
        widths(ws, {"A": 10, "B": 12, "C": 12, "D": 11, "E": 10, "F": 8, "G": 9})

    def reconciliation(self):
        ws = self.wb.create_sheet("Reconciliation")
        title(ws, "Reconciliation: workbook formulas against the Python pipeline",
              "Column D was written by tools/build_workbook.py from the Python results; column E is the live formula.")
        head(ws, 6, ["Area", "Item", "", "Python value", "Workbook value", "Difference", "Match"])
        first, last = 7, 6 + len(self.checks)
        put(ws, "B3", (f'=IF(COUNTIF(G{first}:G{last},"No")=0,"All "&COUNTA(B{first}:B{last})&" checks match",'
                       f'COUNTIF(G{first}:G{last},"No")&" of "&COUNTA(B{first}:B{last})&" checks do not match")'),
            bold=True, size=12)
        for r, (area, item, value, ref) in enumerate(self.checks, start=first):
            put(ws, f"A{r}", area)
            put(ws, f"B{r}", item)
            fmt = "0.000000" if isinstance(value, float) else None
            put(ws, f"D{r}", value, color=BLUE, fmt=fmt)
            put(ws, f"E{r}", f"={ref}", color=GREEN, fmt=fmt)
            put(ws, f"F{r}", f'=IF(AND(ISNUMBER(D{r}),ISNUMBER(E{r})),E{r}-D{r},"")', fmt="0.0E+00")
            put(ws, f"G{r}", (f'=IF(AND(ISNUMBER(D{r}),ISNUMBER(E{r})),IF(ABS(E{r}-D{r})<=1E-9*MAX(1,ABS(D{r})),"Yes","No"),'
                              f'IF(D{r}=E{r},"Yes","No"))'))
        for text, colour in (("Yes", "D5ECDC"), ("No", "F5C6C2")):
            ws.conditional_formatting.add(f"G{first}:G{last}", CellIsRule(operator="equal", formula=[f'"{text}"'],
                                                                         fill=PatternFill("solid", fgColor=colour)))
        ws.freeze_panes = "A7"
        widths(ws, {"A": 14, "B": 46, "C": 3, "D": 16, "E": 16, "F": 12, "G": 8})

    def cover(self):
        ws = self.wb.active
        ws.title = "Cover"
        widths(ws, {"A": 3, "B": 22, "C": 100})
        put(ws, "B2", "Engagement survey: the core figures, as formulas", bold=True, size=18)
        put(ws, "B3", "Voice 2026, a synthetic group of 3,800 invitees in 149 teams", color=MUTED, size=12)
        for i, (name, text) in enumerate({
            "Scores": "Favourable scores by dimension, company and department, averaged over respondents.",
            "Participation": "Response rate by department and the eNPS.",
            "Teams and exits": "Each team's engagement against its resignations in the next twelve months, by quartile.",
            "Data": "One row per invitee: answers in blue, each respondent's favourable shares as formulas.",
            "Reconciliation": "Every figure above checked against the Python pipeline behind the read-out.",
        }.items(), start=6):
            put(ws, f"B{i}", name, color=GREEN)
            put(ws, f"C{i}", text)
        put(ws, "B12", "Check", bold=True)
        put(ws, "C12", "=Reconciliation!B3", bold=True, color=GREEN)
        put(ws, "B14", "The data is synthetic, generated by src/generate_survey.py with a fixed seed.", color=MUTED, italic=True)

    def build(self) -> Path:
        self.cover()
        self.scores()
        self.participation()
        self.teams()
        self.data()
        self.reconciliation()
        OUT.parent.mkdir(exist_ok=True)
        self.wb.save(OUT)
        from excel_twin.determinism import normalise
        normalise(OUT)
        return OUT


if __name__ == "__main__":
    b = Builder()
    path = b.build()
    print(f"{path.relative_to(ROOT)}: {len(b.checks)} figures to reconcile")
