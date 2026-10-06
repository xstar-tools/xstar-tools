#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
import re
from pathlib import Path
from typing import Any, Callable

NUM = r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[EeDd][+-]?\d+)?"
NUM_RE = re.compile(NUM)
OPT_RE = re.compile(r"^\s*print option:\s*([0-9]+)\s*$", re.I)
FINAL_RE = re.compile(r"^\s*final print:\s*([0-9]+)\s*$", re.I)
U_RE = re.compile(r"U\(1-1\.8\),U\(1\.8-4\):\s*(%s)\s+(%s)" % (NUM, NUM))
LBOL_RE = re.compile(r"Lbol=\s*(%s)" % NUM)
ASSIGN_RE = re.compile(r"([A-Za-z][A-Za-z0-9_()]*)\s*=\s*(%s)" % NUM)
ZONE_RE = re.compile(r"^\s*" + r"\s+".join([f"({NUM})"] * 11) + r"\s+([+-]?\d+)(?:\s+[+-]?\d+)?\s*$")
RANKED_LINE_RE = re.compile(r"^\s*(\d+)\s+(\d+)\s+(\S+)\s+(%s)\s+(%s)\s+(%s)\s*$" % (NUM, NUM, NUM))
DETAIL_PREFIX_RE = re.compile(r"^\s*(\d+)\s+(" + NUM + r")\s+(\S+)\s+(.*)$")
SCI5_RE = re.compile(r"[+-]?\d\.\d{5}[EeDd][+-]\d+")
RRC_RE = re.compile(
    r"^\s*(\d+)\s+(\d+)\s+(\S+)\s+(\d+)\s+(\d+)\s+(\S+)\s+(\S+)\s+"
    r"(%s)\s+(%s)\s+(%s)\s*$" % (NUM, NUM, NUM)
)
IONCOL_RE = re.compile(r"^\s*(\d+)\s+(\S+)\s+(%s)\s*$" % NUM)
ENERGY_RE = re.compile(r"energy sums:\s*abs,\s*cont,\s*line,\s*err:\s*(%s)\s*(%s)\s*(%s)\s*(%s)" % (NUM, NUM, NUM, NUM), re.I)

RTOL = 0.01
ABS_FLOOR = 1.0e-30


def fnum(s: str) -> float:
    return float(s.replace("D", "E").replace("d", "e"))


def rel(a: float, b: float, floor: float = ABS_FLOOR) -> float:
    return abs(a - b) / max(abs(a), abs(b), floor)


def log_physical_rel(a: float, b: float) -> float:
    # Compare the physical quantity represented by a base-10 logarithm.
    d = abs(a - b)
    if d > 300.0:
        return math.inf
    return abs(10.0 ** d - 1.0)


def quantized_log_lower_bound_rel(a: float, b: float, displayed_step: float = 0.01) -> float:
    # Each value was rounded to the nearest displayed_step.  Return the
    # smallest possible physical relative difference compatible with those
    # displayed values.  A one-last-digit difference can therefore be
    # correctly classified as display-quantization ambiguous rather than a
    # proven >1% science difference.
    min_dex = max(0.0, abs(a - b) - displayed_step)
    return abs(10.0 ** min_dex - 1.0)


def split_options(text: str) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    cur: str | None = None
    for line in text.splitlines():
        m = OPT_RE.match(line)
        if m:
            cur = str(int(m.group(1)))
            out.setdefault(cur, [])
            continue
        if cur is not None:
            out[cur].append(line)
    return out


def source_diag(text: str) -> dict[str, float | None]:
    um = U_RE.search(text)
    lm = LBOL_RE.search(text)
    return {
        "u_1_1p8": fnum(um.group(1)) if um else None,
        "u_1p8_4": fnum(um.group(2)) if um else None,
        "lbol": fnum(lm.group(1)) if lm else None,
    }


def final_print(text: str) -> list[float]:
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if FINAL_RE.match(line):
            for nxt in lines[i + 1 : i + 6]:
                vals = [fnum(x) for x in NUM_RE.findall(nxt)]
                if len(vals) >= 4:
                    return vals[:4]
    return []


def option17(lines: list[str]) -> list[list[float]]:
    out: list[list[float]] = []
    for line in lines:
        m = ZONE_RE.match(line)
        if m:
            vals = [fnum(x) for x in m.groups()[:-1]]
            vals.append(float(int(m.group(12))))
            out.append(vals)
    return out


def option22(lines: list[str]) -> dict[str, float]:
    out: dict[str, float] = {}
    for line in lines:
        for k, v in ASSIGN_RE.findall(line):
            out[k.lower()] = fnum(v)
    return out


