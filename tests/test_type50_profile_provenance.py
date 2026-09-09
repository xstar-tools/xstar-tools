from types import SimpleNamespace

import numpy as np

from xstar_tools.xstar.type50_profile_provenance import (
    cpp_parity_atomic_mass_amu,
    source_type50_natural_width_ev,
)


class FakeMaster:
    def __init__(self):
        self._reals = {
            10: (0.0, 24.31),
            30: (0.0, 0.0, 1.25e14),
            31: (0.0, 0.0, 2.50e14),
        }
        self._ints = {
            30: (0, 7),
            31: (0, 9),
        }

    def record_reals(self, rec):
        return self._reals.get(int(rec), ())

    def record_integers(self, rec):
        return self._ints.get(int(rec), ())


def fake_derived():
    npar = np.zeros(64, dtype=int)
    npnxt = np.zeros(64, dtype=int)
    npfi = np.zeros((42, 4), dtype=int)
    ion_records = np.zeros(4, dtype=int)
    ion_element_z = np.zeros(4, dtype=int)
    # record 20 is ion header, parent element 10; records 30/31 are rate-41.
    npar[20] = 10
    npar[40] = 20
    npar[30] = 20
    npar[31] = 20
    npnxt[30] = 31
    npfi[41, 2] = 30
    ion_records[2] = 20
    ion_element_z[2] = 12
    return SimpleNamespace(
        npar=npar, npnxt=npnxt, npfi=npfi,
        ion_records=ion_records, ion_element_z=ion_element_z,
    )




def test_deleafnd_match_uses_rate41_third_real():
    d = fake_derived()
    width, rec, matched = source_type50_natural_width_ev(
        FakeMaster(), d, ion_index=2, upper_local=9, fallback_aij_s=9.0e12
    )
    assert matched is True
    assert rec == 31
    assert width == 2.50e14 * 4.136e-15


def test_deleafnd_falls_back_to_type50_aij():
    d = fake_derived()
    width, rec, matched = source_type50_natural_width_ev(
        FakeMaster(), d, ion_index=2, upper_local=11, fallback_aij_s=9.0e12
    )
    assert matched is False
    assert rec == 0
    assert width == 9.0e12 * 4.136e-15
