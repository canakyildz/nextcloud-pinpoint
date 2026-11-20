"""Evaluate Pinpoint on the synthetic dataset.

Two modes:

  oracle  The model is replaced by the ground truth, with known faults injected on purpose: invented
          values, values that contradict their quote, quotes that are not in the document, fields
          swapped with each other. It measures the verification layer alone. Every fault has a
          positive control (the correct answer), so a layer that flags everything fails as surely
          as one that flags nothing. Deterministic; runs in CI with thresholds.

  openai  A real model behind any OpenAI-compatible endpoint (OpenAI, LocalAI, Ollama, vLLM). It
          measures the whole pipeline: field accuracy, and the number that matters most, how many
          wrong values were marked verified ("confidently wrong").

    python evals/run.py oracle --check
    python evals/run.py openai --base-url http://localhost:11434/v1 --model qwen2.5:7b --report evals/results/qwen2.5-7b.md
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import random
import sys
import time
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "ex_app" / "lib"))

from pinpoint.document import (
    LoadOptions,
    document_text,
    load_document,
    ocr_available,
)
from pinpoint.model import FieldResult, FieldStatus, FieldType, Schema
from pinpoint.pipeline import PipelineOptions, extract_from_document
from pinpoint.schemas import template
from pinpoint.values import detect_conventions, is_ambiguous_date, normalize_text

DATASET = Path(__file__).resolve().parent / "dataset"

FAULTS = (
    "correct",
    "wrong_page",
    "hallucinated",
    "contradicts_quote",
    "near_miss",
    "quote_not_in_document",
    "missing_quote",
    "invented_field",
    "swapped_amounts",
)
"""`correct` and `wrong_page` are positive controls: the answer is right and should be verified.
The others are wrong answers that must not be verified."""

POSITIVE = frozenset({"correct", "wrong_page"})

# Minimums enforced by `oracle --check` in CI.
THRESHOLDS = {
    "positive_verified_rate": 0.97,
    "fault_caught_rate": 0.97,
}


@dataclass
class Case:
    name: str
    path: Path
    kind: str
    schema: Schema
    truth: dict[str, Any]
    date_order_known: bool = True
    """False when the document's dates could be read day-first or month-first."""
    text: str = ""
    """The document's text as Pinpoint read it (OCR output for scans), normalised."""


def load_cases(include_scans: bool) -> list[Case]:
    manifest = json.loads((DATASET / "manifest.json").read_text())
    cases = []
    for entry in manifest:
        if entry["kind"] == "scan" and not include_scans:
            continue
        truth = json.loads((DATASET / f"{entry['name']}.json").read_text())
        cases.append(Case(entry["name"], DATASET / entry["file"], entry["kind"], template(truth["template"]), truth))
    return cases


def _perturb_number(value: float, rng: random.Random) -> float:
    digits = list(f"{value:.2f}")
    positions = [i for i, c in enumerate(digits) if c.isdigit()]
    for _ in range(10):
        i, j = sorted(rng.sample(positions, 2))
        if digits[i] != digits[j]:
            digits[i], digits[j] = digits[j], digits[i]
            return float("".join(digits))
    return round(value + 1.11, 2)


