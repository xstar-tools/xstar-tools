from __future__ import annotations

from xstar_tools import __version__
from xstar_tools.xstar import standalone_backend


def test_standalone_python_context_is_persistent() -> None:
    context = standalone_backend.create_context({"backend": "python"})
    first = standalone_backend.run_zone(
        context,
        {
            "zone_id": 1,
            "electron_fraction": 1.2,
            "abundances": [1.0, 0.1],
            "radiation_flux": [3.0, 2.0, 1.0],
        },
        allow_scaffold=True,
    )
    second = standalone_backend.run_zone(
        context,
        {
            "zone_id": 2,
            "electron_fraction": 1.1,
            "abundances": [1.0],
            "radiation_flux": [4.0],
        },
        allow_scaffold=True,
    )
    assert first["backend"] == "python"
    assert second["zone_id"] == 2
    assert standalone_backend.context_stats(context)["zones_completed"] == 2


def test_json_bridge_target() -> None:
    result = standalone_backend.echo_json({"value": 44})
    assert result == {
        "backend": "python",
        "request": {"value": 44},
        "version": __version__,
    }
