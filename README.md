## v0.6.35 four-family rate-payload product promoted

This package promotes exact C++ rate-payload execution for Mg 4:50, 3:51, 3:63, and 42:88.

Normal execution elides the Python scalar seed/oracle for 4:50, 3:63, and 42:88. The accepted direct C++ Type-51 ion batch remains live for 3:51. Reverse verification is opt-in, and any failure triggers a clean whole-element retry on the accepted path.

See `V0635_FOUR_FAMILY_RATE_PAYLOAD_PRODUCT_PROMOTED.md` for controls, provenance, and acceptance requirements.

## v0.6.36 promoted Type-50 dependency hotfix

The four-family Mg rate-payload product now evaluates rate 4 / data 50 through a dedicated native engine scalar path instead of consulting the simple-payload cache, which never contained Type-50 records. See `V0636_FOUR_FAMILY_RATE_PAYLOAD_PRODUCT_PROMOTED_TYPE50_NATIVE_HOTFIX.md`.

