from __future__ import annotations
import struct
import pytest
np=pytest.importorskip('numpy')
from xstar_tools.xstar.source_real_energy_grid import source_ener_grid

def f32(x): return struct.unpack('f',struct.pack('f',float(x)))[0]

def test_source_real_grid_watched_bins_match_fortran_f32():
    g=source_ener_grid(9999)
    expected={
        2980:10.164740562438965,
        3124:12.709136009216309,
        3152:13.273364067077637,
        6663:3079.720947265625,
        6664:3084.50244140625,
        6665:3089.29150390625,
    }
    assert {one:f32(g[one-1]) for one in expected} == expected

def test_source_real_reduced_grid_checkpoints():
    g=source_ener_grid(999)
    assert g[0] == float(np.float32(0.1))
    assert g[979] == pytest.approx(400000.25130070985,rel=2e-15)
    assert g[998] == pytest.approx(1052223.638783294,rel=2e-15)
