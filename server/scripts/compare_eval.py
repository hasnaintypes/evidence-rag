"""
CI helper: diffs the metrics just produced by run_eval.py
(docs/eval_metrics.json) against the checked-in baseline
(docs/eval_baseline.json, last updated by a push to main - see
.github/workflows/eval.yml), and writes a PR-comment-ready markdown
table to server/eval_comment.md.

Writes server/eval_status.txt containing PASS or FAIL - a separate CI
step reads that and fails the job on regression, kept separate so the
comment always gets posted even when the run fails the gate.
"""
import json
import os
import sys

# Windows consoles default to cp1252, which can't encode the emoji status
# markers below; GitHub Actions runners are UTF-8 already, so this is a
# no-op there but keeps local runs on Windows from crashing on print().
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.config import EVAL_METRICS_PATH, EVAL_BASELINE_PATH

REGRESSION_THRESHOLD = 0.05  # absolute drop that counts as a regression
COMMENT_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "eval_comment.md")
STATUS_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "eval_status.txt")

TRACKED_METRICS = [
    ("avg_precision_at_k", "Precision@5"),
    ("avg_recall_at_k", "Recall@5"),
    ("avg_mrr", "MRR"),
    ("avg_faithfulness", "Faithfulness"),
]


def _row(config_label: str, metric_label: str, current: dict, baseline: dict, key: str) -> tuple:
    cur_val = current.get(key)
    base_val = baseline.get(key) if baseline else None

    if cur_val is None:
        return (f"{config_label} {metric_label}", "n/a", "-", "-", "n/a")

    if base_val is None:
        return (f"{config_label} {metric_label}", f"{cur_val}", "n/a", "-", "new")

    delta = round(cur_val - base_val, 3)
    if delta <= -REGRESSION_THRESHOLD:
        status, icon = "FAIL", "regressed"
    elif delta < 0:
        status, icon = "WARN", "down"
    else:
        status, icon = "PASS", "ok"
    sign = "+" if delta >= 0 else ""
    return (f"{config_label} {metric_label}", f"{cur_val}", f"{base_val}", f"{sign}{delta}", icon, status)


def main():
    with open(EVAL_METRICS_PATH, "r", encoding="utf-8") as f:
        current = json.load(f)

    baseline = None
    if os.path.exists(EVAL_BASELINE_PATH):
        with open(EVAL_BASELINE_PATH, "r", encoding="utf-8") as f:
            baseline = json.load(f)

    rows = []
    any_fail = False
    for config_key, config_label in (("naive", "Naive"), ("advanced", "Advanced")):
        cur_cfg = current.get(config_key, {})
        base_cfg = baseline.get(config_key, {}) if baseline else {}
        for key, label in TRACKED_METRICS:
            result = _row(config_label, label, cur_cfg, base_cfg, key)
            rows.append(result)
            if len(result) == 6 and result[5] == "FAIL":
                any_fail = True

    lines = ["## Retrieval Evaluation", ""]
    if baseline is None:
        lines.append("_No baseline yet (first run, or `docs/eval_baseline.json` not committed) - showing current numbers only._")
    elif any_fail:
        lines.append(f"**Regression detected** - one or more metrics dropped by more than {REGRESSION_THRESHOLD} vs. `main`.")
    else:
        lines.append("No regression beyond threshold vs. `main`.")
    lines.append("")
    lines.append("| Metric | Current | Baseline | Delta | |")
    lines.append("|---|---|---|---|---|")
    for row in rows:
        metric, cur, base, delta, icon = row[0], row[1], row[2], row[3], row[4]
        mark = {"regressed": "❌", "down": "⚠️", "ok": "✅", "new": "🆕", "n/a": "–"}[icon]
        lines.append(f"| {metric} | {cur} | {base} | {delta} | {mark} |")

    lines.append("")
    lines.append(f"Full per-question detail: `docs/eval_report.md` (uploaded as a workflow artifact).")

    with open(COMMENT_PATH, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    with open(STATUS_PATH, "w", encoding="utf-8") as f:
        f.write("FAIL" if any_fail else "PASS")

    print("\n".join(lines))
    print(f"\nGate: {'FAIL' if any_fail else 'PASS'}")


if __name__ == "__main__":
    main()
