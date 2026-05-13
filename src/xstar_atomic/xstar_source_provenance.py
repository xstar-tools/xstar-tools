"""Source-code provenance audits for XSTAR live radiation fields.

These helpers are intentionally lightweight text/source audits.  They do not
modify solver physics; they record which XSTAR Fortran arrays are live call-site
inputs and which arrays are written to the detail FITS products.
"""

from __future__ import annotations

import csv
import io
import json
import tarfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence


@dataclass(frozen=True)
class SourceSnippetSpec:
    """A source-code pattern to locate in an XSTAR Fortran file."""

    key: str
    file: str
    pattern: str
    role: str
    interpretation: str
    context: int = 4


def _read_csv(path: str | Path) -> List[Dict[str, str]]:
    p = Path(path)
    if not p.exists():
        return []
    with p.open("r", encoding="utf-8", newline="") as fh:
        return [dict(row) for row in csv.DictReader(fh)]


def _write_csv(path: str | Path, rows: Sequence[Mapping[str, Any]]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    fieldnames: List[str] = []
    for row in rows:
        for key in row.keys():
            if key not in fieldnames:
                fieldnames.append(key)
    with p.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in fieldnames})


def _find_file(source_root: str | Path, rel_or_name: str) -> Optional[Path]:
    root = Path(source_root)
    direct = root / rel_or_name
    if direct.exists():
        return direct
    # Common XSTAR source-tree layout: root may be xstar/ or its parent.
    for prefix in ("xstarlib/src", "src", "xstar/xstarlib/src", "xstar/src"):
        candidate = root / prefix / Path(rel_or_name).name
        if candidate.exists():
            return candidate
    matches = list(root.rglob(Path(rel_or_name).name)) if root.exists() else []
    return matches[0] if matches else None


def _extract_snippet(path: Path, pattern: str, context: int) -> Dict[str, Any]:
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    match_index: Optional[int] = None
    pattern_lower = pattern.lower()
    for i, line in enumerate(lines):
        if pattern_lower in line.lower().replace(" ", "") or pattern_lower in line.lower():
            match_index = i
            break
    # If pattern had spaces stripped, also try stripping spaces from both sides.
    if match_index is None:
        compact = pattern_lower.replace(" ", "")
        for i, line in enumerate(lines):
            if compact and compact in line.lower().replace(" ", ""):
                match_index = i
                break
    if match_index is None:
        return {
            "matched": False,
            "line_start": "",
            "line_end": "",
            "matched_line": "",
            "snippet": "",
        }
    start = max(0, match_index - context)
    end = min(len(lines), match_index + context + 1)
    numbered = [f"{j + 1}: {lines[j]}" for j in range(start, end)]
    return {
        "matched": True,
        "line_start": start + 1,
        "line_end": end,
        "matched_line": f"{match_index + 1}: {lines[match_index]}",
        "snippet": "\n".join(numbered),
    }


DEFAULT_LIVE_BREMSA_SNIPPETS: List[SourceSnippetSpec] = [
    SourceSnippetSpec(
        key="trnfrc_live_flux_outward",
        file="trnfrc.f90",
        pattern="bremsa(jk)=zremsz(jk)*exp(-dpthc(1,jk))/fpr2",
        role="live_bremsa_outward_transfer",
        interpretation=(
            "For outward transfer, the local ionizing flux passed to rate kernels is built from the incident/live zremsz array, "
            "attenuated by the forward continuum depth and divided by 12.56*r19^2."
        ),
        context=6,
    ),
    SourceSnippetSpec(
        key="trnfrc_live_flux_inward",
        file="trnfrc.f90",
        pattern="bremsa(jk)=zrems(1,jk)/fpr2",
        role="live_bremsa_inward_transfer",
        interpretation=(
            "For the opposite transfer direction, trnfrc uses zrems(1) rather than zremsz. Direction and call-site timing therefore matter."
        ),
        context=6,
    ),
    SourceSnippetSpec(
        key="trnfrc_bremsint_integral",
        file="trnfrc.f90",
        pattern="bremsint(jk)=bremsint(jk+1)+sumtmp*(1.602197e-12)",
        role="live_bremsint_integral",
        interpretation="bremsint is integrated from the same live bremsa array immediately after bremsa is constructed.",
        context=5,
    ),
    SourceSnippetSpec(
        key="phint53_uses_bremsa_over_12p56",
        file="phint53.f90",
        pattern="bremtmp=bremsa(kl)/(12.56)",
        role="phint53_photoionization_integrand",
        interpretation=(
            "phint53 consumes the live bremsa array and divides by 12.56 inside the photoionization integral. "
            "This confirms that the v0.3.162/v0.3.163 comparison must use the exact live bremsa units, not an arbitrary detail-output column."
        ),
        context=6,
    ),
    SourceSnippetSpec(
        key="savd_detail4_handoff",
        file="savd.f90",
        pattern="call fstepr4",
        role="detail_output_handoff",
        interpretation="savd writes detail continuum products by passing zrems and dpthc to fstepr4, not bremsa or zremsz.",
        context=8,
    ),
    SourceSnippetSpec(
        key="fstepr4_columns",
        file="fstepr4.f90",
        pattern="'zrems(1)','zrems(2)','zrems(3)'",
        role="detail4_column_schema",
        interpretation="xo01_detal4 columns include zrems(1:5), opacity, emissivities, and forward/backward depths.",
        context=4,
    ),
    SourceSnippetSpec(
        key="fstepr4_writes_zrems",
        file="fstepr4.f90",
        pattern="rwrk1(mm)=sngl(zrems(izcol,mm))",
        role="detail4_zrems_write",
        interpretation="fstepr4 writes zrems(1:5) values directly; it does not write the trnfrc live bremsa array.",
        context=6,
    ),
    SourceSnippetSpec(
        key="fstepr4_writes_forward_depth",
        file="fstepr4.f90",
        pattern="rwrk1(mm)=sngl(dpthc(1,mm))",
        role="detail4_forward_depth_write",
        interpretation="fstepr4 writes forward continuum depth separately; the live attenuation expression is not itself stored as bremsa.",
        context=4,
    ),
]