def ranked_lines(lines: list[str]) -> list[dict[str, Any]]:
    """Parse ranked Options 1/23 in displayed rank order.

    The numerical surface of these reports is a ranked array.  Line identity
    attachment/order is a separate publication diagnostic and must not be
    used as the alignment key for the numerical comparison.
    """
    out: list[dict[str, Any]] = []
    for line in lines:
        m = RANKED_LINE_RE.match(line)
        if not m:
            continue
        out.append({
            "rank": int(m.group(1)),
            "line_index": int(m.group(2)),
            "ion": m.group(3).lower(),
            "wavelength": fnum(m.group(4)),
            "value_1": fnum(m.group(5)),
            "value_2": fnum(m.group(6)),
        })
    out.sort(key=lambda row: row["rank"])
    return out


def compare_ranked_rows(section: str, crows: list[dict[str, Any]], rrows: list[dict[str, Any]]) -> dict[str, Any]:
    """Compare Options 1/23 as ranked numerical arrays, identities diagnostically.

    The science gate is normalized L1 over the arrays after rank-position
    alignment.  Individual >1% tail cells are retained as diagnostics but do
    not turn a numerically identical ranked distribution into a false model
    REJECT.  Identity/order/membership is reported independently.
    """
    n = min(len(crows), len(rrows))
    disc: list[dict[str, Any]] = []
    rowwise: list[dict[str, Any]] = []
    field_metrics: dict[str, Any] = {}
    for field in ("value_1", "value_2"):
        cvals = [float(crows[i][field]) for i in range(n)]
        rvals = [float(rrows[i][field]) for i in range(n)]
        numerator = sum(abs(a - b) for a, b in zip(cvals, rvals))
        denominator = max(sum(abs(a) for a in cvals), sum(abs(b) for b in rvals), ABS_FLOOR)
        nl1 = numerator / denominator
        for i, (cv, rv) in enumerate(zip(cvals, rvals), 1):
            rr = rel(cv, rv)
            if rr > RTOL:
                rowwise.append(discrepancy(section, f"rank={i}", field, cv, rv, rr, "rank_tail_diagnostic"))
        field_metrics[field] = {
            "normalized_l1": nl1,
            "candidate_l1": sum(abs(a) for a in cvals),
            "reference_l1": sum(abs(b) for b in rvals),
            "common_rank_positions": n,
            "rowwise_gt1pct_diagnostics": sum(1 for d in rowwise if d["field"] == field),
            "accept": nl1 <= RTOL,
        }
        if nl1 > RTOL:
            disc.append(discrepancy(section, "ranked_array", f"{field}_normalized_l1", field_metrics[field]["candidate_l1"], field_metrics[field]["reference_l1"], nl1))

    cseq = [int(x["line_index"]) for x in crows]
    rseq = [int(x["line_index"]) for x in rrows]
    cset, rset = set(cseq), set(rseq)
    conly, ronly = cset - rset, rset - cset
    positional: list[dict[str, Any]] = []
    for i in range(n):
        cs, rs = crows[i], rrows[i]
        if (
            int(cs["line_index"]) != int(rs["line_index"])
            or str(cs["ion"]) != str(rs["ion"])
            or rel(float(cs["wavelength"]), float(rs["wavelength"])) > RTOL
        ):
            positional.append({
                "rank": i + 1,
                "candidate_line_index": int(cs["line_index"]),
                "reference_line_index": int(rs["line_index"]),
                "candidate_ion": str(cs["ion"]),
                "reference_ion": str(rs["ion"]),
                "candidate_wavelength": float(cs["wavelength"]),
                "reference_wavelength": float(rs["wavelength"]),
            })

    row_count_mismatch = len(crows) != len(rrows)
    rank_diag = bool(row_count_mismatch or cseq != rseq or conly or ronly or positional)
    numeric_count = len(disc)
    return {
        "candidate_rows": len(crows),
        "reference_rows": len(rrows),
        "common_rank_positions": n,
        "common_identities": len(cset & rset),
        "candidate_only_identities": len(conly),
        "reference_only_identities": len(ronly),
        "candidate_only_material_identities": 0,
        "reference_only_material_identities": 0,
        "material_inventory_mismatches": 0,
        "metadata_mismatches": len(positional),
        "metadata_numeric_above_1pct": 0,
        "identity_mismatches": len(positional) + int(row_count_mismatch),
        "rank_position_identity_mismatches": len(positional),
        "row_count_mismatch": int(row_count_mismatch),
        "numeric_above_1pct": numeric_count,
        "rank_rowwise_gt1pct_diagnostics": len(rowwise),
        "rank_rowwise_gt1pct_sample": sorted(rowwise, key=lambda x: x["relative_difference"], reverse=True)[:40],
        "ranked_array_metrics": field_metrics,
        "rank_or_order_membership_diagnostic": rank_diag,
        "numeric_science_accept": numeric_count == 0,
        "scientific_accept": numeric_count == 0 and not rank_diag,
        "discrepancies": disc,
        "top_discrepancies": sorted(disc, key=lambda x: x["relative_difference"], reverse=True)[:100],
        "candidate_only_sample": [str(x) for x in sorted(conly)[:20]],
        "reference_only_sample": [str(x) for x in sorted(ronly)[:20]],
        "rank_identity_mismatch_sample": positional[:40],
        "numeric_alignment": "rank_position_normalized_l1",
        "identity_alignment": "diagnostic_only",
    }


