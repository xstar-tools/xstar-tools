# xstar_tools 0.6.48.7.46.25.5.17.25.15

This release is a runtime hotfix for the v17.25.12 sequence-23 call-3 branch thermal boundary closure.  It removes the obsolete dependency that required fixed-state parity closure whenever thermal-component parity closure was enabled.  The component closure is now explicitly a thermal residual-consumption boundary closure and does not replace raw native solve populations or committed population state.

# xstar_tools 0.6.48.7.46.25.5.17.25.7

# xstar_tools 0.6.48.7.46.25.5.17.25.7

See `V04874625517255_SEQUENCE16_MG_RESIDUAL_CLOSURE.md` and `v25517255_sequence16_mg_residual_closure_report.md`.

## v17.25.4 sequence-16 contract classification

The generic resumable trajectory now classifies and accepts sequences 1–16. Sequence 16 retains the Mg stages 3–12 topology, uses a 17,028-row source-faithful thermal ledger, and adds an ion-budget-aware zero criterion for numerically negligible level-population rows. Sequence 17 remains fail-closed. ProductWritingState retention and public product publication remain disabled.

# xstar_tools 0.6.48.7.46.25.5.17.25.4

See `V04874625517254_SEQUENCE16_CONTRACT.md` and `v25517254_sequence16_contract_report.md`.
