from __future__ import annotations

from types import SimpleNamespace

import numpy as np

import xstar_atomic as xa
from xstar_atomic.source_port.output_writers import (
    LevelOutputMetadata,
    SourceOutputMetadata,
    _detail_level_vector,
)
from xstar_atomic.source_port.physical_runner import _guard_full_global_level_array


def test_v0477_active_prefix_is_restored_to_full_source_nnml_capacity():
    derived = SimpleNamespace(
        n_level_records=8,
        npilev=np.asarray(
            [
                [0, 0, 0],
                [0, 1, 5],
                [0, 2, 8],
            ],
            dtype=np.int64,
        ),
    )
    guarded = _guard_full_global_level_array([0.25, 0.5, 0.75], derived)
    assert guarded.shape == (9,)
    assert guarded.tolist() == [0.0, 0.25, 0.5, 0.75, 0.0, 0.0, 0.0, 0.0, 0.0]


def test_v0477_full_capacity_vector_reaches_detail_writer_without_short_array_error():
    derived = SimpleNamespace(
        n_level_records=8,
        npilev=np.asarray([[0, 0], [0, 1], [0, 8]], dtype=np.int64),
    )
    metadata = SourceOutputMetadata(
        levels=(
            LevelOutputMetadata(1, 1, 0.0, "h_i", 1, "ground", 1),
            LevelOutputMetadata(8, 1, 10.0, "h_i", 1, "upper", 2),
        ),
        lines=(),
        rrcs=(),
    )
    guarded = _guard_full_global_level_array([1.0, 2.0, 3.0], derived)
    detail = _detail_level_vector(guarded, metadata)
    assert detail.shape == (8,)
    assert detail[:3].tolist() == [1.0, 2.0, 3.0]
    assert np.count_nonzero(detail[3:]) == 0


def test_v0477_version():
    assert xa.__version__ == "0.4.84"