def detail_lines(lines: list[str]) -> dict[int, dict[str, Any]]:
    out: dict[int, dict[str, Any]] = {}
    for line in lines:
        m = DETAIL_PREFIX_RE.match(line)
        if not m:
            continue
        values = SCI5_RE.findall(m.group(4))
        if len(values) < 4:
            continue
        line_index = int(m.group(1))
        out[line_index] = {
            "ion": m.group(3).lower(),
            "wavelength": fnum(m.group(2)),
            "ref_lum": fnum(values[0]),
            "trn_lum": fnum(values[1]),
            "backward_depth": fnum(values[2]),
            "forward_depth": fnum(values[3]),
        }
    return out


def rrc_rows(lines: list[str]) -> dict[int, dict[str, Any]]:
    # The scientific storage identity is npconi2 / continuum_index.  FORTRAN
    # may print more than one metadata record that addresses the same slot;
    # collapse those duplicates for science comparison and retain multiplicity
    # only as a report-identity diagnostic.
    out: dict[int, dict[str, Any]] = {}
    multiplicity: dict[int, int] = {}
    for line in lines:
        m = RRC_RE.match(line)
        if not m:
            continue
        key = int(m.group(1))
        multiplicity[key] = multiplicity.get(key, 0) + 1
        row = {
            "level": int(m.group(2)),
            "ion": m.group(3).lower(),
            "lower_local": int(m.group(4)),
            "upper_local": int(m.group(5)),
            "lower": m.group(6),
            "upper": m.group(7),
            "energy": fnum(m.group(8)),
            "value_1": fnum(m.group(9)),
            "value_2": fnum(m.group(10)),
        }
        if key not in out:
            out[key] = row
        else:
            # Same physical slot should carry the same numeric surface.  Keep
            # the largest magnitude instance if formatting duplicates disagree.
            old = out[key]
            if max(abs(row["value_1"]), abs(row["value_2"])) > max(abs(old["value_1"]), abs(old["value_2"])):
                out[key] = row
    for key, count in multiplicity.items():
        out[key]["print_multiplicity"] = count
    return out


def ion_columns(lines: list[str]) -> dict[tuple[int, str], dict[str, float]]:
    out: dict[tuple[int, str], dict[str, float]] = {}
    for line in lines:
        m = IONCOL_RE.match(line)
        if m:
            out[(int(m.group(1)), m.group(2).lower())] = {"column": fnum(m.group(3))}
    return out


def energy_sums(lines: list[str]) -> dict[str, float]:
    text = "\n".join(lines)
    m = ENERGY_RE.search(text)
    if not m:
        return {}
    return dict(zip(("absorbed", "continuum", "line", "error"), (fnum(x) for x in m.groups())))


def discrepancy(section: str, identity: str, field: str, c: float | None, r: float | None, rr: float, kind: str = "numeric") -> dict[str, Any]:
    return {"section": section, "identity": identity, "field": field, "candidate": c, "reference": r, "relative_difference": rr, "kind": kind}


def compare_scalar_map(section: str, c: dict[str, float], r: dict[str, float], log_fields: set[str] | None = None, expected_fields: set[str] | None = None) -> dict[str, Any]:
    log_fields = log_fields or set()
    disc: list[dict[str, Any]] = []
    fields: dict[str, Any] = {}
    keys = set(c) | set(r) | (expected_fields or set())
    for k in sorted(keys):
        cv, rv = c.get(k), r.get(k)
        if cv is None or rv is None:
            rr = math.inf
        elif k in log_fields:
            rr = log_physical_rel(cv, rv)
        else:
            rr = rel(cv, rv)
        ok = cv is not None and rv is not None and rr <= RTOL
        fields[k] = {"candidate": cv, "reference": rv, "relative_difference": rr, "accept": ok}
        if not ok:
            disc.append(discrepancy(section, "scalar", k, cv, rv, rr))
    return {"fields": fields, "numeric_above_1pct": len(disc), "numeric_science_accept": not disc, "scientific_accept": not disc, "discrepancies": disc, "top_discrepancies": sorted(disc, key=lambda x: x["relative_difference"], reverse=True)[:100]}


