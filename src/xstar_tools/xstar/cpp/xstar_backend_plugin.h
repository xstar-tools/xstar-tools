#ifndef XSTAR_BACKEND_PLUGIN_H
#define XSTAR_BACKEND_PLUGIN_H

#include "xstar_api.h"

#ifdef __cplusplus
extern "C" {
#endif

#define XSTAR_BACKEND_PLUGIN_ABI_VERSION 60450u

typedef struct xstar_backend_descriptor_v1 {
    uint32_t struct_size;
    uint32_t plugin_abi_version;
    const char* backend_name;
    const char* implementation;
    uint32_t capability_flags;
    int (*create)(const xstar_config_v1*, void**, char*, size_t);
    void (*destroy)(void*);
    int (*reset)(void*, char*, size_t);
    int (*run_zone)(void*, const xstar_zone_input_v1*, xstar_zone_output_v1*, char*, size_t);
    int (*run_batch)(void*, const xstar_zone_input_v1*, size_t, xstar_zone_output_v1*, char*, size_t);
    int (*get_stats)(const void*, xstar_context_stats_v1*, char*, size_t);
    int (*get_component_info)(const void*, uint32_t, xstar_component_info_v1*, char*, size_t);
} xstar_backend_descriptor_v1;

typedef const xstar_backend_descriptor_v1* (*xstar_backend_get_descriptor_v1_fn)(void);

XSTAR_API_EXPORT const xstar_backend_descriptor_v1* xstar_backend_get_descriptor_v1(void);

#ifdef __cplusplus
}
#endif

#endif
