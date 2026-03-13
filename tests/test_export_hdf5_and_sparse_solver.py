from pathlib import Path

import numpy as np


def test_write_hdf5_rows_roundtrip(tmp_path):
    import pytest
    pytest.importorskip("astropy")
    h5py = pytest.importorskip("h5py")
    from xstar_atomic.export import write_hdf5_rows, write_hdf5_manifest

    path = tmp_path / 'atomic_export.h5'
    rows = [
        {'level_index': 1, 'label': 'ground', 'energy_eV': 0.0},
        {'level_index': 2, 'label': 'upper', 'energy_eV': 10.5},
    ]
    write_hdf5_rows(path, 'levels', rows, metadata={'ion': 'O VIII'})
    write_hdf5_manifest(path, {'ion': 'O VIII', 'n_levels': 2})

    with h5py.File(path, 'r') as h5:
        assert 'levels' in h5
        assert 'manifest_json' in h5
        assert h5['levels'].attrs['ion'] == 'O VIII'
        assert len(h5['levels']['level_index']) == 2
        assert np.isclose(h5['levels']['energy_eV'][1], 10.5)


def test_sparse_solver_matches_dense_for_small_system():
    import pytest
    pytest.importorskip("astropy")
    pytest.importorskip("scipy")
    from xstar_atomic.solver import solve_steady_state

    # Three-level toy atom. R[i, j] is transition rate j -> i.
    R = np.zeros((3, 3), dtype=float)
    R[0, 1] = 10.0   # 2 -> 1 decay
    R[1, 0] = 0.2    # 1 -> 2 excitation
    R[1, 2] = 5.0    # 3 -> 2 decay
    R[2, 1] = 0.05   # 2 -> 3 excitation

    dense_pop, dense_info = solve_steady_state(R, linear_solver='dense')
    sparse_pop, sparse_info = solve_steady_state(R, linear_solver='sparse')

    assert np.isclose(dense_pop.sum(), 1.0)
    assert np.isclose(sparse_pop.sum(), 1.0)
    assert np.allclose(dense_pop, sparse_pop, rtol=1e-9, atol=1e-12)
    assert sparse_info['solver'] in {'scipy.sparse.linalg.spsolve', 'numpy.linalg.lstsq'}
