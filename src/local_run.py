"""Run the survey analysis locally on a client's CSV export."""

from __future__ import annotations

import argparse
import csv
import os
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
BASE_RESPONSE_FIELDS = {
    "response_id", "team_id", "department", "country", "job_level", "tenure_band",
    "work_model", "shift_worker", "responded", "submitted_date", "enps",
}
TEAM_FIELDS = {"team_id", "department", "team_size"}
INSTRUMENT_FIELDS = {"item_id", "dimension", "wording", "type"}
COMMENT_FIELDS = {"comment_id", "response_id", "question", "comment_text"}
COMMENT_QUESTIONS = {"what_to_change", "what_works"}
REQUIRED_SEGMENTS = {"department", "country", "job_level", "tenure_band", "work_model"}
SUPPORTED_DIMENSIONS = {
    "Manager Support", "Career Growth", "Recognition", "Workload & Wellbeing",
    "Leadership & Direction", "Pay & Benefits", "Inclusion & Belonging", "Tools & Process",
}


class DatasetError(ValueError):
    """Input files do not match the documented local CSV contract."""


def _read_csv(path: Path, required: bool = True) -> tuple[list[str], list[dict[str, str]]]:
    if not path.exists():
        if required:
            raise DatasetError(f"Required file is missing: {path.name}")
        return [], []
    try:
        with path.open(encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            headers = reader.fieldnames or []
            if len(headers) != len(set(headers)):
                raise DatasetError(f"{path.name} contains duplicate column headers")
            rows = list(reader)
            if any(None in row or any(value is None for value in row.values()) for row in rows):
                raise DatasetError(f"{path.name} has rows with a different number of fields than its header")
            return headers, rows
    except csv.Error as exc:
        raise DatasetError(f"Could not parse {path.name}: {exc}") from exc
    except UnicodeError as exc:
        raise DatasetError(f"{path.name} must use UTF-8 or UTF-8 with a byte-order mark") from exc
    except OSError as exc:
        raise DatasetError(f"Could not read {path.name}") from exc


def _require_fields(path: str, actual: list[str], required: set[str]) -> None:
    missing = sorted(required - set(actual))
    if missing:
        raise DatasetError(f"{path} is missing required columns: {', '.join(missing)}")


def _outside_repo(path: Path, label: str) -> None:
    if path == ROOT or ROOT in path.parents:
        raise DatasetError(f"{label} must be outside this repository to avoid accidental publication")


def validate_dataset(data_dir: Path) -> dict[str, int]:
    """Validate the documented one-row-per-invitee CSV schema before analysis."""
    data_dir = data_dir.expanduser().resolve()
    if not data_dir.is_dir():
        raise DatasetError("The input path must be a directory containing the survey CSV files")
    _outside_repo(data_dir, "Input data")

    instrument_headers, instrument = _read_csv(data_dir / "survey_instrument.csv")
    _require_fields("survey_instrument.csv", instrument_headers, INSTRUMENT_FIELDS)
    item_ids = [row["item_id"].strip() for row in instrument]
    if not item_ids or any(not item_id for item_id in item_ids) or len(item_ids) != len(set(item_ids)):
        raise DatasetError("survey_instrument.csv must have unique, non-empty item_id values")
    dimensions = {row["dimension"].strip() for row in instrument if row["type"].strip() == "driver"}
    types = {row["type"].strip() for row in instrument}
    if types - {"driver", "outcome"}:
        raise DatasetError("Instrument type must be driver or outcome")

    if SUPPORTED_DIMENSIONS - dimensions:
        missing = sorted(SUPPORTED_DIMENSIONS - dimensions)
        raise DatasetError("The instrument needs driver items for all supported dimensions: "
                           + ", ".join(missing))
    outcomes = [row["item_id"].strip() for row in instrument
                if row["type"].strip() == "outcome" and row["item_id"].strip() != "enps"]
    if len(outcomes) < 2:
        raise DatasetError("The instrument needs at least two outcome items besides eNPS")

    response_headers, responses = _read_csv(data_dir / "survey_responses.csv")
    _require_fields("survey_responses.csv", response_headers, BASE_RESPONSE_FIELDS | set(item_ids))
    if not responses:
        raise DatasetError("survey_responses.csv contains no invitees")

    team_headers, teams = _read_csv(data_dir / "teams.csv")
    _require_fields("teams.csv", team_headers, TEAM_FIELDS)
    team_by_id = {}
    for row in teams:
        team_id = row["team_id"].strip()
        if not team_id or team_id in team_by_id:
            raise DatasetError("teams.csv must have unique, non-empty team_id values")
        try:
            team_size = int(row["team_size"])
            manager_tenure = int(row["manager_tenure_months"] or 0) if "manager_tenure_months" in row else 0
        except (TypeError, ValueError) as exc:
            raise DatasetError(f"Team {team_id} has invalid team_size or manager_tenure_months") from exc
        if team_size < 0 or manager_tenure < 0:
            raise DatasetError(f"Team {team_id} has a negative size or manager tenure")
        if not row["department"].strip():
            raise DatasetError(f"Team {team_id} is missing department")
        team_by_id[team_id] = team_size
    if not team_by_id:
        raise DatasetError("teams.csv contains no teams")

    response_by_id = {}
    team_counts: Counter[str] = Counter()
    responded_count = 0
    for line, row in enumerate(responses, start=2):
        response_id = row["response_id"].strip()
        team_id = row["team_id"].strip()
        if not response_id or response_id in response_by_id:
            raise DatasetError(f"survey_responses.csv row {line}: response_id is blank or duplicated")
        if team_id not in team_by_id:
            raise DatasetError(f"survey_responses.csv row {line}: team_id is not in teams.csv")
        if any(not row[field].strip() for field in REQUIRED_SEGMENTS):
            raise DatasetError(f"survey_responses.csv row {line}: a required segment is blank")
        if row["responded"].strip() not in {"0", "1"} or row["shift_worker"].strip() not in {"0", "1"}:
            raise DatasetError(f"survey_responses.csv row {line}: responded and shift_worker must be 0 or 1")
        if row["enps"].strip():
            try:
                enps_score = int(row["enps"])
            except ValueError as exc:
                raise DatasetError(f"survey_responses.csv row {line}: eNPS is not an integer") from exc
            if not 0 <= enps_score <= 10:
                raise DatasetError(f"survey_responses.csv row {line}: eNPS must be from 0 to 10")
        for item_id in item_ids:
            if item_id == "enps":
                continue
            value = row[item_id].strip()
            if value:
                try:
                    score = int(value)
                except ValueError as exc:
                    raise DatasetError(f"survey_responses.csv row {line}: {item_id} is not an integer") from exc
                if not 1 <= score <= 5:
                    raise DatasetError(f"survey_responses.csv row {line}: {item_id} must be from 1 to 5")
        if row["responded"].strip() == "1":
            responded_count += 1
            if not any(row[item_id].strip() for item_id in outcomes):
                raise DatasetError(f"survey_responses.csv row {line}: respondent has no outcome answers")
        response_by_id[response_id] = row
        team_counts[team_id] += 1

    for team_id, expected in team_by_id.items():
        if team_counts[team_id] != expected:
            raise DatasetError(f"Team {team_id}: team_size is {expected}, but the response file has "
                               f"{team_counts[team_id]} invitees")
    if responded_count < 5:
        raise DatasetError("At least five respondents are required for the reporting threshold")

    comment_path = data_dir / "survey_comments.csv"
    _comment_headers, comments = _read_csv(comment_path, required=False)
    if comment_path.exists():
        _require_fields("survey_comments.csv", _comment_headers, COMMENT_FIELDS)
        comment_ids = set()
        for line, row in enumerate(comments, start=2):
            comment_id = row["comment_id"].strip()
            response_id = row["response_id"].strip()
            if not comment_id or comment_id in comment_ids:
                raise DatasetError(f"survey_comments.csv row {line}: comment_id is blank or duplicated")
            if response_id not in response_by_id or response_by_id[response_id]["responded"].strip() != "1":
                raise DatasetError(f"survey_comments.csv row {line}: response_id is not a respondent")
            if row["question"].strip() not in COMMENT_QUESTIONS:
                raise DatasetError(f"survey_comments.csv row {line}: unsupported comment question")
            if not row["comment_text"].strip():
                raise DatasetError(f"survey_comments.csv row {line}: comment_text is blank")
            comment_ids.add(comment_id)

    truth_path = data_dir / "comment_themes_truth.csv"
    if truth_path.exists():
        truth_headers, truth_rows = _read_csv(truth_path)
        _require_fields("comment_themes_truth.csv", truth_headers,
                        {"comment_id", "true_themes", "true_tone"})
        comment_ids = {row["comment_id"].strip() for row in comments}
        truth_ids = [row["comment_id"].strip() for row in truth_rows]
        if len(truth_ids) != len(set(truth_ids)):
            raise DatasetError("comment_themes_truth.csv must have unique comment_id values")
        if any(comment_id not in comment_ids for comment_id in truth_ids):
            raise DatasetError("comment_themes_truth.csv references an unknown comment_id")
        if any(row["true_tone"].strip() not in {"positive", "negative", "mixed"}
               for row in truth_rows):
            raise DatasetError("comment_themes_truth.csv true_tone must be positive, negative or mixed")

    return {"invitees": len(responses), "respondents": responded_count, "comments": len(comments)}


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Analyse a survey from local CSV files. No files are uploaded."
    )
    parser.add_argument("--data-dir", required=True,
                        help="directory containing the documented survey CSV files")
    parser.add_argument("--output-dir", required=True,
                        help="new or empty directory outside the repository for local results")
    parser.add_argument("--survey-name", default="Local engagement survey")
    parser.add_argument("--field-window", default="Not provided")
    parser.add_argument("--report-only", action="store_true",
                        help="write the aggregate report and charts without the interactive HTML")
    args = parser.parse_args()

    data_dir = Path(args.data_dir).expanduser().resolve()
    output_dir = Path(args.output_dir).expanduser().resolve()
    summary = validate_dataset(data_dir)
    _outside_repo(output_dir, "Output directory")
    if output_dir.exists() and not output_dir.is_dir():
        raise DatasetError("The output path exists but is not a directory")
    if output_dir.exists() and any(output_dir.iterdir()):
        raise DatasetError("The output directory must be new or empty; existing files are left untouched")
    output_dir.mkdir(parents=True, exist_ok=True)

    os.environ["SURVEY_DATA_DIR"] = str(data_dir)
    os.environ["SURVEY_OUTPUT_DIR"] = str(output_dir)
    os.environ["SURVEY_PRIVATE_MODE"] = "1"
    os.environ["SURVEY_NAME"] = args.survey_name
    os.environ["SURVEY_FIELD_WINDOW"] = args.field_window
    sys.path.insert(0, str(SRC))

    import run_all

    print(f"Validated local dataset: {summary['respondents']:,}/{summary['invitees']:,} respondents; "
          f"comments {'present' if summary['comments'] else 'not supplied'}")
    run_all.run_pipeline(generate_synthetic=False, write_dashboard=not args.report_only)
    print(f"Private outputs written to {output_dir}")
    if args.report_only:
        print("Report-only mode: no interactive HTML dashboard was written.")
    else:
        print("The HTML dashboard contains respondent-level survey values; keep it in an approved, "
              "access-controlled location and do not publish it.")


if __name__ == "__main__":
    try:
        main()
    except DatasetError as exc:
        print(f"Input error: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc
