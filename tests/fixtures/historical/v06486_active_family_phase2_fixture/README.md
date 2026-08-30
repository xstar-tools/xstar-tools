# v06486 active-family phase-2 fixed-state regression fixture

This is the ABI-current regression form of the historical
`v06485_active_family_phase2_fixture` used by the C++ `make test` fixed-state
smoke tests.

The raw coefficient payload (`rows.csv`, `records.csv`, `elements.csv`,
`ints.txt`, and `reals.txt`) is copied byte-for-byte from the historical 60485
fixture.  Only fixture metadata is advanced to the lowered fixed-state program
ABI `60486` and the fixture identifier is renamed to
`v06486_active_family_phase2_fixture`.

The program ABI advanced to 60486 in `0.6.48.12.1`; the old 60485 fixture had
remained wired into the Makefile regression target and therefore failed before
any fixed-state evaluation.  This fixture is qualification data only and does
not modify production/science code.
