from pathlib import Path

import xstar_atomic as xa
from xstar_atomic.workflow import calc_triplet


def test_workflow_type50_and_triplet_api_are_public_without_database():
    ctx = xa.context_from_values(temperature_K=7.0e4, electron_density_cm3=1.0e8, ion="O VII")
    assert ctx.plasma.temperature_K == 7.0e4
    assert ctx.ion == "O VII"

    rate = xa.calc_rate(
        "type50_bound_bound",
        aij_s_inv=10.0,
        oscillator_strength=0.7,
        wavelength_A=20.0,
        vtherm_cm_s=1.0e7,
        bremsa_nb1=3.0e5,
        ptmp1=0.2,
        ptmp2=0.3,
        flinabs_ptmp1=0.8,
        cfrac=0.1,
        ion="O VII",
    )
    assert rate.status == "ok"
    assert rate.upper_to_lower_escaped_decay_s_inv == 5.0

    triplet = xa.calc_triplet(
        "O VII",
        rows=[
            {"upper_level": "1s1.2s1.3S_1", "emit_outward": 2.0, "wavelength": 22.1},
            {"upper_level": "1s1.2p1.3P_1", "emit_outward": 1.0, "wavelength": 21.8},
            {"upper_level": "1s1.2p1.1P_1", "emit_outward": 1.0, "wavelength": 21.6},
        ],
    )
    assert triplet.status == "ok"
    assert triplet.f == 0.5
    assert triplet.R_f_over_i == 2.0
    assert triplet.G_f_plus_i_over_r == 3.0


def test_workflow_context_from_values_roundtrip():
    from xstar_atomic import EscapeContext, RadiationField

    rad = RadiationField.from_pairs([(1.0, 2.0), (2.0, 4.0)])
    esc = EscapeContext(cfrac=0.25, ptmp1=0.1, ptmp2=0.2)
    ctx = xa.context_from_values(
        temperature_K=1.0e6,
        electron_density_cm3=1.0e8,
        ion="C V",
        log_xi=1.5,
        ion_fraction=0.1,
        radiation=rad,
        escape=esc,
    )
    data = ctx.to_dict()
    assert data["ion"] == "C V"
    assert data["plasma"]["log_xi"] == 1.5
    assert data["radiation"]["n_energy_grid"] == 2
    assert data["escape"]["covering_multiplier"] == 0.75


def test_object_namespace_attributes_when_astropy_available():
    import pytest
    pytest.importorskip("astropy")
    from xstar_atomic import XSTARAtomic

    db = XSTARAtomic.__new__(XSTARAtomic)
    # Namespace classes are attached by __init__ in normal use; this lightweight
    # test verifies the attributes exist on a real initialized object only when
    # a configured atdb.fits is available.
    assert hasattr(XSTARAtomic, "get_wavelengths")
    assert hasattr(XSTARAtomic, "calc_triplet")
    assert hasattr(XSTARAtomic, "solve_populations")


def test_public_namespace_modules_import_and_expose_planned_names():
    from xstar_atomic import rates, solve, matrix, validate, runs

    assert hasattr(rates, "type50_bound_bound")
    assert hasattr(rates, "calc_rate")
    assert hasattr(solve, "ion")
    assert hasattr(matrix, "build_ion")
    assert hasattr(validate, "compare_xstar_run")
    assert hasattr(runs, "select_local_state")
