#ifndef XSTAR_PRODUCTION_ZONE_BRIDGE_H
#define XSTAR_PRODUCTION_ZONE_BRIDGE_H

#include <cstddef>
#include <cstdint>

#ifdef __cplusplus
extern "C" {
#endif

#define XSTAR_PRODUCTION_ZONE_ABI_V06481021 60481021

int32_t xstar_production_zone_abi_version_v06481021(void);
const char* xstar_production_zone_backend_name_v06481021(void);

/*
 * Run the exact standalone-production controller/product-state implementation
 * in-process.  This deliberately shares xstar_standalone.cpp rather than
 * reconstructing a second DSEC/zone controller around fixed_state_engine.
 */
int32_t xstar_production_zone_run_v06481021(
    const char* parameters_path,
    const char* output_dir,
    const char* executable_path,
    char* message,
    std::size_t message_size);

#ifdef __cplusplus
}
#endif

#endif
