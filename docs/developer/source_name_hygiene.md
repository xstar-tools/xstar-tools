# Source-name hygiene and ABI naming

`xstar_tools` separates **private implementation names** from **exported ABI symbol names**.

Private Python/C++ helpers should use stable semantic names. Development-version labels such as `_v0648...` or `_patch...` should not be introduced into private function definitions. If a historical helper is unreachable, remove it rather than preserving a campaign-era name indefinitely.

Exported C-linkage symbols are different: their spelling is part of the ABI. Existing `_v1` and production-zone `_v0648110` exports remain versioned because external binaries, plugins, `ctypes`, or dynamic-library clients may bind those exact names. Renaming internal callers does not make an ABI rename safe.

If a cleaner semantic C API is introduced later, add wrapper/alias symbols while retaining the old exports for a documented ABI transition. Remove old exported names only under an intentional ABI revision with qualification.

## Warning-only annotations

Compiler-warning cleanup may use local standard-language annotations such as `[[maybe_unused]]` where appropriate. Do not hide broad warning classes with global `-Wno-*` flags simply to make a release appear clean.

Current science-critical naming/ABI changes are governed by the compact parity-freeze and source-concordance gates rather than by closed version-specific source-name manifests.