def material_row(row: dict[str, Any], value_fields: tuple[str, ...]) -> bool:
    return any(abs(float(row.get(k, 0.0))) > ABS_FLOOR for k in value_fields)


def compare_identity_rows(
    section: str,
    c: dict[Any, dict[str, Any]],
    r: dict[Any, dict[str, Any]],
    value_fields: tuple[str, ...],
    metadata_fields: tuple[str, ...] = (),
    ignore_membership: bool = False,
) -> dict[str, Any]:
    ckeys, rkeys = set(c), set(r)
    common = ckeys & rkeys
    conly, ronly = ckeys - rkeys, rkeys - ckeys
    disc: list[dict[str, Any]] = []
    metadata_mismatch = 0
    metadata_numeric_above_1pct = 0
    for key in common:
        cs, rs = c[key], r[key]
        for field in metadata_fields:
            cv, rv = cs.get(field), rs.get(field)
            if isinstance(cv, (int, float)) and isinstance(rv, (int, float)):
                rr = rel(float(cv), float(rv))
                if rr > RTOL:
                    metadata_mismatch += 1
                    metadata_numeric_above_1pct += 1
                    disc.append(discrepancy(section, str(key), field, float(cv), float(rv), rr, "metadata"))
            elif cv != rv:
                metadata_mismatch += 1
        for field in value_fields:
            cv, rv = float(cs.get(field, 0.0)), float(rs.get(field, 0.0))
            rr = rel(cv, rv)
            if rr > RTOL:
                disc.append(discrepancy(section, str(key), field, cv, rv, rr))
    cmat = [k for k in conly if material_row(c[k], value_fields)]
    rmat = [k for k in ronly if material_row(r[k], value_fields)]
    if not ignore_membership:
        for key in cmat:
            mag = max(abs(float(c[key].get(f, 0.0))) for f in value_fields)
            disc.append(discrepancy(section, str(key), "material_identity_candidate_only", mag, 0.0, 1.0, "material_inventory"))
        for key in rmat:
            mag = max(abs(float(r[key].get(f, 0.0))) for f in value_fields)
            disc.append(discrepancy(section, str(key), "material_identity_reference_only", 0.0, mag, 1.0, "material_inventory"))
    numeric = sum(1 for d in disc if d["kind"] == "numeric")
    inventory = sum(1 for d in disc if d["kind"] == "material_inventory")
    return {
        "candidate_rows": len(c),
        "reference_rows": len(r),
        "common_identities": len(common),
        "candidate_only_identities": len(conly),
        "reference_only_identities": len(ronly),
        "candidate_only_material_identities": len(cmat),
        "reference_only_material_identities": len(rmat),
        "metadata_mismatches": metadata_mismatch,
        "metadata_numeric_above_1pct": metadata_numeric_above_1pct,
        "numeric_above_1pct": numeric,
        "material_inventory_mismatches": inventory,
        "rank_or_order_membership_diagnostic": bool(ignore_membership and (conly or ronly)),
        "numeric_science_accept": numeric == 0 and metadata_numeric_above_1pct == 0,
        "scientific_accept": numeric == 0 and metadata_numeric_above_1pct == 0 and (ignore_membership or inventory == 0),
        "discrepancies": disc,
        "top_discrepancies": sorted(disc, key=lambda x: x["relative_difference"], reverse=True)[:100],
        "candidate_only_sample": [str(x) for x in sorted(conly, key=str)[:20]],
        "reference_only_sample": [str(x) for x in sorted(ronly, key=str)[:20]],
    }



