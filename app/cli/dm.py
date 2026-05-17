"""Deal Meals developer CLI."""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
import tomllib
from typing import Annotated
import unicodedata

import typer


APP_DIR = Path(__file__).resolve().parents[1]
REPO_DIR = APP_DIR.parent
SUPPORT_CHECKS_DIR = APP_DIR / "support_checks"
SV_DIR = APP_DIR / "languages" / "sv"

DEFAULT_FIXTURE_FILE = SV_DIR / "matcher_contracts" / "matcher_regression_cases.json"
DEFAULT_INVENTORY_FILE = SV_DIR / "matcher_contracts" / "matcher_rule_inventory.json"
DEFAULT_KEYWORD_EXTRA_PARENT_FILE = (
    SV_DIR / "ingredient_matching" / "term_registry" / "entries" / "keyword_extra_parent.toml"
)
DEFAULT_DEEP_SANITY_FILE = SUPPORT_CHECKS_DIR / "run_deep_matcher_sanity.py"


app = typer.Typer(help="Deal Meals developer tools.")
matcher_app = typer.Typer(help="Matcher rule-change workflows.")
matcher_add_app = typer.Typer(help="Generate matcher rule-change artifacts.")
matcher_app.add_typer(matcher_add_app, name="add")
app.add_typer(matcher_app, name="matcher")


@dataclass(frozen=True)
class MatcherPaths:
    tree_root: Path
    app_dir: Path
    repo_root: Path
    fixture_file: Path
    inventory_file: Path
    keyword_extra_parent_file: Path
    deep_sanity_file: Path


@dataclass(frozen=True)
class MatcherChangePlan:
    command: str
    policy_ref: str
    entry_ids: tuple[str, ...]
    fixture_ids: tuple[str, ...]
    inventory_id: str | None
    toml_preview: str
    sanity_preview: str
    runtime_delta_filename: str | None = None

    @property
    def first_fixture_id(self) -> str:
        if not self.fixture_ids:
            raise typer.BadParameter(f"{self.command} generated no fixture ids")
        return self.fixture_ids[0]


def _app_dir_for_tree_root(tree_root: Path | None) -> Path:
    if tree_root is None:
        return APP_DIR
    root = tree_root.resolve()
    if (root / "app").is_dir():
        return root / "app"
    return root


def _paths(tree_root: Path | None) -> MatcherPaths:
    app_dir = _app_dir_for_tree_root(tree_root)
    repo_root = app_dir.parent if app_dir.name == "app" else app_dir
    return MatcherPaths(
        tree_root=repo_root,
        app_dir=app_dir,
        repo_root=repo_root,
        fixture_file=app_dir / "languages" / "sv" / "matcher_contracts" / "matcher_regression_cases.json",
        inventory_file=app_dir / "languages" / "sv" / "matcher_contracts" / "matcher_rule_inventory.json",
        keyword_extra_parent_file=(
            app_dir
            / "languages"
            / "sv"
            / "ingredient_matching"
            / "term_registry"
            / "entries"
            / "keyword_extra_parent.toml"
        ),
        deep_sanity_file=app_dir / "support_checks" / "run_deep_matcher_sanity.py",
    )


def _slug(value: str, *, fallback: str = "term") -> str:
    cleaned = value.strip().lower()
    cleaned = (
        cleaned.replace("å", "a")
        .replace("ä", "a")
        .replace("ö", "o")
        .replace("é", "e")
    )
    normalized = unicodedata.normalize("NFKD", cleaned)
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-z0-9]+", "_", ascii_text).strip("_")
    return slug or fallback


def _split_csv(value: str, *, label: str, lowercase: bool = True) -> tuple[str, ...]:
    items = tuple(
        item.strip().lower() if lowercase else item.strip()
        for item in value.split(",")
        if item.strip()
    )
    if not items:
        raise typer.BadParameter(f"{label} must contain at least one value")
    duplicates = sorted({item for item in items if items.count(item) > 1})
    if duplicates:
        raise typer.BadParameter(f"{label} contains duplicates: {', '.join(duplicates)}")
    return items


def _titleish(value: str) -> str:
    return " ".join(part.capitalize() for part in value.split())


