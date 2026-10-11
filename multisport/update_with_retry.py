#!/usr/bin/env python3
"""Retry transient MultiSport update failures and emit a concise Actions report."""
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

MAX_ATTEMPTS = 3
TRANSIENT = re.compile(
    r"(timed? ?out|timeout|temporar(?:y|ily)|connection (?:reset|refused|aborted)|"
    r"remote end closed|broken pipe|name or service not known|"
    r"network is unreachable|http error (?:408|429|500|502|503|504)|"
    r"\b(?:408|429|500|502|503|504)\b|too many requests|"
    r"rate limit|service unavailable|bad gateway|gateway timeout|"
    r"urlopen error|connectionerror|readtimeout|connecttimeout)",
    re.IGNORECASE,
)
REPORT_PATH = Path("multisport/.runtime/update-report.json")
SUMMARY = os.environ.get("GITHUB_STEP_SUMMARY")

def append_summary(lines):
    if SUMMARY:
        with open(SUMMARY, "a", encoding="utf-8") as handle:
            handle.write("\n".join(lines) + "\n")

def write_report(report):
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

def main():
    report = {"runId": os.environ.get("GITHUB_RUN_ID"),
              "checkedAt": datetime.now(timezone.utc).isoformat(),
              "attempts": [], "status": "UNKNOWN"}
    for attempt in range(1, MAX_ATTEMPTS + 1):
        print(f"::group::MultiSport update attempt {attempt}/{MAX_ATTEMPTS}", flush=True)
        try:
            result = subprocess.run([sys.executable, "multisport/update.py"],
                                    capture_output=True, text=True, timeout=420)
            output = (result.stdout or "") + "\n" + (result.stderr or "")
            exit_code = result.returncode
        except subprocess.TimeoutExpired as exc:
            output = str(exc)
            exit_code = 124
        print(output[-12000:], flush=True)
        print("::endgroup::", flush=True)
        retryable = exit_code == 124 or bool(TRANSIENT.search(output))
        report["attempts"].append({"attempt": attempt, "exitCode": exit_code,
                                   "retryable": retryable, "tail": output[-2500:]})
        if exit_code == 0:
            report["status"] = "RECOVERED" if attempt > 1 else "SUCCESS"
            break
        if not retryable or attempt == MAX_ATTEMPTS:
            report["status"] = "PERSISTENT_TRANSIENT_FAILURE" if retryable else "CODE_OR_CONFIG_FAILURE"
            break
        delay = [20, 45][attempt - 1]
        print(f"Transient failure detected. Retrying after {delay}s.", flush=True)
        time.sleep(delay)

    if report["status"] in ("SUCCESS", "RECOVERED"):
        try:
            data = json.loads(Path("multisport/data.json").read_text(encoding="utf-8"))
            report["updatedAt"] = data.get("updatedAt")
            report["sports"] = {
                name: {"status": entry.get("status"), "sourceStatus": entry.get("sourceStatus"),
                       "verifiedRows": entry.get("verifiedRows", 0)}
                for name, entry in data.get("sports", {}).items()
            }
        except (OSError, ValueError) as exc:
            report["snapshotWarning"] = str(exc)
    write_report(report)
    lines = [f"### MultiSport update: {report['status']}",
             f"Attempts: {len(report['attempts'])}/{MAX_ATTEMPTS}"]
    if report.get("updatedAt"):
        lines.append(f"Published snapshot timestamp: {report['updatedAt']}")
    for name, entry in report.get("sports", {}).items():
        lines.append(f"- {name}: {entry['status']} / {entry['sourceStatus']} — {entry['verifiedRows']} verified rows")
    if report["status"] not in ("SUCCESS", "RECOVERED"):
        lines.append("The update did not publish. Review the failing attempt's logs and update-report artifact.")
    append_summary(lines)
    if report["status"] not in ("SUCCESS", "RECOVERED"):
        print(f"::error::MultiSport update failed after {len(report['attempts'])} attempt(s): {report['status']}", flush=True)
        return 1
    return 0

if __name__ == "__main__":
    sys.exit(main())
