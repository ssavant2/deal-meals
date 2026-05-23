#!/usr/bin/env python3
"""Run the standard gate set for a Swedish matcher rule change.

Examples:
    python support_checks/run_matcher_change_gates.py --track A
    python support_checks/run_matcher_change_gates.py --track B --policy-ref plain_sensitive_filmjolk
    python support_checks/run_matcher_change_gates.py --track B --registry-changed --allow-removals

This script does not replace the matcher rule-change runbook. It is the
repeatable command layer for the runbook's common Track A and Track B gates.
"""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
import os
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile
import time


APP_DIR = Path(__file__).resolve().parents[1]
SUPPORT_CHECKS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(APP_DIR))

from support_checks.matcher_contracts import (  # noqa: E402
    contract_paths,
    repo_root_for_tree_root,
)


@dataclass(frozen=True)
class Step:
    name: str
    argv: tuple[str, ...]
    reason: str
    cwd: Path = APP_DIR
    parallel_group: str | None = None


@dataclass(frozen=True)
class StepResult:
    step: Step
    returncode: int
    duration_seconds: float
    output: str = ""


@dataclass(frozen=True)
class ChangeFlags:
    registry_changed: bool
    runtime_changed: bool
    fixtures_changed: bool
    inventory_changed: bool
    support_checks_changed: bool


def _script(name: str) -> str:
    return str(SUPPORT_CHECKS_DIR / name)


def _command(name: str, *args: str) -> tuple[str, ...]:
    return (sys.executable, _script(name), *args)


