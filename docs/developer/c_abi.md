# Native C ABI contract

The Python bindings and native productization layers use two separately
versioned C interfaces.  Their versions are intentionally independent of the
Python distribution version and the frozen science revision.

## Public XSTAR API

Header: `src/xstar_tools/xstar/cpp/xstar_api.h`

Current ABI:

```text
XSTAR_API_ABI_VERSION = 60487
XSTAR_API_VERSION_STRING = 0.6.90.5.5
```

Runtime identity functions:

```c
uint32_t xstar_api_abi_version(void);
const char* xstar_api_version_string(void);
```

The header also exports the context/configuration, backend-discovery,
zone-evaluation, component-information, and statistics interfaces.  Structure
sizes and `abi_version` fields are part of the compatibility contract.

## Production-zone ABI

Header: `src/xstar_tools/xstar/cpp/xstar_production_zone_bridge.h`

Current ABI:

```text
XSTAR_PRODUCTION_ZONE_ABI_V0648110 = 6048110
```

Runtime identity functions:

```c
int32_t xstar_production_zone_abi_version_v0648110(void);
const char* xstar_production_zone_backend_name_v0648110(void);
```

The production-zone surface exports:

- one-shot `xstar_production_zone_run_all_v0648110()` (`zone-all`);
- persistent context create/run-next/done/finalize/destroy functions
  (`zone-cpp`).

Both call the same `command_run_standalone_production()` scientific
implementation used by standalone `xstar_cpp run-production`.

## Compatibility rules

1. Package/API productization releases may advance without changing either ABI.
2. A C ABI change requires an intentional ABI revision, documentation, tests,
   and qualification; do not reuse `60487` or `6048110` for incompatible
   layouts or semantics.
3. The runtime ABI query must agree with the frontend's compiled expectation
   before `xstar-cpp` starts science.
4. Science revision `0.6.90.5.5` remains separately reported.
5. Historical exported identifiers containing version suffixes are preserved
   for compatibility; source-architecture naming changes do not rewrite them.