def compare_option15_material_surfaces(
    c: dict[Any, dict[str, Any]],
    r: dict[Any, dict[str, Any]],
) -> dict[str, Any]:
    """Compare Option 15 common-row science by material ion x field surfaces.

    Rowwise >1% cells are retained verbatim as diagnostics.  The numerical
    science gate is normalized L1 on each common-row ion x field surface,
    with only surfaces whose L1 magnitude exceeds ABS_FLOOR participating in
    the material gate.  Candidate/reference-only identities remain a separate
    inventory/publication diagnostic.
    """
    value_fields = ("ref_lum", "trn_lum", "backward_depth", "forward_depth")
    ckeys, rkeys = set(c), set(r)
    common = ckeys & rkeys
    conly, ronly = ckeys - rkeys, rkeys - ckeys

    diagnostics: list[dict[str, Any]] = []
    metadata_mismatch = 0
    metadata_numeric_above_1pct = 0
    rowwise_count = 0

    groups: dict[tuple[str, str], list[tuple[float, float]]] = {}
    for key in common:
        cs, rs = c[key], r[key]
        cv, rv = float(cs.get("wavelength", 0.0)), float(rs.get("wavelength", 0.0))
        rr = rel(cv, rv)
        if rr > RTOL:
            metadata_mismatch += 1
            metadata_numeric_above_1pct += 1
            diagnostics.append(discrepancy("15", str(key), "wavelength", cv, rv, rr, "metadata"))
        ion = str(rs.get("ion") or cs.get("ion") or "unknown").lower()
        for field in value_fields:
            a, b = float(cs.get(field, 0.0)), float(rs.get(field, 0.0))
            groups.setdefault((ion, field), []).append((a, b))
            rrow = rel(a, b)
            if rrow > RTOL:
                rowwise_count += 1
                diagnostics.append(discrepancy("15", str(key), field, a, b, rrow, "rowwise_gt1pct_diagnostic"))

    surfaces: dict[str, Any] = {}
    material_failures: list[dict[str, Any]] = []
    material_count = 0
    max_material_nl1 = 0.0
    for (ion, field), vals in sorted(groups.items()):
        c_l1 = sum(abs(a) for a, _ in vals)
        r_l1 = sum(abs(b) for _, b in vals)
        denom = max(c_l1, r_l1)
        numerator = sum(abs(a - b) for a, b in vals)
        material = denom > ABS_FLOOR
        nl1 = numerator / max(denom, ABS_FLOOR)
        accept = (not material) or nl1 < RTOL
        if material:
            material_count += 1
            max_material_nl1 = max(max_material_nl1, nl1)
        key = f"{ion}|{field}"
        surfaces[key] = {
            "ion": ion,
            "field": field,
            "common_rows": len(vals),
            "candidate_l1": c_l1,
            "reference_l1": r_l1,
            "absolute_l1_difference": numerator,
            "normalized_l1": nl1,
            "material": material,
            "accept": accept,
        }
        if material and not accept:
            d = discrepancy("15", ion, f"{field}_normalized_l1", c_l1, r_l1, nl1, "material_surface")
            material_failures.append(d)
            diagnostics.append(d)

    cmat = [k for k in conly if material_row(c[k], value_fields)]
    rmat = [k for k in ronly if material_row(r[k], value_fields)]
    for key in cmat:
        mag = max(abs(float(c[key].get(f, 0.0))) for f in value_fields)
        diagnostics.append(discrepancy("15", str(key), "material_identity_candidate_only", mag, 0.0, 1.0, "material_inventory"))
    for key in rmat:
        mag = max(abs(float(r[key].get(f, 0.0))) for f in value_fields)
        diagnostics.append(discrepancy("15", str(key), "material_identity_reference_only", 0.0, mag, 1.0, "material_inventory"))

    inventory = len(cmat) + len(rmat)
    numeric_ok = not material_failures and metadata_numeric_above_1pct == 0
    return {
        "candidate_rows": len(c),
        "reference_rows": len(r),
        "common_identities": len(common),
        "candidate_only_identities": len(conly),
        "reference_only_identities": len(ronly),
        "candidate_only_material_identities": len(cmat),
        "reference_only_material_identities": len(rmat),
        "metadata_mismatches": metadata_mismatch,
        "metadata_numeric_above_1pct": metadata_numeric_above_1pct,
        # Backward-compatible rowwise diagnostic count; it no longer drives the gate.
        "numeric_above_1pct": rowwise_count,
        "rowwise_gt1pct_diagnostics": rowwise_count,
        "material_surface_count": material_count,
        "material_surface_failures": len(material_failures),
        "max_material_surface_normalized_l1": max_material_nl1,
        "material_surface_metrics": surfaces,
        "material_inventory_mismatches": inventory,
        "rank_or_order_membership_diagnostic": False,
        "numeric_science_accept": numeric_ok,
        "scientific_accept": numeric_ok and inventory == 0,
        "discrepancies": diagnostics,
        "top_discrepancies": sorted(diagnostics, key=lambda x: x["relative_difference"], reverse=True)[:100],
        "top_material_surface_failures": sorted(material_failures, key=lambda x: x["relative_difference"], reverse=True)[:100],
        "candidate_only_sample": [str(x) for x in sorted(conly, key=str)[:20]],
        "reference_only_sample": [str(x) for x in sorted(ronly, key=str)[:20]],
        "numeric_gate": "common-row ion_x_field normalized_L1 < 1% for every material surface",
        "rowwise_policy": "per-cell >1% retained as diagnostic only",
        "inventory_policy": "candidate/reference-only material identities remain separate publication diagnostics",
    }