def _read_variant_summary_rows(path: str | Path) -> tuple[str, List[Dict[str, str]], str]:
    """Read an example-69 variant summary from a CSV, directory, or tarball.

    Returns
    -------
    status, rows, resolved_source
        ``status`` is one of ``loaded``, ``missing``, ``directory_no_summary_csv``,
        ``tar_no_summary_csv``, or an error status.  ``resolved_source`` records
        the actual CSV source when one was found.
    """

    p = Path(path)
    if not p.exists():
        return "missing", [], str(p)
    if p.is_dir():
        matches = sorted(p.rglob("xstar_type53_detail_phint53_bremsa_variants_audit_variant_summary.csv"))
        if not matches:
            matches = sorted(p.rglob("*bremsa_variants*_variant_summary.csv"))
        if not matches:
            return "directory_no_summary_csv", [], str(p)
        csv_path = matches[0]
        return "loaded", _read_csv(csv_path), str(csv_path)
    if p.suffix.lower() == ".csv":
        return "loaded", _read_csv(p), str(p)
    name = p.name.lower()
    if name.endswith(".tar.gz") or name.endswith(".tgz") or name.endswith(".tar"):
        try:
            with tarfile.open(p, "r:*") as tf:
                members = [
                    m for m in tf.getmembers()
                    if m.isfile() and (
                        m.name.endswith("xstar_type53_detail_phint53_bremsa_variants_audit_variant_summary.csv")
                        or "bremsa_variants" in Path(m.name).name and Path(m.name).name.endswith("variant_summary.csv")
                    )
                ]
                if not members:
                    return "tar_no_summary_csv", [], str(p)
                member = sorted(members, key=lambda m: m.name)[0]
                fh = tf.extractfile(member)
                if fh is None:
                    return "tar_summary_csv_unreadable", [], f"{p}:{member.name}"
                text = fh.read().decode("utf-8", errors="replace")
                rows = [dict(row) for row in csv.DictReader(io.StringIO(text))]
                return "loaded", rows, f"{p}:{member.name}"
        except (tarfile.TarError, OSError, UnicodeDecodeError) as exc:
            return f"tar_read_error:{exc.__class__.__name__}", [], str(p)
    return "unsupported_path_type", [], str(p)