def _cgroup_cpu_quota_count() -> int | None:
    cpu_max = Path("/sys/fs/cgroup/cpu.max")
    try:
        quota_text = cpu_max.read_text(encoding="utf-8").strip().split()
    except OSError:
        quota_text = []
    if len(quota_text) == 2 and quota_text[0] != "max":
        try:
            quota = int(quota_text[0])
            period = int(quota_text[1])
        except ValueError:
            quota = period = 0
        if quota > 0 and period > 0:
            return max(1, (quota + period - 1) // period)

    cpu_quota = Path("/sys/fs/cgroup/cpu/cpu.cfs_quota_us")
    cpu_period = Path("/sys/fs/cgroup/cpu/cpu.cfs_period_us")
    try:
        quota = int(cpu_quota.read_text(encoding="utf-8").strip())
        period = int(cpu_period.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return None
    if quota > 0 and period > 0:
        return max(1, (quota + period - 1) // period)
    return None


def _available_cpu_count() -> int:
    counts = [os.cpu_count() or 1]
    if hasattr(os, "sched_getaffinity"):
        try:
            counts.append(len(os.sched_getaffinity(0)))
        except OSError:
            pass
    cgroup_count = _cgroup_cpu_quota_count()
    if cgroup_count is not None:
        counts.append(cgroup_count)
    return max(1, min(counts))


def _default_support_self_test_jobs() -> int:
    return max(1, _available_cpu_count() - 1)


def _support_self_test_jobs(args: argparse.Namespace) -> int:
    return args.support_self_test_jobs or _default_support_self_test_jobs()


def _default_parallel_readonly_jobs() -> int:
    return max(1, _available_cpu_count() - 1)


def _parallel_readonly_jobs(args: argparse.Namespace) -> int:
    return args.parallel_readonly_jobs or _default_parallel_readonly_jobs()


def _fixture_file_for_args(args: argparse.Namespace) -> Path:
    return contract_paths(args.tree_root).fixture_file


def _inventory_file_for_args(args: argparse.Namespace) -> Path:
    return contract_paths(args.tree_root).inventory_file


def _fixture_file_args(args: argparse.Namespace) -> list[str]:
    if args.tree_root is None:
        return []
    return ["--fixture-file", str(_fixture_file_for_args(args))]


def _inventory_file_args(args: argparse.Namespace) -> list[str]:
    if args.tree_root is None:
        return []
    return [
        "--inventory-file", str(_inventory_file_for_args(args)),
        "--fixture-file", str(_fixture_file_for_args(args)),
        "--repo-root", str(repo_root_for_tree_root(args.tree_root)),
    ]


def _tree_root_args(args: argparse.Namespace) -> list[str]:
    if args.tree_root is None:
        return []
    return ["--tree-root", str(args.tree_root)]


def _target_filter_args(args: argparse.Namespace) -> list[str]:
    filters: list[str] = []
    for case_id in args.case_id or []:
        filters.extend(["--case-id", case_id])
    for policy_ref in args.policy_ref or []:
        filters.extend(["--policy-ref", policy_ref])
    for canonical in args.canonical or []:
        filters.extend(["--canonical", canonical])
    return filters


def _discover_repo_root() -> Path:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=APP_DIR,
            text=True,
            capture_output=True,
            check=False,
        )
    except FileNotFoundError:
        result = None
    if result is not None and result.returncode == 0 and result.stdout.strip():
        return Path(result.stdout.strip()).resolve()
    if (APP_DIR.parent / ".git").exists():
        return APP_DIR.parent
    if (APP_DIR / ".git").exists():
        return APP_DIR
    return APP_DIR


def _git_changed_paths(repo_root: Path) -> tuple[set[str], str | None]:
    try:
        result = subprocess.run(
            ["git", "status", "--porcelain=v1", "-z", "--untracked-files=all"],
            cwd=repo_root,
            text=True,
            capture_output=True,
            check=False,
        )
    except FileNotFoundError:
        return set(), "git executable not found"
    if result.returncode != 0:
        error = (result.stderr or result.stdout or "git status failed").strip()
        return set(), error

    paths: set[str] = set()
    entries = result.stdout.split("\0")
    index = 0
    while index < len(entries):
        entry = entries[index]
        if not entry:
            index += 1
            continue
        status = entry[:2]
        path = entry[3:]
        if status[0] in {"R", "C"} or status[1] in {"R", "C"}:
            index += 1
            if index < len(entries) and entries[index]:
                path = entries[index]
        if path:
            paths.add(path.replace("\\", "/"))
        index += 1
    return paths, None


def _has_path(paths: set[str], *needles: str) -> bool:
    normalized = {needle.strip("/") for needle in needles}
    for path in paths:
        forms = {path.strip("/")}
        if path.startswith("app/"):
            forms.add(path[4:].strip("/"))
        else:
            forms.add(f"app/{path}".strip("/"))
        for form in forms:
            if any(form.startswith(needle) or form == needle for needle in normalized):
                return True
    return False


def _is_under(path: str, prefix: str) -> bool:
    path = path.strip("/")
    prefix = prefix.strip("/")
    forms = {path}
    if path.startswith("app/"):
        forms.add(path[4:])
    else:
        forms.add(f"app/{path}")
    return any(form.startswith(prefix) or form == prefix for form in forms)


def _detect_change_flags(paths: set[str]) -> ChangeFlags:
    registry_changed = _has_path(
        paths,
        "app/languages/sv/ingredient_matching/term_registry/entries/",
        "app/languages/sv/ingredient_matching/term_registry/baselines/",
        "app/support_checks/run_term_registry_",
    )
    runtime_changed = any(
        (
            _is_under(path, "app/languages/sv/ingredient_matching/")
            and not _is_under(path, "app/languages/sv/ingredient_matching/term_registry/")
        )
        or _is_under(path, "app/languages/sv/recipe_matcher_backend.py")
        for path in paths
    )
    fixtures_changed = _has_path(
        paths,
        "app/languages/sv/matcher_contracts/sources/matcher_regression_cases.toml",
        "app/languages/sv/matcher_contracts/matcher_regression_cases.json",
    )
    inventory_changed = _has_path(
        paths,
        "app/languages/sv/matcher_contracts/sources/matcher_rule_inventory.toml",
        "app/languages/sv/matcher_contracts/matcher_rule_inventory.json",
    )
    support_checks_changed = _has_path(paths, "app/support_checks/")
    return ChangeFlags(
        registry_changed=registry_changed,
        runtime_changed=runtime_changed,
        fixtures_changed=fixtures_changed,
        inventory_changed=inventory_changed,
        support_checks_changed=support_checks_changed,
    )


def _resolve_flag(explicit: bool | None, detected: bool, *, auto_detect: bool) -> bool:
    if explicit is not None:
        return explicit
    return bool(auto_detect and detected)


def _resolved_change_flags(
    args: argparse.Namespace,
    detected: ChangeFlags,
) -> ChangeFlags:
    return ChangeFlags(
        registry_changed=_resolve_flag(
            args.registry_changed,
            detected.registry_changed,
            auto_detect=args.auto_detect,
        ),
        runtime_changed=_resolve_flag(
            args.runtime_changed,
            detected.runtime_changed,
            auto_detect=args.auto_detect,
        ),
        fixtures_changed=_resolve_flag(
            args.fixtures_changed,
            detected.fixtures_changed,
            auto_detect=args.auto_detect,
        ),
        inventory_changed=_resolve_flag(
            args.inventory_changed,
            detected.inventory_changed,
            auto_detect=args.auto_detect,
        ),
        support_checks_changed=_resolve_flag(
            args.support_checks_changed,
            detected.support_checks_changed,
            auto_detect=args.auto_detect,
        ),
    )


def _has_targets(args: argparse.Namespace) -> bool:
    return bool(args.case_id or args.policy_ref or args.canonical)


def _promotion_args(args: argparse.Namespace) -> list[str]:
    promotion_args: list[str] = []
    if args.migrate_hashes:
        promotion_args.append("--migrate-hashes")
    if args.allow_removals:
        promotion_args.append("--allow-removals")
    if args.confirm_large_removals:
        promotion_args.append("--confirm-large-removals")
    if args.baseline_output_dir is not None:
        promotion_args.extend(["--output-dir", str(args.baseline_output_dir)])
    return promotion_args


def _stages_baseline(args: argparse.Namespace, changes: ChangeFlags) -> bool:
    return (
        args.track == "B"
        and changes.registry_changed
        and not args.skip_baseline_promotion
        and args.baseline_output_dir is not None
    )


def _baseline_promotion_step(args: argparse.Namespace) -> Step:
    return Step(
        "promote verified-term baseline",
        _command("promote_term_baseline.py", *_promotion_args(args)),
        "syncs registry TOML changes with the frozen verified-term baseline",
    )


def _preflight_step(args: argparse.Namespace) -> Step:
    return Step(
        "matcher change pre-flight",
        _command("run_matcher_change_preflight.py", *_tree_root_args(args)),
        "collects matcher rule-change infrastructure issues before slower gates",
        cwd=repo_root_for_tree_root(args.tree_root) if args.tree_root is not None else APP_DIR,
    )


def _generated_coverage_step(args: argparse.Namespace) -> Step:
    return Step(
        "generate matcher registry coverage",
        _command("generate_matcher_registry_coverage.py", *_tree_root_args(args), "--write"),
        "updates derived coverage TOML from generated fixture/inventory JSON before validation",
        cwd=repo_root_for_tree_root(args.tree_root) if args.tree_root is not None else APP_DIR,
    )


def _generated_contract_json_step(args: argparse.Namespace) -> Step:
    return Step(
        "generate matcher contract JSON",
        _command("generate_matcher_contract_json_from_toml_sources.py", *_tree_root_args(args), "--write"),
        "updates generated fixture/inventory JSON from authoritative TOML sources before coverage/pre-flight",
        cwd=repo_root_for_tree_root(args.tree_root) if args.tree_root is not None else APP_DIR,
    )


def _generated_coverage_is_stale(args: argparse.Namespace) -> bool:
    from support_checks.generate_matcher_registry_coverage import generate_coverage_files  # noqa: PLC0415

    return any(
        item.changed
        for item in generate_coverage_files(tree_root=args.tree_root)
    )


def _build_track_a_steps(args: argparse.Namespace) -> list[Step]:
    steps = [
        Step(
            "deep matcher sanity",
            _command("run_deep_matcher_sanity.py"),
            "primary Track A regression gate",
            parallel_group="track-a-readonly",
        ),
        Step(
            "full matcher parity",
            _command("run_matcher_layer_parity.py", *_fixture_file_args(args), "--skip-cache-freshness"),
            "proves the narrow runtime fix did not break existing contracts",
            parallel_group="track-a-readonly",
        ),
    ]
    if args.reload_cache:
        steps.append(Step(
            "reload matcher/cache",
            _command("dev_reload.py"),
            "refreshes active dev cache before cache-backed validation",
        ))
    if args.fresh_cache_gates:
        steps.extend([
            Step(
                "full fixture cases with cache freshness",
                _command("run_matcher_layer_fixture_cases.py", *_fixture_file_args(args)),
                "final cache-aware fixture gate",
                parallel_group="fresh-cache-readonly",
            ),
            Step(
                "full parity with cache freshness",
                _command("run_matcher_layer_parity.py", *_fixture_file_args(args)),
                "final cache-aware parity gate",
                parallel_group="fresh-cache-readonly",
            ),
        ])
    return steps


def _build_track_b_steps(args: argparse.Namespace, changes: ChangeFlags) -> list[Step]:
    steps: list[Step] = []
    target_args = _target_filter_args(args)

    if _has_targets(args):
        steps.extend([
            Step(
                "targeted fixture cases",
                _command(
                    "run_matcher_layer_fixture_cases.py",
                    *_fixture_file_args(args),
                    *target_args,
                    "--skip-cache-freshness",
                ),
                "checks the affected fixture/policy/canonical first",
                parallel_group="targeted-readonly",
            ),
            Step(
                "targeted matcher parity",
                _command(
                    "run_matcher_layer_parity.py",
                    *_fixture_file_args(args),
                    *target_args,
                    "--skip-cache-freshness",
                ),
                "checks the affected fixture/policy/canonical across matcher paths",
                parallel_group="targeted-readonly",
            ),
        ])

    if args.refresh_line_refs:
        steps.append(Step(
            "refresh inventory line refs",
            _command(
                "refresh_matcher_rule_inventory_line_refs.py",
                "--write",
                "--repo-root",
                str(repo_root_for_tree_root(args.tree_root)),
            ),
            "updates inventory anchors after moved Python/TOML line refs",
            cwd=repo_root_for_tree_root(args.tree_root),
        ))

    if changes.registry_changed:
        steps.extend([
            Step(
                "term registry contract checks",
                _command("run_term_registry_contract_checks.py", "--language", "sv"),
                "validates registry/baseline contracts",
                parallel_group="registry-readonly",
            ),
            Step(
                "term registry add-term checks",
                _command("run_term_registry_add_term_checks.py", "--language", "sv"),
                "validates add-term expectations and coverage counts",
                parallel_group="registry-readonly",
            ),
            Step(
                "term registry export checks",
                _command("run_term_registry_export_checks.py", "--language", "sv"),
                "validates generated runtime exports from registry entries",
                parallel_group="registry-readonly",
            ),
            Step(
                "term registry guard/bridge checks",
                _command("run_term_registry_guard_bridge_checks.py", "--language", "sv"),
                "validates guarded bridge/no-match registry payloads",
                parallel_group="registry-readonly",
            ),
        ])

    if changes.runtime_changed:
        steps.extend([
            Step(
                "broad sanity checks",
                _command("run_sanity_checks.py"),
                "checks broader runtime support expectations after Python changes",
                parallel_group="runtime-readonly",
            ),
            Step(
                "deep matcher sanity",
                _command("run_deep_matcher_sanity.py"),
                "checks focused matcher regressions for new or changed rules",
                parallel_group="runtime-readonly",
            ),
        ])

    steps.extend([
        Step(
            "full fixture cases",
            _command("run_matcher_layer_fixture_cases.py", *_fixture_file_args(args), "--skip-cache-freshness"),
            "required Track B fixture contract gate",
            parallel_group="full-fixture-readonly",
        ),
        Step(
            "full matcher parity",
            _command("run_matcher_layer_parity.py", *_fixture_file_args(args), "--skip-cache-freshness"),
            "required Track B parity gate across matcher paths",
            parallel_group="full-fixture-readonly",
        ),
    ])

    if changes.fixtures_changed or changes.inventory_changed or changes.registry_changed:
        steps.extend([
            Step(
                "matcher rule model checks",
                _command(
                    "run_matcher_rule_model_checks.py",
                    *_fixture_file_args(args),
                    *(["--inventory-file", str(_inventory_file_for_args(args))] if args.tree_root is not None else []),
                ),
                "validates rule-model and fixture/inventory structure",
                parallel_group="rule-model-readonly",
            ),
            Step(
                "matcher rule inventory checks",
                _command("run_matcher_rule_inventory_checks.py", *_inventory_file_args(args)),
                "validates fixture to inventory ownership",
                parallel_group="rule-model-readonly",
            ),
        ])

    steps.append(Step(
        "matcher version checks",
        _command("run_matcher_version_checks.py"),
        "checks final matcher/contract version state",
    ))

    if args.include_support_self_checks:
        support_self_test_jobs = _support_self_test_jobs(args)
        steps.extend([
            Step(
                "matcher rule-change flow tests",
                (
                    sys.executable,
                    "-m",
                    "unittest_parallel",
                    "-s",
                    "support_checks/tests",
                    "-p",
                    "test_rule_change_flow.py",
                    "-t",
                    ".",
                    "--level",
                    "test",
                    "-j",
                    str(support_self_test_jobs),
                ),
                (
                    "support-check self-test for the pre-flight rule-change flow "
                    f"({support_self_test_jobs} worker process(es))"
                ),
            ),
            Step(
                "matcher fixture schema checks",
                _command("run_matcher_layer_fixture_schema_checks.py"),
                "support-check self-test for fixture schema/tooling changes",
            ),
            Step(
                "matcher diagnostics checks",
                _command("run_matcher_layer_diagnostics_checks.py"),
                "support-check self-test for diagnostics tooling changes",
            ),
            Step(
                "matcher parity checks",
                _command("run_matcher_layer_parity_checks.py"),
                "support-check self-test for parity tooling changes",
            ),
        ])

    if args.reload_cache:
        steps.append(Step(
            "reload matcher/cache",
            _command("dev_reload.py"),
            "refreshes active dev cache before cache-backed validation",
        ))
    if args.fresh_cache_gates:
        steps.extend([
            Step(
                "full fixture cases with cache freshness",
                _command("run_matcher_layer_fixture_cases.py", *_fixture_file_args(args)),
                "final cache-aware fixture gate",
                parallel_group="fresh-cache-readonly",
            ),
            Step(
                "full parity with cache freshness",
                _command("run_matcher_layer_parity.py", *_fixture_file_args(args)),
                "final cache-aware parity gate",
                parallel_group="fresh-cache-readonly",
            ),
        ])

    return steps


def _display_command(step: Step) -> str:
    parts: list[str] = []
    for index, value in enumerate(step.argv):
        if index == 0 and value == sys.executable:
            parts.append("python")
            continue
        try:
            path = Path(value).resolve()
            if path.parent == SUPPORT_CHECKS_DIR:
                parts.append(f"support_checks/{path.name}")
                continue
        except OSError:
            pass
        parts.append(value)
    return " ".join(shlex.quote(part) for part in parts)


def _format_duration(seconds: float) -> str:
    if seconds < 60:
        return f"{seconds:.1f}s"
    minutes = int(seconds // 60)
    remainder = seconds - (minutes * 60)
    return f"{minutes}m {remainder:.1f}s"


def _step_batches(steps: list[Step], *, parallel_jobs: int) -> list[list[Step]]:
    batches: list[list[Step]] = []
    index = 0
    while index < len(steps):
        step = steps[index]
        if parallel_jobs < 2 or step.parallel_group is None:
            batches.append([step])
            index += 1
            continue

        group = [step]
        index += 1
        while (
            index < len(steps)
            and steps[index].parallel_group == step.parallel_group
        ):
            group.append(steps[index])
            index += 1

        batches.append(group if len(group) > 1 else [step])
    return batches


def _run_step_streaming(step: Step) -> StepResult:
    started_at = time.perf_counter()
    result = subprocess.run(list(step.argv), cwd=step.cwd, check=False)
    return StepResult(
        step=step,
        returncode=result.returncode,
        duration_seconds=time.perf_counter() - started_at,
    )


def _run_step_captured(step: Step) -> StepResult:
    started_at = time.perf_counter()
    with tempfile.TemporaryFile(mode="w+t", encoding="utf-8", errors="replace") as output_file:
        result = subprocess.run(
            list(step.argv),
            cwd=step.cwd,
            stdout=output_file,
            stderr=subprocess.STDOUT,
            check=False,
        )
        output_file.seek(0)
        output = output_file.read()
    return StepResult(
        step=step,
        returncode=result.returncode,
        duration_seconds=time.perf_counter() - started_at,
        output=output,
    )


def _print_step_result(result: StepResult) -> None:
    status = "PASSED" if result.returncode == 0 else "FAILED"
    print(
        f"\n{status}: {result.step.name} in {_format_duration(result.duration_seconds)}",
        flush=True,
    )


def _print_change_flags(title: str, flags: ChangeFlags) -> None:
    print(title, flush=True)
    print(f"  registry_changed: {flags.registry_changed}", flush=True)
    print(f"  runtime_changed: {flags.runtime_changed}", flush=True)
    print(f"  fixtures_changed: {flags.fixtures_changed}", flush=True)
    print(f"  inventory_changed: {flags.inventory_changed}", flush=True)
    print(f"  support_checks_changed: {flags.support_checks_changed}", flush=True)


def _warn_before_running(args: argparse.Namespace, changes: ChangeFlags) -> None:
    if args.track == "A" and (
        changes.registry_changed or changes.fixtures_changed or changes.inventory_changed
    ):
        print(
            "\nNOTE: Track A was selected, but registry/fixture/inventory changes were detected. "
            "Use Track B if those changes are part of this matcher rule change.",
            flush=True,
        )
    if args.track == "B" and changes.support_checks_changed and not args.include_support_self_checks:
        print(
            "\nNOTE: support-check files changed. Add --include-support-self-checks if those edits "
            "are part of this change.",
            flush=True,
        )
    if changes.registry_changed and not args.skip_baseline_promotion and args.baseline_output_dir is None:
        baseline_dir = APP_DIR / "languages" / "sv" / "ingredient_matching" / "term_registry" / "baselines"
        if not os.access(baseline_dir, os.W_OK):
            print(
                "\nERROR: baseline directory is not writable as the current user. "
                "Re-run as the file-owning user:\n"
                "  docker compose exec -T -u appuser -w /app web "
                "python support_checks/run_matcher_change_gates.py ...\n"
                "Or pass --baseline-output-dir to explicitly stage files for a read-only environment.",
                flush=True,
            )
            raise SystemExit(1)
    if _stages_baseline(args, changes):
        print(
            "\nNOTE: --baseline-output-dir stages generated files outside the checkout. "
            "This run will stop after baseline promotion; apply the staged files, then rerun gates "
            "without --baseline-output-dir.",
            flush=True,
        )
    if args.refresh_line_refs:
        inventory_file = contract_paths().inventory_file
        if not os.access(inventory_file, os.W_OK):
            print(
                "\nNOTE: inventory line-ref refresh needs a writable checkout. Run this wrapper from the host "
                "checkout or a write-enabled dev container when using --refresh-line-refs.",
                flush=True,
            )


def _run_parallel_batch(
    batch: list[Step],
    *,
    start_number: int,
    total_steps: int,
    parallel_jobs: int,
) -> list[StepResult]:
    group_name = batch[0].parallel_group or "readonly"
    worker_count = min(parallel_jobs, len(batch))
    print(
        f"\n=== {start_number}-{start_number + len(batch) - 1}/{total_steps}: "
        f"{group_name} ({worker_count} parallel jobs) ===",
        flush=True,
    )
    for offset, step in enumerate(batch):
        print(f"{start_number + offset}. {step.name}: {_display_command(step)}", flush=True)

    with ThreadPoolExecutor(max_workers=worker_count) as executor:
        futures = [executor.submit(_run_step_captured, step) for step in batch]
        results = [future.result() for future in futures]

    for result in results:
        print(f"\n--- output: {result.step.name} ---", flush=True)
        if result.output:
            print(result.output, end="" if result.output.endswith("\n") else "\n", flush=True)
        else:
            print("(no output)", flush=True)
        _print_step_result(result)
    return results


def _run_steps(
    steps: list[Step],
    *,
    dry_run: bool,
    parallel_readonly: bool,
    parallel_jobs: int,
) -> int:
    parallel_jobs = max(1, parallel_jobs if parallel_readonly else 1)
    batches = _step_batches(steps, parallel_jobs=parallel_jobs)

    print(f"\nPlanned steps: {len(steps)}", flush=True)
    for number, step in enumerate(steps, start=1):
        parallel_note = f" [parallel: {step.parallel_group}]" if step.parallel_group and parallel_jobs > 1 else ""
        print(f"{number}. {step.name}{parallel_note}: {_display_command(step)}", flush=True)
        print(f"   {step.reason}", flush=True)
    parallel_batches = [batch for batch in batches if len(batch) > 1]
    if parallel_batches:
        print(
            f"\nRead-only parallelism: {parallel_jobs} job(s), "
            f"{len(parallel_batches)} batch(es). Use --no-parallel-readonly to force serial execution.",
            flush=True,
        )

    if dry_run:
        print("\nDry run only. No commands executed.", flush=True)
        return 0

    started_at = time.perf_counter()
    failures: list[StepResult] = []
    step_number = 1
    for batch in batches:
        if len(batch) == 1:
            step = batch[0]
            print(f"\n=== {step_number}/{len(steps)}: {step.name} ===", flush=True)
            print(_display_command(step), flush=True)
            result = _run_step_streaming(step)
            _print_step_result(result)
            if result.returncode != 0:
                failures.append(result)
                break
        else:
            results = _run_parallel_batch(
                batch,
                start_number=step_number,
                total_steps=len(steps),
                parallel_jobs=parallel_jobs,
            )
            failures.extend(result for result in results if result.returncode != 0)
            if failures:
                break
        step_number += len(batch)

    total_duration = time.perf_counter() - started_at

    if failures:
        print("\nMatcher change gates failed:", flush=True)
        for result in failures:
            print(
                f"  {result.step.name}: exit {result.returncode} "
                f"after {_format_duration(result.duration_seconds)}",
                flush=True,
            )
        print(f"Total elapsed: {_format_duration(total_duration)}", flush=True)
        return 1

    print(f"\nAll selected matcher change gates passed in {_format_duration(total_duration)}.", flush=True)
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--track", choices=("A", "B"), required=True)
    parser.add_argument("--dry-run", action="store_true", help="Print planned gates without running them.")
    parser.add_argument(
        "--parallel-readonly",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Run independent read-only gate steps in parallel. Defaults to enabled.",
    )
    parser.add_argument(
        "--parallel-readonly-jobs",
        type=int,
        default=None,
        help="Worker process count for read-only gate batches. Defaults to available CPU cores minus one.",
    )
    parser.add_argument(
        "--tree-root",
        type=Path,
        default=None,
        help="Run path-aware gates against this checkout/tree root instead of the live /app tree.",
    )
    parser.add_argument("--case-id", action="append", help="Target this fixture id. Can be repeated.")
    parser.add_argument("--policy-ref", action="append", help="Target this policy_ref. Can be repeated.")
    parser.add_argument("--canonical", action="append", help="Target this canonical. Can be repeated.")
    parser.add_argument(
        "--auto-detect",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Infer changed areas from git status when explicit change flags are not provided.",
    )
    parser.add_argument("--registry-changed", action=argparse.BooleanOptionalAction, default=None)
    parser.add_argument("--runtime-changed", action=argparse.BooleanOptionalAction, default=None)
    parser.add_argument("--fixtures-changed", action=argparse.BooleanOptionalAction, default=None)
    parser.add_argument("--inventory-changed", action=argparse.BooleanOptionalAction, default=None)
    parser.add_argument("--support-checks-changed", action=argparse.BooleanOptionalAction, default=None)
    parser.add_argument(
        "--skip-baseline-promotion",
        action="store_true",
        help="Skip promote_term_baseline.py even when registry changes are selected.",
    )
    parser.add_argument(
        "--migrate-hashes",
        action="store_true",
        help="Backward-compatible no-op alias; baseline hash-equivalent ID migrations are automatic.",
    )
    parser.add_argument(
        "--allow-removals",
        action="store_true",
        help="Pass --allow-removals to promote_term_baseline.py after confirming intentional removals.",
    )
    parser.add_argument(
        "--confirm-large-removals",
        action="store_true",
        help="Pass --confirm-large-removals to promote_term_baseline.py after reviewing large removals.",
    )
    parser.add_argument(
        "--baseline-output-dir",
        type=Path,
        default=None,
        help=(
            "Pass --output-dir to promote_term_baseline.py for read-only containers. "
            "The wrapper stops after staged promotion so staged files can be applied before final gates."
        ),
    )
    parser.add_argument(
        "--refresh-line-refs",
        action="store_true",
        help="Run refresh_matcher_rule_inventory_line_refs.py --write before inventory checks.",
    )
    parser.add_argument(
        "--reload-cache",
        action="store_true",
        help="Run dev_reload.py before optional fresh-cache gates.",
    )
    parser.add_argument(
        "--fresh-cache-gates",
        action="store_true",
        help="Run fixture/parity gates without --skip-cache-freshness at the end.",
    )
    parser.add_argument(
        "--include-support-self-checks",
        action="store_true",
        help="Run support-check self-tests for fixture schema, diagnostics, and parity tooling.",
    )
    parser.add_argument(
        "--support-self-test-jobs",
        type=int,
        default=None,
        help=(
            "Worker process count for the rule-change-flow unittest-parallel self-test. "
            "Defaults to CPU cores minus one."
        ),
    )
    parser.add_argument(
        "--generate-coverage",
        action=argparse.BooleanOptionalAction,
        default=True,
        help=(
            "For Track B fixture/inventory changes, refresh generated matcher contract JSON "
            "and registry coverage TOML before pre-flight."
        ),
    )
    args = parser.parse_args()
    if args.support_self_test_jobs is not None and args.support_self_test_jobs < 1:
        parser.error("--support-self-test-jobs must be at least 1")
    if args.parallel_readonly_jobs is not None and args.parallel_readonly_jobs < 1:
        parser.error("--parallel-readonly-jobs must be at least 1")
    return args


def main() -> int:
    args = parse_args()
    repo_root = repo_root_for_tree_root(args.tree_root) if args.tree_root is not None else _discover_repo_root()
    changed_paths, git_error = _git_changed_paths(repo_root) if args.auto_detect else (set(), None)
    detected = _detect_change_flags(changed_paths)
    changes = _resolved_change_flags(args, detected)
    generated_coverage_refresh = (
        args.track == "B"
        and args.generate_coverage
        and (changes.fixtures_changed or changes.inventory_changed)
    )
    generated_coverage_stale = _generated_coverage_is_stale(args) if generated_coverage_refresh else False
    if (generated_coverage_refresh or generated_coverage_stale) and not changes.registry_changed:
        changes = ChangeFlags(
            registry_changed=True,
            runtime_changed=changes.runtime_changed,
            fixtures_changed=changes.fixtures_changed,
            inventory_changed=changes.inventory_changed,
            support_checks_changed=changes.support_checks_changed,
        )

    print(f"Repo root: {repo_root}", flush=True)
    if git_error:
        print(f"Git auto-detect unavailable: {git_error}", flush=True)
    elif args.auto_detect:
        print(f"Git auto-detect saw {len(changed_paths)} changed path(s).", flush=True)
        _print_change_flags("Detected change flags:", detected)
    _print_change_flags("Selected change flags:", changes)
    _warn_before_running(args, changes)

    steps: list[Step] = []
    if generated_coverage_refresh:
        steps.append(_generated_contract_json_step(args))
        steps.append(_generated_coverage_step(args))
    if args.track == "B" and _stages_baseline(args, changes):
        steps.append(_baseline_promotion_step(args))
        return _run_steps(
            steps,
            dry_run=args.dry_run,
            parallel_readonly=args.parallel_readonly,
            parallel_jobs=_parallel_readonly_jobs(args),
        )
    if args.track == "B" and changes.registry_changed and not args.skip_baseline_promotion:
        steps.append(_baseline_promotion_step(args))
    steps.append(_preflight_step(args))
    if args.track == "A":
        steps.extend(_build_track_a_steps(args))
    else:
        steps.extend(_build_track_b_steps(args, changes))
    return _run_steps(
        steps,
        dry_run=args.dry_run,
        parallel_readonly=args.parallel_readonly,
        parallel_jobs=_parallel_readonly_jobs(args),
    )


if __name__ == "__main__":
    raise SystemExit(main())
