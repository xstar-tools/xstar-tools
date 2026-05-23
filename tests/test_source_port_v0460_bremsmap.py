from __future__ import annotations

import numpy as np
import pytest

import xstar_atomic as xa
from xstar_atomic.source_port import (
    BremsMapPortError,
    XSTARPythonDriver,
    XSTARPythonState,
    XSTARSourceRoutine,
    apply_bremsmap_to_state,
    bremsmap,
    nbinc,
    register_bremsmap_source_routine,
    run_direct_fortran_reference_validation,
)


def test_v0460_direct_original_fortran_cases_pass():
    summary = run_direct_fortran_reference_validation()
    assert summary["bremsmap_source_acceptance_ready"] is True
    assert summary["reduced_grid_mapping_ready"] is True
    assert summary["caller_owned_bremsint_tail_ready"] is True


def test_v0460_literal_tail_and_partial_mutation_semantics():
    epi = np.asarray([1., 2., 4., 8., 16., 32., 64., 128.])
    brem = np.asarray([1., 2., 3., 4., 5., 6., 7., 8.])
    epim = np.asarray([1., 5., 20.])
    before_map = np.asarray([9., 9., 9., 77., 88.])
    before_int = np.asarray([1., 2., 3., 100., 200., 300., 400., 500.])
    out = bremsmap(brem, before_int, epi, epim, ncn2=8, ncn2m=3, bremsam_before=before_map)
    assert out.bremsam_after[3:].tolist() == [77., 88.]
    assert out.bremsint_after[3] == 100.0
    assert np.array_equal(out.bremsint_after[3:], before_int[3:])
    assert out.mapped_high_resolution_indices_one_based.tolist() == [2, 3, 5]


def test_v0460_nbinc_uses_reduced_search_extent():
    epi = np.asarray([2.0 ** i for i in range(12)])
    # ncn2=12 -> numcon3=10, so the selected index cannot exceed 10.
    assert nbinc(1.0e20, epi, 12) == 10


def test_v0460_epim_stop_is_explicit_error():
    with pytest.raises(BremsMapPortError, match="epim error"):
        bremsmap([1., 2., 3.], [0., 0.], [1., 2., 3.], [1.0e-40], ncn2=3, ncn2m=1)


def test_v0460_state_mutation_and_driver_registration():
    state = XSTARPythonState()
    state.radiation.epi = np.asarray([1., 2., 4., 8., 16., 32., 64., 128.])
    state.radiation.bremsa = np.arange(1., 9.)
    state.radiation.epim = np.asarray([1., 5., 20.])
    state.radiation.bremsam = np.full(8, -1.0)
    state.radiation.bremsint = np.asarray([0., 0., 0., 10., 20., 30., 40., 50.])
    state.control.update(ncn2=8, ncn2m=3)
    result = apply_bremsmap_to_state(state)
    assert state.radiation.bremsam[:3] == pytest.approx(result.bremsam_after[:3])
    assert state.radiation.bremsint[3] == 10.0
    driver = XSTARPythonDriver()
    register_bremsmap_source_routine(driver)
    assert XSTARSourceRoutine.BREMSMAP in driver.implemented_source_routines()


def test_v0460_version():
    assert xa.__version__ == "0.4.84"
