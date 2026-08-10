# Source-name hygiene and ABI naming

`xstar_tools` separates **private implementation names** from **exported ABI symbol names**.

Private Python/C++ helpers should use stable semantic names. Development-version labels such as `_v0648...` or `_patch...` must not be introduced into private function definitions. If a historical helper is unreachable, remove it instead of preserving its campaign-era name.

Exported C-linkage symbols are different: their spelling is part of the ABI. Existing `_v1` and production-zone `_v0648110` exports remain versioned in 0.6.76 because already-built binaries, plugins, `ctypes`, or `dlsym` clients may bind those exact names. Renaming both the implementation and in-repository callers would still break external clients.

If a cleaner semantic C API is introduced later, add new semantic wrapper/alias symbols while retaining the old exports for a documented deprecation/ABI transition cycle. Remove old exported names only as an intentional ABI revision with qualification.

The 0.6.76 boundary is enforced by `qualification/source_name_hygiene_0_6_76.json` and `tools/qualification/check_source_name_hygiene_0_6_76.py`. Historical qualification manifests are not rewritten; compatibility checkers accept only exact source hashes pinned by the 0.6.76 hygiene manifest.
