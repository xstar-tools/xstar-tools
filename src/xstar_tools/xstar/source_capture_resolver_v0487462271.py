"""Resolve, verify, or atomically rebuild the all-61 v0.6.47.2 source capture.

This module prevents qualification runners from trusting a source-capture path
merely because it exists.  Every candidate is verified with the current v21.2
contract.  If no candidate is valid, a fresh capture is built from the frozen
source archive and ATDB, verified, and atomically promoted for reuse.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any, Iterable

from xstar_tools.xstar import v0472_all61_independent_thermal_capture_v048746212 as capture_mod

RELEASE = "0.6.48.7.46.21.17.2"
SCHEMA = "xstar-tools-v06487462272-source-capture-resolver-v2"
CAPTURE_BASENAME = "v0472_all61_independent_thermal_capture"


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def _candidate_key(path: Path) -> tuple[int, int, str]:
    text = str(path)
    # Prefer the v21.2 corrected capture, then a persistent capture generated in
    # the current output directory, and only then older lineage copies.
    preferred = 0 if "v048746212" in text else 1
    generated = 0 if ".source_capture" not in text and path.name == CAPTURE_BASENAME else 1
    return (preferred, generated, text)


def _dedupe(paths: Iterable[Path]) -> list[Path]:
    seen: set[str] = set()
    result: list[Path] = []
    for path in paths:
        try:
            key = str(path.expanduser().resolve())
        except OSError:
            key = str(path.expanduser().absolute())
        if key in seen:
            continue
        seen.add(key)
        result.append(Path(key))
    return result


def _discovered_candidates(
    search_roots: Iterable[Path], limit: int = 64, max_depth: int = 5
) -> list[Path]:
    found: list[Path] = []
    for root in _dedupe(search_roots):
        if not root.is_dir():
            continue
        # Avoid following symlink loops and skip large generated native replay
        # trees.  The desired bundle always has the fixed basename.
        for current, dirs, _files in os.walk(root, followlinks=False):
            here = Path(current)
            try:
                depth = len(here.relative_to(root).parts)
            except ValueError:
                depth = max_depth + 1
            if depth >= max_depth:
                dirs[:] = []
            dirs[:] = [
                d for d in dirs
                if d not in {".git", "build", "dist", "native_all61", "v048746227_native_fixed_replay"}
                and not d.startswith("evaluation_")
            ]
            if here.name == CAPTURE_BASENAME:
                found.append(here)
                dirs[:] = []
                if len(found) >= limit:
                    return sorted(_dedupe(found), key=_candidate_key)
    return sorted(_dedupe(found), key=_candidate_key)


def _verify(path: Path) -> dict[str, Any]:
    if not path.is_dir():
        return {"result": "REJECT", "errors": ["not_a_directory"]}
    try:
        return capture_mod.verify(path)
    except Exception as exc:  # keep candidate failures diagnostic, not fatal
        return {"result": "REJECT", "errors": [f"{type(exc).__name__}: {exc}"]}


def resolve(
    *,
    candidates: Iterable[Path],
    search_roots: Iterable[Path],
    generated_dir: Path,
    source_archive: Path,
    atdb_path: Path,
    parameters_json: Path,
    coheat_path: Path | None,
    force_recapture: bool = False,
) -> dict[str, Any]:
    generated_dir = generated_dir.resolve()
    explicit = _dedupe(candidates)
    skipped_candidates: list[dict[str, Any]] = []
    rejected_candidates: list[dict[str, Any]] = []

    def compact_rejection(candidate: Path, verification: dict[str, Any]) -> dict[str, Any]:
        errors = list(verification.get("errors", []))
        return {
            "path": str(candidate),
            "result": verification.get("result", "REJECT"),
            "evaluations": int(verification.get("evaluations", 0) or 0),
            "type99_capture_result": verification.get("type99_capture_result", "MISSING"),
            "error_count": len(errors),
            "first_error": errors[0] if errors else "verification_rejected",
        }

    def accepted_report(candidate: Path, mode: str, recaptured: bool) -> dict[str, Any]:
        return {
            "schema": SCHEMA,
            "release": RELEASE,
            "result": "ACCEPT",
            "selected_dir": str(candidate.resolve()),
            "selected_mode": mode,
            "recaptured": recaptured,
            "skipped_candidates": skipped_candidates,
            "rejected_candidates": rejected_candidates,
            "errors": [],
            "qualification_only": True,
            "product_level_parity": "NOT_IN_SCOPE",
            "production_promotion_ready": False,
        }

    def try_candidates(paths: Iterable[Path]) -> dict[str, Any] | None:
        for candidate in _dedupe(paths):
            if not candidate.is_dir():
                skipped_candidates.append({"path": str(candidate), "reason": "not_present"})
                continue
            verification = _verify(candidate)
            if verification.get("result") == "ACCEPT" and int(verification.get("evaluations", 0)) == 61:
                return accepted_report(candidate, "verified_reuse", False)
            rejected_candidates.append(compact_rejection(candidate, verification))
        return None

    if not force_recapture:
        # Explicit candidates are authoritative and cheap.  The generated cache
        # is checked next, then bounded discovery is used only as a fallback.
        selected = try_candidates([*explicit, generated_dir])
        if selected is not None:
            return selected
        selected = try_candidates(_discovered_candidates(search_roots))
        if selected is not None:
            return selected

    generated_dir.parent.mkdir(parents=True, exist_ok=True)
    temp_parent = generated_dir.parent
    temp_dir = Path(tempfile.mkdtemp(prefix=f".{generated_dir.name}.", dir=temp_parent))
    backup_dir = generated_dir.with_name(f".{generated_dir.name}.previous")
    try:
        captured = capture_mod.capture(
            source_archive.resolve(), atdb_path.resolve(), temp_dir,
            parameters_json.resolve(), coheat_path.resolve() if coheat_path else None,
        )
        if captured.get("result") != "ACCEPT" or int(captured.get("evaluations", 0)) != 61:
            rejected_candidates.append(compact_rejection(temp_dir, captured))
            return {
                "schema": SCHEMA, "release": RELEASE, "result": "REJECT",
                "errors": ["fresh source capture did not satisfy the v21.2 all-61 contract"],
                "skipped_candidates": skipped_candidates,
                "rejected_candidates": rejected_candidates,
                "qualification_only": True, "product_level_parity": "NOT_IN_SCOPE",
                "production_promotion_ready": False,
            }
        verified = _verify(temp_dir)
        if verified.get("result") != "ACCEPT" or int(verified.get("evaluations", 0)) != 61:
            rejected_candidates.append(compact_rejection(temp_dir, verified))
            return {
                "schema": SCHEMA, "release": RELEASE, "result": "REJECT",
                "errors": ["fresh source capture failed post-capture verification"],
                "skipped_candidates": skipped_candidates,
                "rejected_candidates": rejected_candidates,
                "qualification_only": True, "product_level_parity": "NOT_IN_SCOPE",
                "production_promotion_ready": False,
            }
        if backup_dir.exists(): shutil.rmtree(backup_dir)
        if generated_dir.exists(): generated_dir.rename(backup_dir)
        temp_dir.rename(generated_dir)
        if backup_dir.exists(): shutil.rmtree(backup_dir)
        return accepted_report(generated_dir, "fresh_atomic_recapture", True)
    except Exception as exc:
        return {
            "schema": SCHEMA, "release": RELEASE, "result": "REJECT",
            "errors": [f"{type(exc).__name__}: {exc}"],
            "skipped_candidates": skipped_candidates,
            "rejected_candidates": rejected_candidates,
            "qualification_only": True, "product_level_parity": "NOT_IN_SCOPE",
            "production_promotion_ready": False,
        }
    finally:
        if temp_dir.exists(): shutil.rmtree(temp_dir, ignore_errors=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidate", action="append", type=Path, default=[])
    parser.add_argument("--search-root", action="append", type=Path, default=[])
    parser.add_argument("--generated-dir", type=Path, required=True)
    parser.add_argument("--source-archive", type=Path, required=True)
    parser.add_argument("--atdb-path", type=Path, required=True)
    parser.add_argument("--parameters-json", type=Path, required=True)
    parser.add_argument("--coheat-path", type=Path)
    parser.add_argument("--force-recapture", action="store_true")
    parser.add_argument("--output-json", type=Path, required=True)
    args = parser.parse_args(argv)
    report = resolve(
        candidates=args.candidate,
        search_roots=args.search_root,
        generated_dir=args.generated_dir,
        source_archive=args.source_archive,
        atdb_path=args.atdb_path,
        parameters_json=args.parameters_json,
        coheat_path=args.coheat_path,
        force_recapture=args.force_recapture,
    )
    _write_json(args.output_json, report)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report.get("result") == "ACCEPT" else 2


if __name__ == "__main__":
    raise SystemExit(main())