def _toml_string(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def _toml_array(values: tuple[str, ...] | list[str]) -> str:
    return "[" + ", ".join(_toml_string(value) for value in values) + "]"


def _load_json_list(path: Path) -> list[dict]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise typer.BadParameter(f"{path} must contain a JSON list")
    return payload


def _write_json_list(path: Path, payload: list[dict]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _append_json_list_items(path: Path, items: tuple[dict, ...], *, dry_run: bool) -> None:
    payload = _load_json_list(path)
    payload.extend(items)
    if not dry_run:
        _write_json_list(path, payload)


def _append_text_block(path: Path, block: str, *, dry_run: bool, trim_existing: bool = False) -> None:
    if dry_run:
        return
    existing_text = path.read_text(encoding="utf-8")
    if trim_existing:
        path.write_text(existing_text.rstrip() + "\n" + block, encoding="utf-8")
        return
    separator = "" if existing_text.endswith("\n\n") else "\n"
    path.write_text(existing_text + separator + block, encoding="utf-8")


def _existing_entry_ids(path: Path) -> set[str]:
    if not path.exists():
        return set()
    return set(re.findall(r'^entry_id = "([^"]+)"', path.read_text(encoding="utf-8"), flags=re.MULTILINE))


def _ensure_can_add_keyword_extra_parent(
    *,
    paths: MatcherPaths,
    canonical: str,
    kids: tuple[str, ...],
    fixture_ids: tuple[str, ...],
    inventory_id: str,
) -> None:
    fixtures = _load_json_list(paths.fixture_file)
    existing_fixture_ids = {str(item.get("id") or "") for item in fixtures if isinstance(item, dict)}
    duplicate_fixtures = sorted(set(fixture_ids) & existing_fixture_ids)
    if duplicate_fixtures:
        raise typer.BadParameter(f"fixture already exists: {', '.join(duplicate_fixtures)}")

    inventory = _load_json_list(paths.inventory_file)
    existing_inventory_ids = {str(item.get("id") or "") for item in inventory if isinstance(item, dict)}
    if inventory_id in existing_inventory_ids:
        raise typer.BadParameter(f"inventory entry already exists: {inventory_id}")

    toml_payload = tomllib.loads(paths.keyword_extra_parent_file.read_text(encoding="utf-8"))
    entries = toml_payload.get("entries", [])
    if not isinstance(entries, list):
        raise typer.BadParameter(f"{paths.keyword_extra_parent_file} must contain TOML [[entries]]")
    for kid in kids:
        has_mapping = any(
            isinstance(entry, dict)
            and str(entry.get("canonical") or "").lower() == canonical
            and kid in {str(variant).lower() for variant in entry.get("variants", [])}
            for entry in entries
        )
        if has_mapping:
            raise typer.BadParameter(f"keyword_extra_parent coverage already exists: {kid} -> {canonical}")


def _next_numeric_suffix(entry_ids: set[str]) -> int:
    suffixes = []
    for entry_id in entry_ids:
        match = re.search(r"_(\d+)$", entry_id)
        if match:
            suffixes.append(int(match.group(1)))
    return (max(suffixes) + 1) if suffixes else 1


def _keyword_extra_parent_block(
    *,
    entry_id: str,
    canonical: str,
    kid: str,
    source_ref: str,
    ingredient: str,
    offer_name: str,
) -> str:
    return "\n".join([
        "[[entries]]",
        f"entry_id = {_toml_string(entry_id)}",
        'language = "sv"',
        'market = "SE"',
        f"canonical = {_toml_string(canonical)}",
        'status = "active"',
        f"variants = {_toml_array((kid,))}",
        f"route_terms = {_toml_array((canonical,))}",
        f"source_refs = {_toml_array((source_ref,))}",
        'layer_policy = ["route_only"]',
        f"notes = {_toml_string('Generated by dm matcher add keyword-extra-parent.')}",
        "",
        "[[entries.coverage]]",
        'source_family = "keyword_extra_parent"',
        f"canonical = {_toml_string(canonical)}",
        f"variant = {_toml_string(kid)}",
        'layer_role = "keyword_extra_parent_mapping"',
        "",
        "[[entries.positive_examples]]",
        f"ingredient = {_toml_string(ingredient)}",
        f"offer_name = {_toml_string(offer_name)}",
        "expected = 1",
        "",
    ])


def _append_keyword_extra_parent_entries(
    *,
    paths: MatcherPaths,
    canonical: str,
    kids: tuple[str, ...],
    offer_names: tuple[str, ...],
    source_ref: str,
    ingredient: str,
    dry_run: bool,
) -> tuple[tuple[str, ...], int, str]:
    existing_ids = _existing_entry_ids(paths.keyword_extra_parent_file)
    suffix = _next_numeric_suffix(existing_ids)
    canonical_slug = _slug(canonical)
    entry_ids: list[str] = []
    blocks: list[str] = []
    for kid, offer_name in zip(kids, offer_names, strict=True):
        base = f"sv-se.family.{canonical_slug}.{_slug(kid)}"
        entry_id = f"{base}_{suffix:03d}"
        while entry_id in existing_ids:
            suffix += 1
            entry_id = f"{base}_{suffix:03d}"
        suffix += 1
        existing_ids.add(entry_id)
        entry_ids.append(entry_id)
        blocks.append(_keyword_extra_parent_block(
            entry_id=entry_id,
            canonical=canonical,
            kid=kid,
            source_ref=source_ref,
            ingredient=ingredient,
            offer_name=offer_name,
        ))

    existing_text = paths.keyword_extra_parent_file.read_text(encoding="utf-8")
    start_line = len(existing_text.splitlines()) + 1
    append_text = "\n".join(blocks)
    _append_text_block(paths.keyword_extra_parent_file, append_text, dry_run=dry_run)
    return tuple(entry_ids), start_line, append_text


def _append_fixtures(
    *,
    paths: MatcherPaths,
    canonical: str,
    kids: tuple[str, ...],
    offer_names: tuple[str, ...],
    recipe_name: str,
    ingredient: str,
    offer_category: str,
    policy_ref: str,
    source_ref: str,
    dry_run: bool,
) -> tuple[str, ...]:
    fixture_ids = []
    fixture_rows: list[dict] = []
    canonical_slug = _slug(canonical)
    for kid, offer_name in zip(kids, offer_names, strict=True):
        fixture_id = f"keyword_extra_parent_{canonical_slug}_{_slug(kid)}_positive"
        fixture_ids.append(fixture_id)
        fixture_rows.append({
            "id": fixture_id,
            "policy_ref": policy_ref,
            "source_ref": source_ref,
            "recipe_name": recipe_name,
            "ingredients": [ingredient],
            "expected_matches": [
                {
                    "canonical": canonical,
                    "ingredient_index": 0,
                    "must_match_keyword": canonical,
                }
            ],
            "offer": {
                "name": offer_name,
                "category": offer_category,
            },
            "expected": 1,
        })
    _append_json_list_items(paths.fixture_file, tuple(fixture_rows), dry_run=dry_run)
    return tuple(fixture_ids)


def _append_inventory(
    *,
    paths: MatcherPaths,
    canonical: str,
    kids: tuple[str, ...],
    fixture_ids: tuple[str, ...],
    policy_ref: str,
    source_ref: str,
    inventory_id: str,
    first_entry_id: str,
    first_entry_line: int,
    dry_run: bool,
) -> None:
    kids_text = ", ".join(kids)
    inventory_row = {
        "id": inventory_id,
        "status": "wrapped_adapter",
        "kind": "legacy_parent",
        "canonical": canonical,
        "owner": "matcher",
        "policy_ref": policy_ref,
        "source_refs": [source_ref],
        "fixture_refs": list(fixture_ids),
        "risk": "policy_term",
        "adapter_ref": f"matcher_layer_diagnostics:{policy_ref}",
        "line_refs": [
            {
                "path": "app/languages/sv/ingredient_matching/term_registry/entries/keyword_extra_parent.toml",
                "start": first_entry_line,
                "end": first_entry_line,
                "anchor": f"entry_id = \"{first_entry_id}\"",
            }
        ],
        "notes": (
            f"{kids_text} roll up to generic {canonical} for recipes that ask for "
            "the parent family. Generated by dm matcher add keyword-extra-parent."
        ),
    }
    _append_json_list_items(paths.inventory_file, (inventory_row,), dry_run=dry_run)


def _append_deep_sanity_stub(
    *,
    paths: MatcherPaths,
    canonical: str,
    kids: tuple[str, ...],
    offer_names: tuple[str, ...],
    ingredient: str,
    offer_category: str,
    policy_ref: str,
    dry_run: bool,
) -> str:
    lines = [
        "",
        f"# {policy_ref}: generated by dm matcher add keyword-extra-parent",
    ]
    for kid, offer_name in zip(kids, offer_names, strict=True):
        lines.extend([
            f"test({_toml_string(_titleish(canonical) + ' recipe matches ' + kid)},",
            f"     match({_toml_string(offer_name)}, {_toml_string(ingredient)}, {_toml_string(offer_category)}), {_toml_string(canonical)})",
        ])
    block = "\n".join(lines) + "\n"
    _append_text_block(paths.deep_sanity_file, block, dry_run=dry_run, trim_existing=True)
    return block


def _run(argv: list[str], *, cwd: Path, env: dict[str, str] | None = None) -> int:
    print("+ " + " ".join(str(part) for part in argv), flush=True)
    return subprocess.run(argv, cwd=cwd, env=env, check=False).returncode


def _run_coverage_generator(paths: MatcherPaths) -> int:
    argv = [
        sys.executable,
        str(SUPPORT_CHECKS_DIR / "generate_matcher_registry_coverage.py"),
        "--tree-root",
        str(paths.repo_root),
        "--write",
    ]
    return _run(argv, cwd=paths.repo_root)


def _write_runtime_delta_entries(paths: MatcherPaths, filename: str, toml_text: str) -> Path:
    runtime_entries_dir = paths.repo_root / ".dm_matcher_runtime_entries"
    runtime_entries_dir.mkdir(parents=True, exist_ok=True)
    (runtime_entries_dir / filename).write_text(toml_text, encoding="utf-8")
    return runtime_entries_dir


def _gate_env(
    paths: MatcherPaths,
    report_root: Path | None,
    runtime_entries_dir: Path | None,
) -> dict[str, str]:
    env = os.environ.copy()
    env.setdefault("DEAL_MEALS_SUPPORT_REPORT_ROOT", "/tmp/deal-meals-support-checks-dm")
    if report_root is not None:
        env["DEAL_MEALS_SUPPORT_REPORT_ROOT"] = str(report_root)
    if runtime_entries_dir is not None:
        env["TERM_REGISTRY_EXTRA_ENTRIES_DIRS"] = str(runtime_entries_dir)
        env.pop("TERM_REGISTRY_DISABLE_LOCAL_ENTRIES", None)
    return env


def _run_track_b_gates(
    *,
    paths: MatcherPaths,
    policy_ref: str,
    first_fixture_id: str,
    report_root: Path | None,
    runtime_entries_dir: Path | None,
) -> int:
    argv = [
        sys.executable,
        str(SUPPORT_CHECKS_DIR / "run_matcher_change_gates.py"),
        "--track",
        "B",
        "--policy-ref",
        policy_ref,
        "--case-id",
        first_fixture_id,
        "--fixtures-changed",
        "--inventory-changed",
    ]
    if paths.app_dir == APP_DIR:
        argv.extend(["--registry-changed", "--runtime-changed"])
    else:
        argv.extend([
            "--tree-root",
            str(paths.repo_root),
            "--no-registry-changed",
            "--no-runtime-changed",
            "--no-support-checks-changed",
        ])
    return _run(argv, cwd=APP_DIR, env=_gate_env(paths, report_root, runtime_entries_dir))


def _run_track_b_change_plan(
    *,
    paths: MatcherPaths,
    change: MatcherChangePlan,
    report_root: Path | None,
) -> int:
    coverage_status = _run_coverage_generator(paths)
    if coverage_status != 0:
        return coverage_status

    runtime_entries_dir = (
        _write_runtime_delta_entries(paths, change.runtime_delta_filename, change.toml_preview)
        if paths.app_dir != APP_DIR and change.runtime_delta_filename is not None
        else None
    )
    return _run_track_b_gates(
        paths=paths,
        policy_ref=change.policy_ref,
        first_fixture_id=change.first_fixture_id,
        report_root=report_root,
        runtime_entries_dir=runtime_entries_dir,
    )


def _print_dry_run_preview(change: MatcherChangePlan) -> None:
    if change.toml_preview:
        typer.echo(change.toml_preview)
    if change.sanity_preview:
        typer.echo(change.sanity_preview)
    typer.echo("Dry run only; no files written.")


def _run_preflight(paths: MatcherPaths, report_root: Path | None) -> int:
    argv = [sys.executable, str(SUPPORT_CHECKS_DIR / "run_matcher_change_preflight.py")]
    if paths.app_dir != APP_DIR:
        argv.extend(["--tree-root", str(paths.repo_root)])
    return _run(argv, cwd=APP_DIR, env=_gate_env(paths, report_root, None))


def _watch_files(paths: MatcherPaths) -> tuple[Path, ...]:
    entries_dir = paths.app_dir / "languages" / "sv" / "ingredient_matching" / "term_registry" / "entries"
    files = [
        paths.fixture_file,
        paths.inventory_file,
        paths.deep_sanity_file,
        *sorted(entries_dir.glob("*.toml")),
    ]
    return tuple(path for path in files if path.exists())


def _mtime_snapshot(files: tuple[Path, ...]) -> dict[Path, int]:
    return {path: path.stat().st_mtime_ns for path in files if path.exists()}


def _validate_keyword_extra_parent_args(canonical: str, kids: tuple[str, ...]) -> None:
    if not canonical.strip():
        raise typer.BadParameter("canonical must not be empty")
    if any(kid == canonical for kid in kids):
        raise typer.BadParameter("kids must differ from canonical")
    if any(re.search(r"\s", kid) for kid in kids):
        raise typer.BadParameter("keyword-extra-parent currently supports single-token kids only")


@matcher_add_app.command("keyword-extra-parent")
def add_keyword_extra_parent(
    canonical: Annotated[str, typer.Argument(help="Existing parent canonical, e.g. citrusfrukter.")],
    kids_csv: Annotated[
        str,
        typer.Option(
            "--kids",
            help="Comma-separated child/product terms that should roll up to the parent canonical.",
        ),
    ],
    recipe_name: Annotated[str, typer.Option("--recipe-name", help="Recipe name for generated positive fixtures.")],
    ingredient: Annotated[str, typer.Option("--ingredient", help="Ingredient text for generated fixtures.")],
    offer_names_csv: Annotated[
        str | None,
        typer.Option("--offer-names", help="Optional comma-separated offer names matching --kids order."),
    ] = None,
    offer_category: Annotated[str, typer.Option("--offer-category", help="Offer category used in fixtures.")] = "pantry",
    policy_ref: Annotated[str | None, typer.Option("--policy-ref", help="Stable policy ref override.")] = None,
    source_ref: Annotated[str | None, typer.Option("--source-ref", help="Stable source ref override.")] = None,
    inventory_id_override: Annotated[
        str | None,
        typer.Option("--inventory-id", help="Stable inventory id override."),
    ] = None,
    tree_root: Annotated[Path | None, typer.Option("--tree-root", help="Repo/tree root to edit instead of /app.")] = None,
    run_gates: Annotated[
        bool,
        typer.Option("--run-gates/--no-run-gates", help="Run generated coverage and Track B gates after writing."),
    ] = True,
    report_root: Annotated[
        Path | None,
        typer.Option("--report-root", help="Writable DEAL_MEALS_SUPPORT_REPORT_ROOT for generated reports."),
    ] = None,
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Print generated blocks without writing files.")] = False,
) -> None:
    kids = _split_csv(kids_csv, label="--kids")
    offer_names = (
        _split_csv(offer_names_csv, label="--offer-names", lowercase=False)
        if offer_names_csv
        else tuple(_titleish(kid) for kid in kids)
    )
    if len(offer_names) != len(kids):
        raise typer.BadParameter("--offer-names must have the same item count as --kids")
    canonical = canonical.strip().lower()
    _validate_keyword_extra_parent_args(canonical, kids)

    canonical_slug = _slug(canonical)
    policy_ref = policy_ref or f"keyword_extra_parent_{canonical_slug}_family"
    source_ref = source_ref or f"current_review:keyword_extra_parent_{canonical_slug}_routing"
    inventory_id = (
        inventory_id_override.strip()
        if inventory_id_override is not None
        else f"legacy_parent_{canonical_slug}_family"
    )
    if not inventory_id:
        raise typer.BadParameter("--inventory-id must not be empty")
    paths = _paths(tree_root)
    planned_fixture_ids = tuple(
        f"keyword_extra_parent_{canonical_slug}_{_slug(kid)}_positive"
        for kid in kids
    )
    _ensure_can_add_keyword_extra_parent(
        paths=paths,
        canonical=canonical,
        kids=kids,
        fixture_ids=planned_fixture_ids,
        inventory_id=inventory_id,
    )

    entry_ids, first_entry_line, toml_preview = _append_keyword_extra_parent_entries(
        paths=paths,
        canonical=canonical,
        kids=kids,
        offer_names=offer_names,
        source_ref=f"registry:keyword_extra_parent_entries:{policy_ref}",
        ingredient=ingredient,
        dry_run=dry_run,
    )
    fixture_ids = _append_fixtures(
        paths=paths,
        canonical=canonical,
        kids=kids,
        offer_names=offer_names,
        recipe_name=recipe_name,
        ingredient=ingredient,
        offer_category=offer_category,
        policy_ref=policy_ref,
        source_ref=source_ref,
        dry_run=dry_run,
    )
    _append_inventory(
        paths=paths,
        canonical=canonical,
        kids=kids,
        fixture_ids=fixture_ids,
        policy_ref=policy_ref,
        source_ref=source_ref,
        inventory_id=inventory_id,
        first_entry_id=entry_ids[0],
        first_entry_line=first_entry_line,
        dry_run=dry_run,
    )
    sanity_preview = _append_deep_sanity_stub(
        paths=paths,
        canonical=canonical,
        kids=kids,
        offer_names=offer_names,
        ingredient=ingredient,
        offer_category=offer_category,
        policy_ref=policy_ref,
        dry_run=dry_run,
    )

    change = MatcherChangePlan(
        command="keyword-extra-parent",
        policy_ref=policy_ref,
        entry_ids=entry_ids,
        fixture_ids=fixture_ids,
        inventory_id=inventory_id,
        toml_preview=toml_preview,
        sanity_preview=sanity_preview,
        runtime_delta_filename="keyword_extra_parent.toml",
    )

    if dry_run:
        _print_dry_run_preview(change)
        return

    typer.echo(f"Generated keyword_extra_parent rule: {change.policy_ref}")
    typer.echo(f"  entries: {', '.join(change.entry_ids)}")
    typer.echo(f"  fixtures: {', '.join(change.fixture_ids)}")
    typer.echo(f"  inventory: {change.inventory_id}")

    if not run_gates:
        typer.echo("Skipped gates (--no-run-gates).")
        return

    gate_status = _run_track_b_change_plan(paths=paths, change=change, report_root=report_root)
    raise typer.Exit(gate_status)


@matcher_app.command("dev-watch")
def matcher_dev_watch(
    tree_root: Annotated[Path | None, typer.Option("--tree-root", help="Repo/tree root to watch instead of /app.")] = None,
    interval: Annotated[
        float,
        typer.Option("--interval", min=0.25, help="Polling interval in seconds; default reports within 5 seconds."),
    ] = 1.0,
    report_root: Annotated[
        Path | None,
        typer.Option("--report-root", help="Writable DEAL_MEALS_SUPPORT_REPORT_ROOT for generated reports."),
    ] = None,
    once: Annotated[bool, typer.Option("--once", help="Run pre-flight once and exit.")] = False,
) -> None:
    paths = _paths(tree_root)
    files = _watch_files(paths)
    typer.echo(f"Watching {len(files)} matcher file(s); press Ctrl-C to stop.")
    status = _run_preflight(paths, report_root)
    if once:
        raise typer.Exit(status)

    snapshot = _mtime_snapshot(files)
    try:
        while True:
            time.sleep(interval)
            current_files = _watch_files(paths)
            current = _mtime_snapshot(current_files)
            if current != snapshot:
                changed = sorted(
                    str(path.relative_to(paths.repo_root) if path.is_relative_to(paths.repo_root) else path)
                    for path in set(current) | set(snapshot)
                    if current.get(path) != snapshot.get(path)
                )
                typer.echo("")
                typer.echo(f"Change detected: {', '.join(changed[:6])}")
                if len(changed) > 6:
                    typer.echo(f"... and {len(changed) - 6} more")
                status = _run_preflight(paths, report_root)
                snapshot = current
    except KeyboardInterrupt:
        typer.echo("")
        typer.echo("Stopped matcher dev-watch.")
        raise typer.Exit(status)


@matcher_app.command(
    "gates",
    context_settings={"allow_extra_args": True, "ignore_unknown_options": True},
)
def matcher_gates(
    ctx: typer.Context,
    report_root: Annotated[
        Path | None,
        typer.Option("--report-root", help="Writable DEAL_MEALS_SUPPORT_REPORT_ROOT for generated reports."),
    ] = None,
) -> None:
    env = os.environ.copy()
    env.setdefault("DEAL_MEALS_SUPPORT_REPORT_ROOT", "/tmp/deal-meals-support-checks-dm")
    if report_root is not None:
        env["DEAL_MEALS_SUPPORT_REPORT_ROOT"] = str(report_root)
    status = _run(
        [sys.executable, str(SUPPORT_CHECKS_DIR / "run_matcher_change_gates.py"), *ctx.args],
        cwd=APP_DIR,
        env=env,
    )
    raise typer.Exit(status)


def main() -> None:
    app()


if __name__ == "__main__":
    main()
