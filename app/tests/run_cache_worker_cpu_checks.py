#!/usr/bin/env python3
"""Checks for cache rebuild CPU/worker sizing helpers."""

from __future__ import annotations

from pathlib import Path
import os
import sys
import tempfile

APP_DIR = Path(__file__).resolve().parents[1]
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from cache_manager import (  # noqa: E402
    _detect_cgroup_cpu_count,
    _parse_cgroup_v2_cpu_max,
    _select_cache_rebuild_worker_count,
)


passed = 0
failed = 0


def test(desc: str, actual, expected) -> None:
    global passed, failed
    if actual == expected:
        passed += 1
        print(f"OK {desc}")
        return
    failed += 1
    print(f"FAIL: {desc}")
    print(f"  got:      {actual}")
    print(f"  expected: {expected}")


def test_cgroup_v2_cpu_max_parsing() -> None:
    test("cgroup v2 max means unlimited", _parse_cgroup_v2_cpu_max("max 100000"), None)
    test("cgroup v2 one CPU quota", _parse_cgroup_v2_cpu_max("100000 100000"), 1)
    test("cgroup v2 two CPU quota", _parse_cgroup_v2_cpu_max("200000 100000"), 2)
    test("cgroup v2 fractional quota is conservative", _parse_cgroup_v2_cpu_max("250000 100000"), 2)
    test("cgroup v2 invalid quota", _parse_cgroup_v2_cpu_max("nope 100000"), None)


def test_cgroup_file_detection() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        cpu_max = tmp_path / "cpu.max"
        quota = tmp_path / "cpu.cfs_quota_us"
        period = tmp_path / "cpu.cfs_period_us"

        cpu_max.write_text("150000 100000\n", encoding="utf-8")
        test(
            "cgroup v2 file detection",
            _detect_cgroup_cpu_count(
                cpu_max_path=cpu_max,
                cpu_quota_path=quota,
                cpu_period_path=period,
            ),
            1,
        )

        cpu_max.unlink()
        quota.write_text("300000\n", encoding="utf-8")
        period.write_text("100000\n", encoding="utf-8")
        test(
            "cgroup v1 file detection",
            _detect_cgroup_cpu_count(
                cpu_max_path=cpu_max,
                cpu_quota_path=quota,
                cpu_period_path=period,
            ),
            3,
        )


def test_worker_selection() -> None:
    test(
        "one CPU uses one rebuild worker",
        _select_cache_rebuild_worker_count(
            effective_cpu_count=1,
            configured_max_workers=3,
        ),
        1,
    )
    test(
        "two CPUs keep one CPU for web",
        _select_cache_rebuild_worker_count(
            effective_cpu_count=2,
            configured_max_workers=3,
        ),
        1,
    )
    test(
        "four CPUs use n minus one up to max",
        _select_cache_rebuild_worker_count(
            effective_cpu_count=4,
            configured_max_workers=3,
        ),
        3,
    )
    test(
        "configured max caps workers",
        _select_cache_rebuild_worker_count(
            effective_cpu_count=8,
            configured_max_workers=2,
        ),
        2,
    )
    test(
        "call max caps workers",
        _select_cache_rebuild_worker_count(
            effective_cpu_count=8,
            configured_max_workers=3,
            call_max_workers=1,
        ),
        1,
    )


def main() -> int:
    test_cgroup_v2_cpu_max_parsing()
    test_cgroup_file_detection()
    test_worker_selection()

    print("\n========================================")
    print(f"TOTAL: {passed}/{passed + failed} checks passed")
    if failed:
        print(f"{failed} FAILED!")
        print("========================================")
        return 1

    print("ALL CACHE WORKER CPU CHECKS PASSED")
    print("========================================")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
