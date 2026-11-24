from pathlib import Path
from app.evaluate import evaluate

def test_labeled_dataset_reports_expected_matcher_quality():
    report=evaluate(Path("eval/datasets/matching_v1.jsonl"))
    assert report["cases"] == 4
    assert report["accuracy"] == 1.0
    assert report["hold_recall"] == 1.0
    assert report["false_approve_count"] == 0
