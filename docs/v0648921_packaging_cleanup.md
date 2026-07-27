# 0.6.48.9.2.1 packaging and benchmark cleanup

0.6.48.9.2.1 is a qualification-neutral packaging hotfix derived from the accepted 0.6.48.9.2 measurement baseline.

The scientific implementation and 0.6.48.9.2 performance instrumentation are unchanged. The accepted 0.6.48.9.2 timing series remains the performance baseline for this hotfix.

## Removed benchmark material

The release removes benchmark directories that were only historical/internal test fixtures and were not needed by current standalone production, the 0.6.48.9.2 qualification/performance runners, active C++ self-tests, or still-supported CLI regression gates.

Retained old-named benchmark directories are intentional: each still backs an active source-port regression gate, public audit command, C++ self-test, or diagnostic/reference fallback.

## Versioning

The cleanup uses 0.6.48.9.2.1 so that 0.6.48.9.3 remains reserved for the first Type50 profile-kernel performance optimization.
