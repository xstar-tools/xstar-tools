# Developer guide


Packaging development after the portability closure is documented in {doc}`pip_packaging_refresh_0_6_89`.
The developer documentation is organized around the frozen scientific boundary, the Fortran/Python/C++ source concordance, native execution ownership, qualification, and release portability.

For the current platform matrix and the accepted `0.6.88.6.1.2.1` closure, start with {doc}`cross_platform_portability_status`.

```{toctree}
:maxdepth: 2

architecture
execution_modes
cross_platform_portability_status
qualification
performance_rules
versioning_and_freeze
fortran_source_map
python_cpp_fortran_concordance
function_commenting
public_python_api
unified_cli
xstar_cpp
c_abi
adding_atomic_data
true_mpi_xstar2xspec_0_6_86
cross_platform_qualification_0_6_88_6
cross_platform_fixed_state_equivalence_closure_0_6_88_6_1
cross_platform_workflow_discovery_closure_0_6_88_6_1_1
windows_reference_payload_line_ending_closure_0_6_88_6_1_2
windows_git_preflight_shell_closure_0_6_88_6_1_2_1
pip_packaging_refresh_0_6_89
packaging
conda_packaging
documentation_policy
```

Historical milestone notes remain available in this directory even when they are not all listed in the primary navigation. Their original ACCEPT/REJECT status is preserved rather than rewritten by later closures.
