from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

import xstar_atomic.source_port.ion_balance as ib
from xstar_atomic.source_port import (
    CalcIonRatesContext,
    FixedStateElementRequest,
    IoneqmResult,
    calc_hmc_all,
    calc_ion_rates,
    istruc,
    ioneqm,
    select_ion_stage_limits,
)
from xstar_atomic.source_port.ucalc import UCalcStatus


def test_ioneqm_reproduces_adjacent_stage_ratios_and_normalization():
    z = np.array([2.0, 3.0, 5.0])
    a = np.array([4.0, 6.0, 10.0])
    result = ioneqm(z, a)
    assert np.sum(result.fractions) == pytest.approx(1.0)
    # Steady adjacent balance: x_{j+1}/x_j = z_j/a_j.
    assert result.fractions[1:] / result.fractions[:-1] == pytest.approx(z / a)


def test_istruc_returns_one_based_guards_and_literal_last_stage_residual():
    result = istruc([1.0, 1.0], [1.0, 1.0])
    assert result.ionization_rates.tolist() == [0.0, 1.0, 1.0]
    assert result.recombination_rates.tolist() == [0.0, 1.0, 1.0]
    assert result.fractions[0] == 0.0
    assert result.fractions[1:] == pytest.approx([1.0 / 3.0] * 3)
    assert np.sum(result.fractions[1:]) == pytest.approx(1.0)


def test_select_ion_stage_limits_preserves_source_crossing_and_padding():
    # stages 3..5 exceed critf, then the source pads by one stage on each side.
    fractions = np.array([0.0, 1e-12, 1e-10, 1e-4, 0.8, 0.19, 1e-10, 1e-14])
    result = select_ion_stage_limits(fractions, nnz=6, critf=1e-8)
    assert (result.mml, result.mmu) == (2, 6)
    all_result = select_ion_stage_limits(fractions, nnz=6, critf=1e-35)
    assert (all_result.mml, all_result.mmu) == (1, 6)


class _FakeMaster:
    def __init__(self):
        self.headers = {
            101: SimpleNamespace(data_type=50, rate_type=1),
            102: SimpleNamespace(data_type=53, rate_type=7),
            103: SimpleNamespace(data_type=53, rate_type=7),
            104: SimpleNamespace(data_type=1, rate_type=8),
            105: SimpleNamespace(data_type=99, rate_type=6),
            106: SimpleNamespace(data_type=50, rate_type=4),
        }
        self.ints = {
            101: np.array([0, 1]),
            102: np.array([1, 0]),
            103: np.array([2, 0]),
            104: np.array([0, 1]),
            105: np.array([0, 1]),
            106: np.array([0, 1]),
        }

    def header(self, record):
        return self.headers[record]

    def record_integers(self, record):
        return self.ints[record]


class _FakeDispatcher:
    def evaluate_record_number(self, master, record, context, **kwargs):
        endpoints = {
            101: (1, 2),
            102: (1, 4),  # accepted: nlev+2 for nlev=2
            103: (2, 3),  # record itself is excluded before dispatch
            104: (1, 2),
            105: (1, 2),
        }
        ans1 = {101: 2.0, 102: 3.0, 104: 5.0, 105: 7.0}[record]
        id1, id2 = endpoints[record]
        return SimpleNamespace(
            status=UCalcStatus.EVALUATED,
            idest1=id1,
            idest2=id2,
            ans1=ans1,
            ans2=0.0,
            reason="",
        )


def test_calc_ion_rates_uses_only_source_selected_families(monkeypatch):
    # Avoid requiring a real packed level table for this exact traversal test.
    monkeypatch.setattr(ib, "build_level_table", lambda *args, **kwargs: SimpleNamespace())
    monkeypatch.setattr(ib, "_parent_destination_context", lambda *args, **kwargs: ({}, {}))

    npfi = np.zeros((16, 2), dtype=int)
    npfi[1, 1] = 101
    npfi[7, 1] = 102
    npfi[8, 1] = 104
    npfi[6, 1] = 105
    npfi[4, 1] = 106
    # A second rate-7 row with packed idest1=2 follows the selected one.
    npnxt = np.zeros(107, dtype=int)
    npnxt[102] = 103
    npnxt[103] = 0
    npar = np.zeros(107, dtype=int)
    for record in range(101, 107):
        npar[record] = 900
    derived = SimpleNamespace(
        n_ions=1,
        ion_records=np.array([0, 900]),
        ion_element_z=np.array([0, 8]),
        ion_stage=np.array([0, 7]),
        nlevs=np.array([0, 2]),
        npfi=npfi,
        npnxt=npnxt,
        npar=npar,
    )
    result = calc_ion_rates(
        _FakeMaster(),
        derived,
        ion_index=1,
        context=CalcIonRatesContext(temperature_k=1e6, hydrogen_density_cm3=1e8, electron_fraction_xee=1.0),
        dispatcher=_FakeDispatcher(),
    )
    assert result.pirti == pytest.approx(5.0)  # rate 1 + ground-state rate 7
    assert result.rrrti == pytest.approx(12.0)  # rate 8 + rate 6
    assert [row.record for row in result.contributions] == [101, 105, 102, 104]
    assert result.n_records_selected == 4
    assert result.n_records_blocked == 0
    assert result.ready is True


def _fake_pre_matrix(master, derived, *, element_z, context, critf, dispatcher=None):
    rates = {
        1: SimpleNamespace(ready=True, pirti=11.0, rrrti=21.0, contributions=[], ion_index=1),
        2: SimpleNamespace(ready=True, pirti=12.0, rrrti=22.0, contributions=[], ion_index=2),
    }
    preliminary = SimpleNamespace(
        n_rates=2,
        fractions=np.array([0.0, 0.5, 0.3, 0.2]),
    )
    limits = SimpleNamespace(mml=1, mmu=2)
    return rates, preliminary, limits


