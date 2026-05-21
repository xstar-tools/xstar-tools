from types import SimpleNamespace

from xstar_atomic.source_port_dsec_physical_cli import _format_element_basis_sizes


def test_physical_dsec_progress_uses_element_assembly_basis() -> None:
    result = SimpleNamespace(
        element_results=(
            SimpleNamespace(
                request=SimpleNamespace(element_z=1),
                equilibrium=SimpleNamespace(
                    assembly=SimpleNamespace(basis=SimpleNamespace(n_rows=2))
                ),
            ),
            SimpleNamespace(
                request=SimpleNamespace(element_z=2),
                equilibrium=SimpleNamespace(
                    assembly=SimpleNamespace(basis=SimpleNamespace(n_rows=7))
                ),
            ),
            SimpleNamespace(
                request=SimpleNamespace(element_z=8),
                equilibrium=SimpleNamespace(
                    assembly=SimpleNamespace(basis=SimpleNamespace(n_rows=367))
                ),
            ),
        )
    )
    assert _format_element_basis_sizes(result) == "Z1:2,Z2:7,Z8:367"
