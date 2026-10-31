#!/usr/bin/env python3
"""Calculate financial comparisons with explicit inputs, units and provenance."""
import argparse
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, localcontext
import json
from pathlib import Path
import sys

sys.dont_write_bytecode = True
import taskharness  # noqa: F401  (puts task-harness scripts on sys.path)
from contract import fingerprint, nonempty, require, safe_path, write_new

FORMULAS = {
    "growth_pct": "(current / previous - 1) * 100",
    "change": "current - previous",
    "ratio": "numerator / denominator",
    "percentage": "numerator / denominator * 100",
}


def number(value):
    require(isinstance(value, (str, int, float)) and not isinstance(value, bool), "value must be a decimal number or null")
    try:
        result = Decimal(str(value))
    except InvalidOperation as exc:
        raise ValueError("invalid decimal value") from exc
    require(result.is_finite(), "non-finite values are not allowed")
    return result


def calculate(root, input_file="inputs/metrics.json"):
    path = safe_path(root, input_file)
    data = json.loads(path.read_text(encoding="utf-8"))
    require(isinstance(data, dict) and data.get("schema_version") == 1, "metrics schema_version must be 1")
    metrics, calculations = data.get("metrics"), data.get("calculations")
    require(isinstance(metrics, list) and metrics, "metrics must be a nonempty list")
    require(isinstance(calculations, list) and calculations, "calculations must be a nonempty list")
    by_id = {}
    for metric in metrics:
        require(isinstance(metric, dict), "metric must be an object")
        for key in ("id", "entity", "period", "unit", "basis", "source_id"):
            require(nonempty(metric.get(key)), f"metric needs {key}")
        require(metric["id"] not in by_id, "duplicate metric ID")
        require("value" in metric, "missing value must be explicit null")
        if metric["value"] is not None:
            number(metric["value"])
        by_id[metric["id"]] = metric
    results, ids = [], set()
    for calc in calculations:
        require(isinstance(calc, dict) and nonempty(calc.get("id")), "calculation needs an ID")
        require(calc["id"] not in ids, "duplicate calculation ID")
        ids.add(calc["id"])
        op, refs = calc.get("operation"), calc.get("inputs")
        require(op in FORMULAS, "unsupported operation")
        require(isinstance(refs, list) and len(refs) == 2 and all(isinstance(x, str) and x in by_id for x in refs),
                "calculation requires two known metric IDs in formula order")
        require(nonempty(calc.get("comparability")), "calculation needs an explanation of comparability")
        left, right = [by_id[x] for x in refs]
        for key in ("entity", "unit", "basis"):
            require(left[key] == right[key], f"incompatible {key}; normalize and document inputs first")
        if op in {"ratio", "percentage"}:
            require(left["period"] == right["period"], "ratio/percentage inputs must cover the same period")
        elif op == "growth_pct":
            require(left["period"] != right["period"], "growth needs distinct periods")
        result = {"id": calc["id"], "operation": op, "formula": FORMULAS[op], "inputs": [left, right],
                  "comparability": calc["comparability"], "status": "PASS", "value": None,
                  "unit": "%" if op in {"growth_pct", "percentage"} else left["unit"] if op == "change" else "multiple"}
        if left["value"] is None or right["value"] is None:
            result.update(status="MISSING", reason="An input is missing; no imputation was performed.")
        else:
            a, b = number(left["value"]), number(right["value"])
            if op != "change" and b <= 0:
                result.update(status="NOT_MEANINGFUL", reason="A nonpositive denominator/base does not support this ratio or growth convention.")
            else:
                with localcontext() as ctx:
                    ctx.prec = 28
                    value = {"change": lambda: a - b, "ratio": lambda: a / b,
                             "percentage": lambda: a / b * 100, "growth_pct": lambda: (a / b - 1) * 100}[op]()
                    result["value"] = format(value, "f")
        results.append(result)
    return {"schema_version": 1, "created_at": datetime.now(timezone.utc).isoformat(),
            "input_file": input_file, "input_fingerprint": fingerprint(path), "results": results,
            "assessment": "PASS" if all(x["status"] == "PASS" for x in results) else "PARTIAL",
            "claim_limit": "Arithmetic and declared comparability only; source values and financial meaning require review."}


def verify_saved(root, report_file):
    saved = json.loads(safe_path(root, report_file).read_text(encoding="utf-8"))
    require(isinstance(saved, dict), "calculation report must be an object")
    actual = calculate(root, saved["input_file"])
    stable = lambda x: {k: v for k, v in x.items() if k != "created_at"}
    require(stable(actual) == stable(saved), "calculation report or its inputs changed; save a new calculation run")
    return actual


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--root", type=Path, required=True)
    p.add_argument("--input", default="inputs/metrics.json")
    p.add_argument("--out", required=True, help="new task-relative outputs/*.json")
    args = p.parse_args()
    root = args.root.resolve()
    out = safe_path(root, args.out)
    require(root / "outputs" in out.parents and out.suffix == ".json", "calculation output must be under outputs/")
    require(not out.exists(), "calculation output already exists; use a new name")
    result = calculate(root, args.input)
    write_new(out, result)
    print(json.dumps({"assessment": result["assessment"], "out": args.out, "calculations": len(result["results"])}, ensure_ascii=False))
    return 0 if result["assessment"] == "PASS" else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (ValueError, OSError, KeyError, TypeError, InvalidOperation) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(2)
