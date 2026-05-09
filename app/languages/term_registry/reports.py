"""Report writers for registry checks."""

from __future__ import annotations

from pathlib import Path
from typing import Any
import json


def write_json_and_markdown_report(
    *,
    report_dir: Path,
    stem: str,
    payload: dict[str, Any],
    title: str,
) -> tuple[Path, Path]:
    report_dir.mkdir(parents=True, exist_ok=True)
    json_path = report_dir / f"{stem}.json"
    md_path = report_dir / f"{stem}.md"

    json_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    summary = payload.get("summary", {})
    issue_counts = summary.get("issue_counts", {})
    lines = [
        f"# {title}",
        "",
        f"Generated: {payload.get('generated_at', '')}",
        "",
        "## Summary",
        "",
    ]
    for key, value in summary.items():
        if isinstance(value, (str, int, float, bool)):
            lines.append(f"- {key}: `{value}`")
    if issue_counts:
        lines.extend(["", "## Issue Counts", ""])
        for key, value in issue_counts.items():
            lines.append(f"- `{key}`: {value}")

    findings = payload.get("findings", [])
    lines.extend(["", "## Findings", ""])
    if findings:
        for finding in findings[:50]:
            lines.append(
                f"- `{finding.get('severity')}` `{finding.get('code')}`: "
                f"{finding.get('message')}"
            )
        if len(findings) > 50:
            lines.append(f"- ... {len(findings) - 50} more findings")
    else:
        lines.append("- none")

    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return json_path, md_path