def summarize_bremsa_variant_gap(variant_summary_csv: str | Path | None = None) -> Dict[str, Any]:
    """Summarize an example-69 variant-summary CSV, directory, or tarball.

    v0.3.168 makes missing or mis-pointed variant-summary paths explicit.  This
    matters because the source-path audit can still confirm the Fortran live
    ``bremsa(:)`` path even when the optional example-69 CSV is not found.
    """

    if not variant_summary_csv:
        return {
            "variant_summary_status": "not_supplied",
            "variant_summary_source": "",
            "variant_summary_path_exists": False,
            "best_variant": None,
            "best_median_matrix_over_detail": None,
            "best_within10_without_scale": None,
            "best_within10_after_scale": None,
            "n_variants": 0,
            "n_numeric_variants": 0,
            "interpretation": "No example-69 variant summary was supplied; only source-code provenance was audited.",
        }

    status, rows, source = _read_variant_summary_rows(variant_summary_csv)
    if status != "loaded":
        return {
            "variant_summary_status": status,
            "variant_summary_source": source,
            "variant_summary_path_exists": Path(variant_summary_csv).exists(),
            "best_variant": None,
            "best_median_matrix_over_detail": None,
            "best_within10_without_scale": None,
            "best_within10_after_scale": None,
            "n_variants": 0,
            "n_numeric_variants": 0,
            "interpretation": (
                "The optional example-69 variant summary was not loaded.  "
                "Pass the actual variant-summary CSV, the audit output directory, or the audit tar.gz "
                "to combine source provenance with the observed matrix/detail normalization gap."
            ),
        }

    parsed = []
    for row in rows:
        try:
            median = float(row.get("median_matrix_over_variant_detail") or row.get("median_matrix_over_detail") or "nan")
        except ValueError:
            continue
        if median != median:
            continue
        try:
            within_no = int(float(row.get("n_within_10pct_without_free_scale") or row.get("within10_no_scale") or 0))
        except ValueError:
            within_no = 0
        try:
            within_scaled = int(float(row.get("n_within_10pct_after_variant_scale") or row.get("within10_scaled") or 0))
        except ValueError:
            within_scaled = 0
        variant_name = row.get("bremsa_variant") or row.get("variant") or row.get("name") or ""
        parsed.append((median, within_no, within_scaled, variant_name, row))
    if not parsed:
        return {
            "variant_summary_status": "loaded_no_numeric_rows",
            "variant_summary_source": source,
            "variant_summary_path_exists": True,
            "best_variant": None,
            "best_median_matrix_over_detail": None,
            "best_within10_without_scale": None,
            "best_within10_after_scale": None,
            "n_variants": len(rows),
            "n_numeric_variants": 0,
            "interpretation": "The variant summary was found, but no numeric median matrix/detail rows were readable.",
        }
    # Prefer small absolute log scale, then more unscaled matches.
    parsed.sort(key=lambda item: (abs(item[0] - 1.0), -item[1]))
    best_median, best_no, best_scaled, best_variant, best_row = parsed[0]
    return {
        "variant_summary_status": "loaded",
        "variant_summary_source": source,
        "variant_summary_path_exists": True,
        "best_variant": best_variant or best_row.get("bremsa_variant") or best_row.get("variant"),
        "best_median_matrix_over_detail": best_median,
        "best_within10_without_scale": best_no,
        "best_within10_after_scale": best_scaled,
        "n_variants": len(rows),
        "n_numeric_variants": len(parsed),
        "interpretation": (
            "No available xo01_detal4 bremsa variant removed the normalization gap without a free scale. "
            "The next parity target is the live zremsz/bremsa call-site state, not another detail-column choice."
            if best_no == 0 and abs(best_median - 1.0) > 0.1
            else "At least one detail variant partly reduces the gap; inspect that variant before replacing the live radiation kernel."
        ),
    }