class OracleModel:
    """Answers from the ground truth, with one fault applied to one field."""

    def __init__(self, truth: dict[str, Any], fault: str, target: str | None, rng: random.Random) -> None:
        self.truth, self.fault, self.target, self.rng = truth, fault, target, rng

    async def complete(self, prompt: str) -> str:
        fields: dict[str, dict[str, Any]] = {}
        for key, t in self.truth["fields"].items():
            fields[key] = {"value": t["value"], "quote": t["quote"], "page": t.get("page")}
        f = fields.get(self.target) if self.target else None
        if self.fault == "wrong_page" and f:
            f["page"] = (f["page"] or 1) + 1
        elif self.fault == "hallucinated" and f:
            if isinstance(f["value"], float):
                f["value"] = round(f["value"] * 1.37 + 3.21, 2)
                f["quote"] = f"Total amount {f['value']:.2f}"
            else:
                f["value"] = (
                    f"{f['value']} Holdings" if isinstance(f["value"], str) and "-" not in f["value"] else "2026-12-31"
                )
                f["quote"] = f"Issued by {f['value']}"
        elif self.fault == "contradicts_quote" and f:
            if isinstance(f["value"], float):
                f["value"] = _perturb_number(f["value"], self.rng)
            elif isinstance(f["value"], str) and len(f["value"]) == 10 and f["value"][4] == "-":
                d = date.fromisoformat(f["value"])
                f["value"] = d.replace(day=d.day % 28 + 1).isoformat()
            else:
                f["value"] = "Northwind Traders" if f["value"] != "Northwind Traders" else "Contoso"
        elif self.fault == "near_miss" and f:
            # One character, one cent or one day off, with the genuine quote: the hardest wrong answer.
            if isinstance(f["value"], float):
                f["value"] = round(f["value"] + 0.01, 2)
            elif isinstance(f["value"], str) and len(f["value"]) == 10 and f["value"][4] == "-":
                f["value"] = (date.fromisoformat(f["value"]) + timedelta(days=1)).isoformat()
            else:
                f["value"] = f["value"][:-1] + ("7" if f["value"][-1] != "7" else "8")
        elif self.fault == "quote_not_in_document" and f:
            f["quote"] = f"{f['quote']} (see attachment B)" if f["quote"] else "see attachment B"
            f["quote"] = "Ref. " + f["quote"].upper()[::-1]
        elif self.fault == "missing_quote" and f:
            f["quote"] = None
        elif self.fault == "invented_field" and f:
            f["value"] = "2026-12-31" if "date" in self.target else "Invented value 4711"
            f["quote"] = "Payable on 31 December 2026" if "date" in self.target else "Invented value 4711"
            f["page"] = 1
        elif self.fault == "swapped_amounts":
            a, b = fields["total"], fields["tax"]
            a["value"], b["value"] = b["value"], a["value"]
            a["quote"], b["quote"] = b["quote"], a["quote"]
        return json.dumps({"fields": fields}, ensure_ascii=False)


def _targets(case: Case, fault: str) -> list[str | None]:
    fields = case.truth["fields"]
    present = [k for k, v in fields.items() if v["value"] is not None]
    absent = [k for k, v in fields.items() if v["value"] is None]
    if fault == "invented_field":
        return list(absent)
    if fault == "swapped_amounts":
        ok = fields.get("tax", {}).get("value") is not None and "subtotal" in fields
        return [None] if ok and fields["subtotal"]["value"] is not None else []
    if fault == "missing_quote" or fault in POSITIVE or fault == "quote_not_in_document":
        return list(present)
    # hallucinated / contradicts_quote / near_miss: skip currency, whose value is a code, not literal text
    return [k for k in present if k != "currency"]


@dataclass
class OracleTally:
    expected_ok: Counter[str] = field(default_factory=Counter)
    total: Counter[str] = field(default_factory=Counter)
    misses: list[str] = field(default_factory=list)


NOT_VERIFIED = frozenset({FieldStatus.REVIEW, FieldStatus.UNVERIFIED})


def expected_status(case: Case, key: str) -> frozenset[FieldStatus]:
    """The statuses a correct answer may get. Selection and yes/no values are the model's reading of
    the quote unless the option is written out, so they go to review by design. On scans, a value the
    OCR did not read literally (an umlaut lost, a 0 read as O) cannot be verified, so it must not be."""
    truth = case.truth["fields"][key]
    if truth["value"] is None:
        return frozenset({FieldStatus.MISSING})
    if case.kind == "scan" and normalize_text(truth["quote"] or "") not in case.text:
        return NOT_VERIFIED
    spec = next(f for f in case.schema.fields if f.key == key)
    if spec.type in (FieldType.SELECTION, FieldType.BOOLEAN) and normalize_text(
        str(truth["value"])
    ) not in normalize_text(truth["quote"] or ""):
        return frozenset({FieldStatus.REVIEW})
    if spec.type == FieldType.DATE and not case.date_order_known and is_ambiguous_date(truth["quote"] or ""):
        return frozenset({FieldStatus.REVIEW})
    return frozenset({FieldStatus.VERIFIED})