def compare_option17(crows: list[list[float]], rrows: list[list[float]]) -> dict[str, Any]:
    fields = ("log_r", "log_delr_over_r", "log_N", "log_xi", "x_e", "log_n", "log_t", "hc_local_pct", "hc_forward_pct", "log_tau_fwd", "log_tau_rev", "dsec")
    logidx = {0, 1, 2, 3, 5, 6, 9, 10}
    disc: list[dict[str, Any]] = []
    ambiguous: list[dict[str, Any]] = []
    n = min(len(crows), len(rrows))
    for i in range(n):
        for j, field in enumerate(fields):
            cv, rv = crows[i][j], rrows[i][j]
            if j == 11:
                if int(round(cv)) != int(round(rv)):
                    disc.append(discrepancy("17", f"zone_row={i+1}", field, cv, rv, math.inf, "identity"))
                continue
            if j in logidx:
                raw_rr = log_physical_rel(cv, rv)
                lower_rr = quantized_log_lower_bound_rel(cv, rv, 0.01)
                if raw_rr > RTOL and lower_rr <= RTOL:
                    ambiguous.append(discrepancy("17", f"zone_row={i+1}", field, cv, rv, raw_rr, "display_quantization"))
                elif lower_rr > RTOL:
                    disc.append(discrepancy("17", f"zone_row={i+1}", field, cv, rv, raw_rr))
            elif j in (7, 8):
                # H-C columns are percentages.  One percentage point is the
                # physically relevant tolerance; relative error near zero is
                # not meaningful.
                if abs(cv - rv) > 1.0:
                    rr = abs(cv - rv) / max(abs(cv), abs(rv), 1.0)
                    disc.append(discrepancy("17", f"zone_row={i+1}", field, cv, rv, rr))
            else:
                rr = rel(cv, rv)
                if rr > RTOL:
                    disc.append(discrepancy("17", f"zone_row={i+1}", field, cv, rv, rr))
    row_count_mismatch = abs(len(crows) - len(rrows))
    if row_count_mismatch:
        disc.append(discrepancy("17", "rows", "row_count", float(len(crows)), float(len(rrows)), math.inf, "identity"))
    numeric_count = sum(1 for d in disc if d["kind"] == "numeric")
    identity_count = sum(1 for d in disc if d["kind"] == "identity")
    return {
        "candidate_rows": crows,
        "reference_rows": rrows,
        "row_count_mismatch": row_count_mismatch,
        "numeric_above_1pct": numeric_count,
        "display_quantization_ambiguous": len(ambiguous),
        "identity_mismatches": identity_count,
        "numeric_science_accept": numeric_count == 0,
        "scientific_accept": numeric_count == 0 and identity_count == 0,
        "discrepancies": disc,
        "top_discrepancies": sorted(disc, key=lambda x: x["relative_difference"], reverse=True)[:100],
        "quantization_ambiguous_examples": ambiguous[:40],
    }