def audit_xstar_live_bremsa_source_path(
    *,
    xstar_source_root: str | Path,
    variant_summary_csv: str | Path | None = None,
    snippets: Sequence[SourceSnippetSpec] | None = None,
) -> Dict[str, Any]:
    """Audit source-code provenance for live ``bremsa(:)`` versus detail output.

    Parameters
    ----------
    xstar_source_root:
        Root of an extracted XSTAR source tree.  The function accepts either the
        directory containing ``xstarlib/src`` or its parent.
    variant_summary_csv:
        Optional variant summary produced by example 69.  When present, the
        resulting JSON/Markdown includes the observed matrix/detail scale gap.
    snippets:
        Optional custom snippet specs for testing.
    """

    root = Path(xstar_source_root)
    specs = list(snippets or DEFAULT_LIVE_BREMSA_SNIPPETS)
    rows: List[Dict[str, Any]] = []
    missing: List[str] = []
    for spec in specs:
        path = _find_file(root, spec.file)
        if path is None:
            missing.append(spec.file)
            rows.append(
                {
                    "key": spec.key,
                    "role": spec.role,
                    "file": spec.file,
                    "resolved_path": "",
                    "pattern": spec.pattern,
                    "matched": False,
                    "line_start": "",
                    "line_end": "",
                    "matched_line": "",
                    "interpretation": spec.interpretation,
                    "snippet": "",
                }
            )
            continue
        extracted = _extract_snippet(path, spec.pattern, spec.context)
        rows.append(
            {
                "key": spec.key,
                "role": spec.role,
                "file": spec.file,
                "resolved_path": str(path),
                "pattern": spec.pattern,
                **extracted,
                "interpretation": spec.interpretation,
            }
        )
    gap = summarize_bremsa_variant_gap(variant_summary_csv)
    matched = sum(1 for row in rows if row.get("matched") is True)
    status = "source_path_confirmed" if matched == len(rows) else "source_path_partially_confirmed"
    if gap.get("best_within10_without_scale") == 0:
        status = "source_path_confirmed_detail_variants_do_not_recover_live_bremsa" if matched == len(rows) else status
    summary: Dict[str, Any] = {
        "audit_version": "v0.3.168",
        "xstar_source_root": str(root),
        "variant_summary_csv": str(variant_summary_csv) if variant_summary_csv else "",
        "n_source_snippet_specs": len(rows),
        "n_source_snippets_matched": matched,
        "missing_source_files": sorted(set(missing)),
        "status": status,
        **gap,
        "fortran_live_bremsa_outward_formula": "trnfrc.f90: bremsa(jk)=zremsz(jk)*exp(-dpthc(1,jk))/(12.56*r19*r19)",
        "detail4_content": "savd.f90 -> fstepr4.f90 writes zrems(1:5), opacity, rccemis(1:2), dpthc(1:2); it does not write bremsa or zremsz.",
        "recommended_next_step": "Reconstruct or expose live trnfrc zremsz/bremsa at the same calc_hmc_ion call site; do not treat xo01_detal4 zrems variants as exact live bremsa.",
        "performance_note": "This source-provenance audit is lightweight. Heavy production phint53/radiative-transfer kernels should later move to the planned C++ backend after Python physics parity is complete.",
    }
    return {"summary": summary, "source_snippets": rows}


def write_xstar_live_bremsa_source_path_audit(
    audit: Mapping[str, Any],
    out_dir: str | Path,
    *,
    prefix: str = "xstar_live_bremsa_source_path_audit",
) -> Dict[str, str]:
    """Write source-code provenance audit products."""

    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    summary = dict(audit.get("summary", {}) or {})
    snippets = list(audit.get("source_snippets", []) or [])
    snippets_csv = out / f"{prefix}_snippets.csv"
    _write_csv(snippets_csv, snippets)
    json_path = out / f"{prefix}.json"
    json_path.write_text(json.dumps({"summary": summary, "source_snippets": snippets}, indent=2, default=str), encoding="utf-8")
    md_path = out / f"{prefix}.md"
    lines = [
        "# XSTAR live bremsa source-path audit",
        "",
        f"audit_version: `{summary.get('audit_version')}`",
        f"status: `{summary.get('status')}`",
        f"xstar_source_root: `{summary.get('xstar_source_root')}`",
        f"n_source_snippets_matched: `{summary.get('n_source_snippets_matched')}` / `{summary.get('n_source_snippet_specs')}`",
        "",
        "## Type-53 detail-continuum gap context",
        "",
        f"variant_summary_status: `{summary.get('variant_summary_status')}`",
        f"variant_summary_source: `{summary.get('variant_summary_source')}`",
        f"variant_summary_path_exists: `{summary.get('variant_summary_path_exists')}`",
        f"n_numeric_variants: `{summary.get('n_numeric_variants')}`",
        f"best_variant: `{summary.get('best_variant')}`",
        f"best_median_matrix_over_detail: `{summary.get('best_median_matrix_over_detail')}`",
        f"best_within10_without_scale: `{summary.get('best_within10_without_scale')}`",
        f"best_within10_after_scale: `{summary.get('best_within10_after_scale')}`",
        "",
        str(summary.get("interpretation") or ""),
        "",
        "## Source-code conclusion",
        "",
        f"- live bremsa formula: `{summary.get('fortran_live_bremsa_outward_formula')}`",
        f"- detail product content: `{summary.get('detail4_content')}`",
        f"- recommended next step: `{summary.get('recommended_next_step')}`",
        "",
        "## Matched source snippets",
        "",
    ]
    for row in snippets:
        lines.extend(
            [
                f"### {row.get('key')}",
                "",
                f"role: `{row.get('role')}`",
                f"file: `{row.get('file')}`",
                f"matched: `{row.get('matched')}`",
                f"line range: `{row.get('line_start')}-{row.get('line_end')}`",
                "",
                str(row.get("interpretation") or ""),
                "",
                "```fortran",
                str(row.get("snippet") or ""),
                "```",
                "",
            ]
        )
    lines.extend([f"snippets_csv: `{snippets_csv.name}`", f"json: `{json_path.name}`"])
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {"snippets_csv": str(snippets_csv), "json": str(json_path), "markdown": str(md_path)}
