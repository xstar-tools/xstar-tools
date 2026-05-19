# Oxygen v0.4.34 correction targets

This frozen manifest records the six bounded discrepancy groups isolated from
the complete v0.4.33 oxygen diagnosis archive. It is a regression-selection
oracle, not a replacement for a v0.4.34 production rerun.

The baseline target counts are:

- 35 milestone-blocking `global_level_rnisg` rows;
- 349 `global_level_bilevg` rows;
- 205 type-53 exact `leveltemp` rows;
- 196 type-53 rate-7 `cj2` records;
- 7 type-99 `ans5` records;
- 2 thermal-family rows.

After the three v0.4.34 source-semantic corrections, a production rerun must
reduce all six counts to zero and report
`oxygen_pre_continuum_acceptance_ready=True`.
