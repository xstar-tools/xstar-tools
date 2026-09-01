#pragma once

// 0.6.88.4.1 MACOS_WARNING_CLEANUP
// Keep warning cleanup narrowly scoped to Apple Clang so the accepted Linux
// declarations and runtime expressions remain unchanged.
#if defined(__APPLE__) && defined(__clang__)
#define XSTAR_APPLE_MAYBE_UNUSED [[maybe_unused]]
#define XSTAR_APPLE_CLANG_DIAGNOSTIC_PUSH _Pragma("clang diagnostic push")
#define XSTAR_APPLE_CLANG_IGNORE_DEPRECATED_DECLARATIONS \
    _Pragma("clang diagnostic ignored \"-Wdeprecated-declarations\"")
#define XSTAR_APPLE_CLANG_DIAGNOSTIC_POP _Pragma("clang diagnostic pop")
#else
#define XSTAR_APPLE_MAYBE_UNUSED
#define XSTAR_APPLE_CLANG_DIAGNOSTIC_PUSH
#define XSTAR_APPLE_CLANG_IGNORE_DEPRECATED_DECLARATIONS
#define XSTAR_APPLE_CLANG_DIAGNOSTIC_POP
#endif