def downgraded_by_check(result: FieldResult) -> bool:
    """A correct value sent to review because a cross-field check failed on a neighbour."""
    return result.status == FieldStatus.REVIEW and all(r.startswith("Check failed") for r in result.reasons)


async def run_oracle(cases: list[Case], options: PipelineOptions) -> dict[str, Any]:
    rng = random.Random(7)
    tally = OracleTally()
    for case in cases:
        document = load_document(case.path.read_bytes(), None, options.load)
        text = document_text(document)
        case.date_order_known = detect_conventions(text)[1] is not None
        case.text = normalize_text(text)
        if case.kind == "scan":
            tally.total["scan_fields_ocr_differs"] += sum(
                1 for k, t in case.truth["fields"].items() if t["quote"] and normalize_text(t["quote"]) not in case.text
            )
        for fault in FAULTS:
            for target in _targets(case, fault):
                model = OracleModel(case.truth, fault, target, rng)
                result = await extract_from_document(document, case.schema, model, options)
                if fault == "swapped_amounts":
                    judged = [result.field("total"), result.field("tax")]
                else:
                    judged = [result.field(target)] if target else []
                for r in judged:
                    if r is None:
                        continue
                    tally.total[fault] += 1
                    if fault in POSITIVE:
                        ok = r.status in expected_status(case, r.key)
                    else:
                        ok = r.status != FieldStatus.VERIFIED
                    if ok:
                        tally.expected_ok[fault] += 1
                    else:
                        tally.misses.append(f"{case.name} {fault} {r.key}: {r.status.value} {r.reasons}")
                # Positive control on the untouched fields of every faulty run, too.
                if fault not in POSITIVE:
                    for r in result.fields:
                        if r in judged:
                            continue
                        tally.total["untouched"] += 1
                        if r.status in expected_status(case, r.key):
                            tally.expected_ok["untouched"] += 1
                        elif downgraded_by_check(r):
                            # Correct, and sent to review only because a check it takes part in failed:
                            # Pinpoint cannot tell which of the summed amounts is the wrong one.
                            tally.expected_ok["untouched"] += 1
                            tally.total["untouched_downgraded_by_check"] += 1
                        else:
                            tally.misses.append(f"{case.name} {fault} untouched {r.key}: {r.status.value} {r.reasons}")

    positive_total = sum(tally.total[f] for f in (*POSITIVE, "untouched"))
    positive_ok = sum(tally.expected_ok[f] for f in (*POSITIVE, "untouched"))
    fault_total = sum(tally.total[f] for f in FAULTS if f not in POSITIVE)
    fault_ok = sum(tally.expected_ok[f] for f in FAULTS if f not in POSITIVE)
    return {
        "documents": len(cases),
        "by_fault": {f: {"expected": tally.expected_ok[f], "total": tally.total[f]} for f in (*FAULTS, "untouched")},
        "untouched_downgraded_by_check": tally.total["untouched_downgraded_by_check"],
        "scan_fields_ocr_differs": tally.total["scan_fields_ocr_differs"],
        "positive_verified_rate": positive_ok / positive_total if positive_total else 0.0,
        "fault_caught_rate": fault_ok / fault_total if fault_total else 0.0,
        "misses": tally.misses,
    }


