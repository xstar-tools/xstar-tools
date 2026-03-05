import sys
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def test_export_module_imports():
    pytest.importorskip("astropy")
    from xstar_atomic.export import export_superwind_bundle, parse_ion_list, ion_slug

    assert parse_ion_list("O VIII,Ne IX") == ["O VIII", "Ne IX"]
    assert ion_slug("O VIII") == "o_viii"
    assert callable(export_superwind_bundle)
