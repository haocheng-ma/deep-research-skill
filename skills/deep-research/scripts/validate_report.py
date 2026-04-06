"""Standalone report validation script.

stdlib-only — no external dependencies.

Usage:
    python3 validate_report.py /path/to/report.md
"""

import re
import sys
from pathlib import Path


def validate(file_path: str) -> dict:
    """Validate a research report. Returns {"status": "PASS"|"FAIL", "issues": [...]}."""
    report_path = Path(file_path)

    if not report_path.exists():
        return {"status": "FAIL", "issues": ["Report file does not exist."]}

    try:
        report_text = report_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        return {"status": "FAIL", "issues": [f"Report file is unreadable: {exc}"]}

    issues: list[str] = []

    # Check 1: Minimum total length
    char_count = len(report_text)
    if char_count < 2000:
        issues.append(
            f"Report has insufficient content ({char_count} chars). "
            "Minimum required: >= 2000 chars."
        )

    # Check 2: No [sources: ...] outline markers
    if re.search(r"\[sources:", report_text):
        issues.append(
            'Report contains "[sources: ...]" outline markers. '
            "Remove all [sources: ...] lines — they belong in the outline only."
        )

    # Check 3: Minimum section count (>= 3 ## headings)
    h2_headings = re.findall(r"^## .+", report_text, re.MULTILINE)
    if len(h2_headings) < 3:
        issues.append(
            f"Report has only {len(h2_headings)} ## heading(s). "
            "Minimum required: >= 3 (e.g., Introduction, body sections, Conclusion)."
        )

    # Check 4: No empty sections
    heading_pattern = re.compile(r"^(#{2,3}) .+", re.MULTILINE)
    headings = list(heading_pattern.finditer(report_text))
    for i, match in enumerate(headings):
        heading_text = match.group(0).strip()
        heading_level = match.group(1)
        next_match = headings[i + 1] if i + 1 < len(headings) else None
        if heading_level == "##" and next_match is not None and next_match.group(1) == "###":
            continue
        start = match.end()
        end = next_match.start() if next_match is not None else len(report_text)
        body = report_text[start:end].strip()
        if len(body) < 50:
            issues.append(
                f'Section "{heading_text}" has no content ({len(body)} chars). '
                "Every section must have at least 50 characters of body text."
            )

    # Check 5: Has at least one citation
    if not re.search(r"\[citation:", report_text):
        issues.append(
            "Report contains no [citation:...] inline citations. "
            "Every factual claim must be cited."
        )

    if issues:
        return {"status": "FAIL", "issues": issues}
    return {"status": "PASS", "issues": []}


def main():
    if len(sys.argv) < 2:
        print("Usage: python3 validate_report.py <report_path>", file=sys.stderr)
        sys.exit(1)

    result = validate(sys.argv[1])

    if result["status"] == "PASS":
        print("PASS — report validated")
    else:
        print(f"FAIL — {len(result['issues'])} issue(s) found:")
        for i, issue in enumerate(result["issues"], 1):
            print(f"{i}. {issue}")
        print("\nFix FAIL issues and run again.")

    sys.exit(0 if result["status"] == "PASS" else 1)


if __name__ == "__main__":
    main()
