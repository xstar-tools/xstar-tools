// XSTAR-SOURCE-CORRESPONDENCE-BEGIN
// Fortran: No direct Fortran routine; bridges Python control to xstarcalc-equivalent native components.
// Role: C declarations used by the Python/native interoperability layer.
// Relation: Infrastructure only; scientific ownership is delegated to mapped kernels.
// Concordance: BACKEND-001
// Qualification: Python/C++ parity campaign 45.x
// XSTAR-SOURCE-CORRESPONDENCE-END

#ifndef XSTAR_PYTHON_BRIDGE_H
#define XSTAR_PYTHON_BRIDGE_H

#include <stddef.h>
#include <stdint.h>
#include "xstar_api.h"

#ifdef _WIN32
#  ifdef XSTAR_PYTHON_BACKEND_BUILD
#    define XSTAR_PYTHON_BRIDGE_EXPORT __declspec(dllexport)
#  else
#    define XSTAR_PYTHON_BRIDGE_EXPORT
#  endif
#else
#  define XSTAR_PYTHON_BRIDGE_EXPORT __attribute__((visibility("default")))
#endif

#ifdef __cplusplus
extern "C" {
#endif

#define XSTAR_PYTHON_BRIDGE_ABI_VERSION 60450u

XSTAR_PYTHON_BRIDGE_EXPORT uint32_t xstar_python_bridge_abi_version(void);

/*
 * Generic JSON adapter for Python routines. The target callable receives one
 * JSON-decoded object and its return value is JSON-encoded. If response is
 * NULL or too small, *response_size receives the required byte count including
 * the terminating NUL and XSTAR_STATUS_BUFFER_TOO_SMALL is returned.
 */
XSTAR_PYTHON_BRIDGE_EXPORT int xstar_python_call_json_v1(
    const char* module_name,
    const char* callable_name,
    const char* request_json,
    char* response,
    size_t* response_size,
    char* error_message,
    size_t error_message_size
);

#ifdef __cplusplus
}
#endif

#endif