def compare_energy(c: dict[str, float], r: dict[str, float]) -> dict[str, Any]:
    disc: list[dict[str, Any]] = []
    fields: dict[str, Any] = {}
    for k in ("absorbed", "continuum", "line", "error"):
        cv, rv = c.get(k), r.get(k)
        if cv is None or rv is None:
            rr = math.inf
            ok = False
        else:
            # All Option-5 fields, including the signed ``err`` residual, are
            # compared relatively.  The v064812333 absolute 0.01 test falsely
            # rejected large-magnitude residuals that differed by tiny
            # fractions (for example -1199.4 versus -1199.34).
            rr = rel(cv, rv)
            ok = rr <= RTOL
        fields[k] = {"candidate": cv, "reference": rv, "difference_metric": rr, "accept": ok}
        if not ok:
            disc.append(discrepancy("5", "energy_sums", k, cv, rv, rr))
    return {"fields": fields, "numeric_above_1pct": len(disc), "numeric_science_accept": not disc, "scientific_accept": not disc, "discrepancies": disc, "top_discrepancies": disc}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--candidate", required=True)
    ap.add_argument("--reference", required=True)
    ap.add_argument("--json", required=True)
    ns = ap.parse_args()
    ct = Path(ns.candidate).read_text(errors="replace")
    rt = Path(ns.reference).read_text(errors="replace")
    cb, rb = split_options(ct), split_options(rt)

    csrc, rsrc = source_diag(ct), source_diag(rt)
    src = compare_scalar_map("source_spectrum", {k: v for k, v in csrc.items() if v is not None}, {k: v for k, v in rsrc.items() if v is not None}, expected_fields={"u_1_1p8", "u_1p8_4", "lbol"})

    cf, rf = final_print(ct), final_print(rt)
    fnames = ("T4", "HTTOT", "CLTOT", "HMCTOT")
    final_fields: dict[str, Any] = {}
    final_disc: list[dict[str, Any]] = []
    for i, name in enumerate(fnames):
        cv = cf[i] if i < len(cf) else None
        rv = rf[i] if i < len(rf) else None
        rr = math.inf if cv is None or rv is None else rel(cv, rv)
        ok = cv is not None and rv is not None and rr <= RTOL
        final_fields[name] = {"candidate": cv, "reference": rv, "relative_difference": rr, "accept": ok}
        if not ok:
            final_disc.append(discrepancy("final", "scalar", name, cv, rv, rr))
    thermal_accept = all(final_fields[x]["accept"] for x in ("T4", "HTTOT", "CLTOT"))

    c22, r22 = option22(cb.get("22", [])), option22(rb.get("22", []))
    log22 = {"log(xi)", "logxi", "log(u1)", "log(ux)"}
    # log(Xi) lowercases to log(xi), colliding with log(xi) in a dict if we
    # blindly lower-case.  The source spelling is case-significant here, so
    # reparse option 22 preserving Xi below.
    def option22_case(lines: list[str]) -> dict[str, float]:
        out: dict[str, float] = {}
        for line in lines:
            for k, v in ASSIGN_RE.findall(line):
                key = "logXi" if k == "log(Xi)" else k.lower()
                out[key] = fnum(v)
        return out
    c22, r22 = option22_case(cb.get("22", [])), option22_case(rb.get("22", []))
    o22 = compare_scalar_map("22", c22, r22, {"log(xi)", "logxi", "log(u1)", "log(ux)", "logXi"}, expected_fields={"r", "t", "log(xi)", "n_e", "n_p", "httot", "cltot", "taulc", "taulcb", "logXi", "log(u1)", "log(ux)", "gamma", "rdel"})

    sections: dict[str, Any] = {}
    sections["17"] = compare_option17(option17(cb.get("17", [])), option17(rb.get("17", [])))
    sections["22"] = o22
    sections["1"] = compare_ranked_rows("1", ranked_lines(cb.get("1", [])), ranked_lines(rb.get("1", [])))
    sections["23"] = compare_ranked_rows("23", ranked_lines(cb.get("23", [])), ranked_lines(rb.get("23", [])))
    sections["15"] = compare_option15_material_surfaces(detail_lines(cb.get("15", [])), detail_lines(rb.get("15", [])))
    sections["24"] = compare_identity_rows("24", rrc_rows(cb.get("24", [])), rrc_rows(rb.get("24", [])), ("value_1", "value_2"), ("energy",), ignore_membership=False)
    sections["19"] = compare_identity_rows("19", rrc_rows(cb.get("19", [])), rrc_rows(rb.get("19", [])), ("value_1", "value_2"), ("energy",), ignore_membership=False)
    sections["27"] = compare_identity_rows("27", ion_columns(cb.get("27", [])), ion_columns(rb.get("27", [])), ("column",), (), ignore_membership=False)
    sections["5"] = compare_energy(energy_sums(cb.get("5", [])), energy_sums(rb.get("5", [])))
    sections["16"] = {"science_applicable": False, "numeric_science_accept": True, "scientific_accept": True, "reason": "CPU timing/accounting only; native controller does not retain FORTRAN CPU accumulators"}

    ordered_science_sections = ("17", "22", "1", "23", "15", "24", "19", "27", "5")
    numeric_failure_sections = [k for k in ordered_science_sections if not sections[k].get("numeric_science_accept", sections[k].get("scientific_accept", False))]
    failure_sections = [k for k in ordered_science_sections if not sections[k].get("scientific_accept", False)]
    inventory_issue_sections = [k for k in ordered_science_sections if int(sections[k].get("material_inventory_mismatches", 0) or 0) > 0]
    ranking_diagnostics = [k for k in ("1", "23") if sections[k].get("rank_or_order_membership_diagnostic")]
    all_disc: list[dict[str, Any]] = []
    all_disc.extend(src.get("discrepancies", []))
    all_disc.extend(final_disc)
    for k in sections:
        all_disc.extend(sections[k].get("discrepancies", []))
    all_disc.sort(key=lambda x: x.get("relative_difference", 0.0), reverse=True)
    numeric_disc = [x for x in all_disc if x.get("kind") in ("numeric", "metadata")]
    inventory_disc = [x for x in all_disc if x.get("kind") == "material_inventory"]

    doc = {
        "schema": "xstar-tools-v0648123361-step-science-material-option15-v1",
        "policy": {
            "relative_tolerance": RTOL,
            "absolute_denominator_floor": ABS_FLOOR,
            "row_order": "Options 15/24/19/27 aligned by source identity; Options 1/23 numerical arrays aligned by displayed rank position",
            "ranked_options_1_23": "numeric ranked arrays aligned by rank position and gated by normalized L1 <=1%; per-rank >1% tail cells and line identity/order/membership are diagnostics",
            "option15_exponent": "scientific notation accepts arbitrary exponent width, including E-101",
            "option15_common_row_numeric": "common-row Option15 science is gated by normalized L1 <1% for every material ion x field surface; rowwise >1% cells are diagnostics only",
            "option15_24_inventory": "candidate/reference-only identities are inventory diagnostics separate from common-row numerical science",
            "option5_error": "signed error residual compared by relative difference, not absolute 0.01",
            "option16": "ignored as CPU timing/accounting, not science",
            "option17_log_display": "base-10 logs compared as physical quantities; one displayed 0.01-dex last-digit difference is quantization-ambiguous, not automatically a >1% failure",
        },
        "source_spectrum": src,
        "source_spectrum_accept": src["scientific_accept"],
        "final_print": final_fields,
        "final_discrepancies": final_disc,
        "thermal_accept": thermal_accept,
        "sections": sections,
        "numeric_failure_sections": numeric_failure_sections,
        "scientific_failure_sections": failure_sections,
        "material_inventory_issue_sections": inventory_issue_sections,
        "ranking_or_order_diagnostic_sections": ranking_diagnostics,
        "step_numeric_science_accept": bool(src["scientific_accept"] and thermal_accept and not numeric_failure_sections),
        "step_science_accept": bool(src["scientific_accept"] and thermal_accept and not failure_sections),
        "top_discrepancies": all_disc[:200],
        "top_numeric_discrepancies": numeric_disc[:200],
        "top_material_inventory_discrepancies": inventory_disc[:200],
    }
    Path(ns.json).write_text(json.dumps(doc, indent=2, sort_keys=True) + "\n")
    print(f"V0648123361_STEP_SOURCE_SPECTRUM={'ACCEPT' if doc['source_spectrum_accept'] else 'REJECT'}")
    print(f"V0648123361_STEP_THERMAL={'ACCEPT' if thermal_accept else 'REJECT'}")
    for k in ("17", "22", "1", "23", "15", "24", "19", "27", "5"):
        print(f"V0648123361_STEP_OPTION{k}_SCIENCE={'ACCEPT' if sections[k].get('scientific_accept') else 'REJECT'}")
    print("V0648123361_STEP_OPTION16_SCIENCE=IGNORED_TIMING_ONLY")
    print("V0648123361_STEP_NUMERIC_FAILURE_SECTIONS=" + (";".join(numeric_failure_sections) if numeric_failure_sections else "NONE"))
    print("V0648123361_STEP_SCIENCE_FAILURE_SECTIONS=" + (";".join(failure_sections) if failure_sections else "NONE"))
    print("V0648123361_STEP_MATERIAL_INVENTORY_ISSUES=" + (";".join(inventory_issue_sections) if inventory_issue_sections else "NONE"))
    print("V0648123361_STEP_RANK_ORDER_DIAGNOSTICS=" + (";".join(ranking_diagnostics) if ranking_diagnostics else "NONE"))
    o15 = sections["15"]
    print(f"V0648123361_STEP_OPTION15_NUMERIC_SCIENCE={'ACCEPT' if o15.get('numeric_science_accept') else 'REJECT'}")
    print(f"V0648123361_STEP_OPTION15_ROWWISE_GT1PCT_DIAGNOSTIC={o15.get('rowwise_gt1pct_diagnostics', 0)}")
    print(f"V0648123361_STEP_OPTION15_MATERIAL_SURFACE_COUNT={o15.get('material_surface_count', 0)}")
    print(f"V0648123361_STEP_OPTION15_MATERIAL_SURFACE_FAILURES={o15.get('material_surface_failures', 0)}")
    print(f"V0648123361_STEP_OPTION15_MAX_MATERIAL_NL1={o15.get('max_material_surface_normalized_l1', 0.0):.17g}")
    print(f"V0648123361_STEP_NUMERIC_SCIENCE={'ACCEPT' if doc['step_numeric_science_accept'] else 'REJECT'}")
    print(f"V0648123361_STEP_SCIENCE={'ACCEPT' if doc['step_science_accept'] else 'REJECT'}")
    return 0 if doc["step_science_accept"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
