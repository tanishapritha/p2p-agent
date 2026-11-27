"""Offline deterministic matcher evaluator over labeled JSONL cases (no LLM calls)."""

import argparse
import json
from pathlib import Path

from app.matching import MatchInput, run_three_way_match


def evaluate(path: Path) -> dict:
    rows = [
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
    ]
    correct = 0
    false_approve = 0
    hold_cases = 0
    hold_detected = 0
    outputs = []
    for row in rows:
        result = run_three_way_match(MatchInput.model_validate(row["input"]))
        pred = result["recommendation"]
        expected = row["expected"]
        correct += pred == expected
        is_hold = expected == "HOLD_FOR_REVIEW"
        hold_cases += is_hold
        hold_detected += is_hold and pred == "HOLD_FOR_REVIEW"
        false_approve += is_hold and pred == "APPROVE_FOR_REVIEW"
        outputs.append(
            {
                "id": row["id"],
                "expected": expected,
                "predicted": pred,
                "correct": pred == expected,
                "exceptions": result["exceptions"],
            }
        )
    n = len(rows)
    return {
        "dataset": path.name,
        "cases": n,
        "accuracy": correct / n if n else 0,
        "hold_recall": hold_detected / hold_cases if hold_cases else None,
        "false_approve_count": false_approve,
        "results": outputs,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", default="eval/datasets/matching_v1.jsonl")
    args = parser.parse_args()
    print(json.dumps(evaluate(Path(args.dataset)), indent=2))


if __name__ == "__main__":
    main()
