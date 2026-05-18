from __future__ import annotations

import numpy as np

from xstar_atomic.source_port.ucalc import (
    _xstar_nbinc_fortran_value,
    _xstar_phint53hunt_pass_indices,
)


def test_nbinc_reproduces_nearest_log_grid_source_value():
    # huntf/nbinc returns a one-based nearest-grid value over the continuum
    # range truncated by numcon2=max(2,n/50).
    grid = np.geomspace(1.0, 1.0e4, 100)
    # Exact grid values retain their one-based identity.
    assert _xstar_nbinc_fortran_value(float(grid[20]), grid) == 21
    # A point closer in log space to the successor advances to it.
    midpoint = float(np.sqrt(grid[20] * grid[21])) * 1.0001
    assert _xstar_nbinc_fortran_value(midpoint, grid) == 22


def test_phint53hunt_stride_does_not_force_nphint_endpoint():
    # phint53hunt starts at kl=nb1-1 and advances by nskp.  For these values
    # nphint is not naturally reached and must not be appended.
    assert _xstar_phint53hunt_pass_indices(5, 13, 4) == [4, 8, 12]
    assert _xstar_phint53hunt_pass_indices(5, 13, 2) == [4, 6, 8, 10, 12]
    assert _xstar_phint53hunt_pass_indices(5, 13, 1)[-1] == 13
