# 0.6.88.6.1.2 — WINDOWS_REFERENCE_PAYLOAD_LINE_ENDING_CLOSURE

`0.6.88.6.1.2` is a qualification-only closure for the Windows checkout behavior exposed by `0.6.88.6.1.1`.

The Windows `0.6.88.6.1.1` host run passed native build, warning-free build, process/XSTAR2XSPEC smoke, fixed-state same-host determinism, cross-platform fixed-state reference equivalence, embedded Python, bridge, and regression. Source qualification alone rejected because Git converted the checked-in canonical text fixtures from LF to CRLF before the source checker hashed them.

This release:

- marks the two canonical text fixtures `-text` in `.gitattributes` and the FITS fixture `binary`;
- validates canonical text fixture digests after CRLF/CR -> LF normalization;
- builds the synthetic CRLF test from a normalized source payload, so an already-CRLF checkout cannot generate CRCRLF;
- keeps the FITS reference hash byte-exact;
- preserves same-host raw-byte determinism for generated outputs;
- preserves the `1e-13` relative and `64 ULP` cross-platform numerical equivalence contract;
- keeps Windows MPI out of scope.

No scientific implementation, loader, process, path, embedded-Python, scheduler, publication, or ABI behavior changes.