class OpenAICompatibleModel:
    def __init__(self, base_url: str, model: str, api_key: str | None, timeout: float) -> None:
        self.base_url, self.model, self.api_key, self.timeout = base_url.rstrip("/"), model, api_key, timeout

    async def complete(self, prompt: str) -> str:
        import niquests  # shipped with nc_py_api

        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        body = {"model": self.model, "messages": [{"role": "user", "content": prompt}], "temperature": 0}

        def call() -> str:
            response = niquests.post(
                f"{self.base_url}/chat/completions", json=body, headers=headers, timeout=self.timeout
            )
            response.raise_for_status()
            return response.json()["choices"][0]["message"]["content"]

        return await asyncio.to_thread(call)


def _value_correct(expected: Any, got: Any) -> bool:
    if expected is None or got is None:
        return expected is None and got is None
    if isinstance(expected, float):
        return isinstance(got, int | float) and abs(float(got) - expected) <= 0.005
    return str(expected).strip().casefold() == str(got).strip().casefold()


async def run_model(cases: list[Case], model: OpenAICompatibleModel, options: PipelineOptions) -> dict[str, Any]:
    rows = []
    status_counts: Counter[str] = Counter()
    correct_by_status: dict[str, Counter[bool]] = defaultdict(Counter)
    durations = []
    failures = []
    for case in cases:
        document = load_document(case.path.read_bytes(), None, options.load)
        started = time.perf_counter()
        try:
            result = await extract_from_document(document, case.schema, model, options)
        except Exception as exc:  # report and keep going
            failures.append(f"{case.name}: {exc}")
            continue
        durations.append(time.perf_counter() - started)
        for r in result.fields:
            expected = case.truth["fields"][r.key]["value"]
            correct = _value_correct(expected, r.value)
            status_counts[r.status.value] += 1
            correct_by_status[r.status.value][correct] += 1
            rows.append(
                {
                    "case": case.name,
                    "kind": case.kind,
                    "field": r.key,
                    "status": r.status.value,
                    "correct": correct,
                    "expected": expected,
                    "got": r.value,
                }
            )
        print(f"  {case.name}: {result.summary()}", flush=True)

    total = len(rows)
    correct = sum(r["correct"] for r in rows)
    verified = correct_by_status["verified"]
    wrong = [r for r in rows if not r["correct"]]
    return {
        "documents": len(cases),
        "fields": total,
        "accuracy": correct / total if total else 0.0,
        "status_counts": dict(status_counts),
        "verified_precision": verified[True] / (verified[True] + verified[False]) if verified.total() else 0.0,
        "confidently_wrong": sum(1 for r in wrong if r["status"] == "verified"),
        "wrong_total": len(wrong),
        "wrong_flagged_rate": (sum(1 for r in wrong if r["status"] != "verified") / len(wrong)) if wrong else 1.0,
        "median_seconds_per_document": sorted(durations)[len(durations) // 2] if durations else None,
        "failures": failures,
        "wrong": wrong,
    }


def _report_markdown(title: str, summary: dict[str, Any], args: argparse.Namespace) -> str:
    lines = [f"# {title}", "", f"Run on {date.today().isoformat()} with `{' '.join(sys.argv[1:])}`.", ""]
    if args.mode == "oracle":
        lines += [
            f"- Documents: {summary['documents']}",
            f"- Correct answers given the expected status: **{summary['positive_verified_rate']:.1%}**",
            f"- Faulty answers caught (not verified): **{summary['fault_caught_rate']:.1%}**",
            "",
            "| Case | As expected | Total |",
            "|---|---|---|",
            *(f"| {k} | {v['expected']} | {v['total']} |" for k, v in summary["by_fault"].items()),
            "",
            f"Untouched fields sent to review because a check they take part in failed: "
            f"{summary['untouched_downgraded_by_check']} (counted as expected: when net + tax != total, "
            "Pinpoint cannot tell which amount is wrong, so all three go to review).",
            "",
            f"Fields on scans whose printed text the OCR did not read literally: {summary['scan_fields_ocr_differs']} "
            "(for these, a correct value is expected to go to review rather than be verified).",
        ]
    else:
        counts = summary["status_counts"]
        lines += [
            f"- Documents: {summary['documents']}, fields: {summary['fields']}",
            f"- Field accuracy: **{summary['accuracy']:.1%}**",
            f"- Verified fields that were correct: **{summary['verified_precision']:.1%}**",
            f"- Wrong values marked verified (confidently wrong): **{summary['confidently_wrong']}** "
            f"of {summary['wrong_total']} wrong values",
            "- Statuses: " + ", ".join(f"{k} {v}" for k, v in sorted(counts.items())),
            f"- Median time per document: {summary['median_seconds_per_document']:.1f} s"
            if summary["median_seconds_per_document"]
            else "",
            "",
            "## Wrong values",
            "",
            "| Document | Field | Expected | Got | Status |",
            "|---|---|---|---|---|",
            *(
                f"| {r['case']} | {r['field']} | {r['expected']} | {r['got']} | {r['status']} |"
                for r in summary["wrong"]
            ),
        ]
        if summary["failures"]:
            lines += ["", "## Failed documents", "", *(f"- {f}" for f in summary["failures"])]
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate Pinpoint on the synthetic dataset.")
    sub = parser.add_subparsers(dest="mode", required=True)
    oracle = sub.add_parser("oracle", help="verification layer only, with injected faults")
    oracle.add_argument("--check", action="store_true", help="exit non-zero below the CI thresholds")
    real = sub.add_parser("openai", help="full pipeline with an OpenAI-compatible model")
    real.add_argument("--base-url", required=True)
    real.add_argument("--model", required=True)
    real.add_argument("--api-key", default=os.environ.get("OPENAI_API_KEY"))
    real.add_argument("--timeout", type=float, default=600)
    real.add_argument("--limit", type=int, default=0, help="only the first N documents")
    for p in (oracle, real):
        p.add_argument("--report", type=Path, help="write a markdown report here")
        p.add_argument("--json", type=Path, help="write the raw summary here")
        p.add_argument("--no-scans", action="store_true", help="skip scanned documents (no OCR needed)")
        p.add_argument("--ocr-languages", default="eng+deu+fra")
    args = parser.parse_args()

    include_scans = not args.no_scans
    if include_scans and not ocr_available():
        print("Tesseract is not installed: skipping scanned documents.", file=sys.stderr)
        include_scans = False
    cases = load_cases(include_scans)
    options = PipelineOptions(load=LoadOptions(ocr_languages=args.ocr_languages))

    if args.mode == "oracle":
        summary = asyncio.run(run_oracle(cases, options))
        title = "Pinpoint verification layer: oracle evaluation"
        print(f"Documents: {summary['documents']}")
        for k, v in summary["by_fault"].items():
            print(f"  {k:24} {v['expected']:4} / {v['total']}")
        print(f"  (untouched fields sent to review by a failed check: {summary['untouched_downgraded_by_check']})")
        print(f"Correct answers verified: {summary['positive_verified_rate']:.1%}")
        print(f"Faulty answers caught:    {summary['fault_caught_rate']:.1%}")
        for miss in summary["misses"][:40]:
            print(f"  miss: {miss}")
    else:
        if args.limit:
            cases = cases[: args.limit]
        model = OpenAICompatibleModel(args.base_url, args.model, args.api_key, args.timeout)
        summary = asyncio.run(run_model(cases, model, options))
        title = f"Pinpoint with {args.model}"
        print(json.dumps({k: v for k, v in summary.items() if k != "wrong"}, indent=2))

    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(_report_markdown(title, summary, args))
    if args.json:
        args.json.write_text(json.dumps(summary, indent=2, default=str) + "\n")

    if args.mode == "oracle" and args.check:
        failed = [k for k, minimum in THRESHOLDS.items() if summary[k] < minimum]
        if failed:
            print(f"Below threshold: {', '.join(failed)}", file=sys.stderr)
            sys.exit(1)


if __name__ == "__main__":
    main()
