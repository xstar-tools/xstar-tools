# Frozen parity evidence

These files are stable, byte-for-byte copies of qualification artifacts accepted before the post-parity productization boundary. They are operational dependencies of `tools/qualification/check_parity_freeze.py` and are organized by purpose rather than historical development version.

| Stable file | Historical origin | Accepted SHA-256 |
|---|---|---|
| `cpp44/production_source_hashes_44.json` | `tools/qualification/v064812345/production_source_hashes_44.json` | `973422c415264718f9acfe65171dfe097cb9519a4cb0073d7c7caa0c25b02c9f` |
| `option15/compare_step_log_science.py` | `tools/qualification/v0648123361/compare_step_log_science.py` | `3973eacb4e772e7a528611fa538b799afcd5d7ab44ba8d708d3835206b59eabe` |
| `option23/compare_step_log_science.py` | `tools/qualification/v064812345332/compare_step_log_science.py` | `9cb905c12691c0749f9e6ebc42f5bf1d70207cfb4931deba669a1d8dc9f19f05` |
| `option23/selftest_option23_comparator.py` | `tools/qualification/v064812345332/selftest_option23_comparator.py` | `b45a1b0f66f1c31ae3d8145f567c8ee411d51d6642f0b9692851da04148d29ad` |

The Option-23 comparator and self-test intentionally retain their accepted original basenames within a stable `option23/` directory, so the byte-identical self-test remains directly runnable.

Do not rewrite these files during ordinary productization. If comparator science is intentionally reopened, treat that as a new science revision and requalify it before replacing the pinned evidence.