def _fake_element_with_guard(master, derived, *, element_z, context, dispatcher=None):
    rows = [
        SimpleNamespace(compact_index=1, roles=[{"ion_stage": 1, "local_level": 1}]),
        SimpleNamespace(compact_index=2, roles=[{"ion_stage": 2, "local_level": 1}]),
    ]
    blocks = [SimpleNamespace(ion_stage=1), SimpleNamespace(ion_stage=2)]
    assembly = SimpleNamespace(
        basis=SimpleNamespace(rows=rows, blocks=blocks),
        # one-based guard followed by the two real LTE entries
        initial_populations=np.array([0.0, 0.8, 0.2]),
    )
    solve = SimpleNamespace(
        heating=0.0, cooling=0.0, heating2=0.0, cooling2=0.0,
        ion_population_totals=np.array([0.7, 0.2]),
        ionization_totals=np.array([31.0, 32.0]),
        recombination_totals=np.array([41.0, 42.0]),
        ionization_components=np.zeros((5, 2)),
        recombination_components=np.zeros((5, 2)),
        populations=np.array([0.7, 0.2]),
        gamma=np.zeros(2), alpha=np.zeros(2),
        fgamma=np.zeros((5, 2)), falpha=np.zeros((5, 2)),
        igammamax_record=np.zeros(2, dtype=int),
        ialphamax_record=np.zeros(2, dtype=int),
    )
    return SimpleNamespace(assembly=assembly, solve=solve, full_element_direct_solve_ready=True)


def test_fixed_state_mapping_uses_one_based_lte_and_keeps_pre_rates_separate():
    result = calc_hmc_all(
        object(),
        SimpleNamespace(ion_element_z=np.array([0, 2])),
        elements=[FixedStateElementRequest(2, 1, 2, abundance=1.0)],
        temperature_k=1e6,
        hydrogen_density_cm3=1e8,
        electron_fraction_xee=0.4,
        element_solver=_fake_element_with_guard,
        pre_matrix_solver=_fake_pre_matrix,
    )
    assert result.rnisg[(2, 1, 1)] == pytest.approx(0.8)
    assert result.rnisg[(2, 2, 1)] == pytest.approx(0.2)
    assert result.bilevg[(2, 1, 1)] == pytest.approx(0.7 / 0.8)
    assert result.pirt[(2, 1)] == pytest.approx(11.0)
    assert result.rrrt[(2, 2)] == pytest.approx(22.0)
    assert result.stotg[(2, 1)] == pytest.approx(31.0)
    assert result.atotg[(2, 2)] == pytest.approx(42.0)


def test_bounded_calc_hmc_all_probe_comparator(tmp_path):
    from xstar_atomic.source_port import (
        compare_calc_hmc_all_pre_continuum_probe,
        write_calc_hmc_all_pre_continuum_parity_products,
    )

    (tmp_path / "xstar_calc_hmc_element_pre_matrix_probe.csv").write_text(
        "calc_hmc_all_call_id,element_z,ion_stage,pirt,rrrt,xitp,mml,mmu,critf\n"
        "9,2,1,11,21,0.5,1,2,1e-8\n"
        "9,2,2,12,22,0.3,1,2,1e-8\n"
        "9,2,3,0,0,0.2,1,2,1e-8\n"
    )
    (tmp_path / "xstar_calc_hmc_all_pre_continuum_summary_probe.csv").write_text(
        "calc_hmc_all_call_id,temperature_t4,temperature_k,xee,xpx,httot,cltot,httot2,cltot2,enelec,elcter\n"
        "9,100,1000000,0.4,100000000,3,1,4,2,0.4,0\n"
    )
    fake = SimpleNamespace(
        preliminary_ion_fractions={(2, 1): 0.5, (2, 2): 0.3, (2, 3): 0.2},
        pirt={(2, 1): 11.0, (2, 2): 12.0},
        rrrt={(2, 1): 21.0, (2, 2): 22.0},
        mml={2: 1}, mmu={2: 2},
        temperature_k=1e6,
        electron_fraction_xee=0.4,
        hydrogen_density_cm3=1e8,
        httot=3.0, cltot=1.0, httot2=4.0, cltot2=2.0,
        electron_contribution=0.4, elcter=0.0,
    )
    parity = compare_calc_hmc_all_pre_continuum_probe(fake, tmp_path)
    assert parity.call_id == 9
    assert parity.pre_matrix_ready is True
    assert parity.pre_continuum_summary_ready is True
    assert parity.parity_ready is True
    assert parity.n_outside_tolerance == 0
    paths = write_calc_hmc_all_pre_continuum_parity_products(parity, tmp_path / "out")
    assert all(Path(path).is_file() for path in paths.values())


def test_calc_hmc_all_probe_products_are_bounded_and_source_local(tmp_path):
    from xstar_atomic import write_calc_hmc_all_probe_products

    outputs = write_calc_hmc_all_probe_products(tmp_path)
    helper = Path(outputs["helper_fortran"]).read_text()
    assert "XSTAR_ATOMIC_HMC_TARGET_CALL" in helper
    assert "xap_hmc_capture" in helper
    assert "xstar_calc_hmc_element_pre_matrix_probe.csv" in helper
    assert "xstar_calc_hmc_all_pre_continuum_summary_probe.csv" in helper
    assert "xstar_calc_hmc_all_pre_continuum_levels_probe.csv" in helper
    assert "call xap_hmc_begin_call" in Path(outputs["calc_hmc_all_begin_call_insertion"]).read_text()
    assert "before call comp2" in Path(outputs["calc_hmc_all_pre_continuum_insertion"]).read_text()
