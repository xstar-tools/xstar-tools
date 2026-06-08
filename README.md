## v0.6.35 four-family rate-payload product promoted

This package promotes exact C++ rate-payload execution for Mg 4:50, 3:51, 3:63, and 42:88.

Normal execution elides the Python scalar seed/oracle for 4:50, 3:63, and 42:88. The accepted direct C++ Type-51 ion batch remains live for 3:51. Reverse verification is opt-in, and any failure triggers a clean whole-element retry on the accepted path.

See `V0635_FOUR_FAMILY_RATE_PAYLOAD_PRODUCT_PROMOTED.md` for controls, provenance, and acceptance requirements.

## v0.6.37 diagnostic four-family candidate

The `v0.6.37` package adds an order-preserving four-family rate-payload candidate with mandatory full reverse verification. It retains the accepted path as the oracle, evaluates native Type-50/63/88 scalars for every supported record, replaces exact C++ rows in-place, and requires exact ordered-stream and solver-input checkpoints before live commit. See `V0637_FOUR_FAMILY_ORDER_PRESERVING_COMMIT_AND_FULL_REVERSE_VERIFICATION.md`.

