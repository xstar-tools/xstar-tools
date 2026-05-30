// Skeleton rates backend for xstar_atomic/source_port.
//
// v0.5.53 intentionally exposes a stable C ABI without moving physics out of
// the Python reference path yet.  The next releases will fill this interface
// with compact-array Mg rate kernels.  This file is plain C++ and can be linked
// either as libxstar_rates.so for Python ctypes or into a future standalone
// xstar_tools_engine executable.

#include <cstddef>
#include <cstdio>
#include <cstring>

namespace {
constexpr int XSTAR_RATES_ABI_VERSION = 1;
constexpr int XSTAR_RATES_FEATURE_SKELETON = 1;

void write_message(char* errbuf, std::size_t errbuf_size, const char* message) {
    if (errbuf == nullptr || errbuf_size == 0) {
        return;
    }
    std::snprintf(errbuf, errbuf_size, "%s", message == nullptr ? "" : message);
}
}  // namespace

extern "C" {

int xstar_rates_abi_version() {
    return XSTAR_RATES_ABI_VERSION;
}

const char* xstar_rates_backend_name() {
    return "xstar_rates_skeleton";
}

int xstar_rates_feature_flags() {
    return XSTAR_RATES_FEATURE_SKELETON;
}

int xstar_rates_eval_mg(
    int n_ions,
    int n_records,
    const void* compact_payload,
    std::size_t compact_payload_size,
    char* errbuf,
    std::size_t errbuf_size
) {
    (void)compact_payload;
    (void)compact_payload_size;
    if (n_ions < 0 || n_records < 0) {
        write_message(errbuf, errbuf_size, "xstar_rates_eval_mg received negative dimensions");
        return 2;
    }
    write_message(errbuf, errbuf_size, "xstar_rates_eval_mg skeleton ABI OK; no physics executed");
    return 0;
}

}  // extern "C"
