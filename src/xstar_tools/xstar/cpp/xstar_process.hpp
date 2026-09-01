// XSTAR-SOURCE-CORRESPONDENCE-BEGIN
// Fortran: No direct Fortran routine.
// Role: Cross-platform process/environment portability boundary.
// Relation: Infrastructure only; no scientific operation.
// Concordance: ARCH-001
// Qualification: 0.6.88.4 PORTABLE_PROCESS_LAYER
// XSTAR-SOURCE-CORRESPONDENCE-END

#ifndef XSTAR_PROCESS_HPP
#define XSTAR_PROCESS_HPP

#include <cerrno>
#include <cstdlib>
#include <cstdint>

#if defined(_WIN32)
#include <process.h>
#else
#include <signal.h>
#include <sys/types.h>
#include <sys/wait.h>
#include <unistd.h>
#endif

namespace xstar_process {

#if defined(_WIN32)
using process_id = std::intptr_t;

// Windows process creation/wait/termination is intentionally deferred to the
// native MinGW closure.  Callers depend on this interface rather than POSIX
// names so that the backend can be replaced without touching orchestration.
inline process_id fork_process() noexcept {
    errno = ENOSYS;
    return static_cast<process_id>(-1);
}

inline int exec_program(const char*, char* const[], bool) noexcept {
    errno = ENOSYS;
    return -1;
}

inline process_id wait_process(process_id, int*, int) noexcept {
    errno = ENOSYS;
    return static_cast<process_id>(-1);
}

inline int terminate_process(process_id) noexcept {
    errno = ENOSYS;
    return -1;
}

inline int force_kill_process(process_id) noexcept {
    errno = ENOSYS;
    return -1;
}

inline int wait_nohang() noexcept { return 1; }
inline int decode_wait_status(int) noexcept { return 127; }
inline void exit_child(int code) noexcept { std::_Exit(code); }
inline long long current_process_id() noexcept { return static_cast<long long>(::_getpid()); }

inline int set_environment(const char* name, const char* value, int overwrite) noexcept {
    if (!overwrite && std::getenv(name) != nullptr) return 0;
    return ::_putenv_s(name, value);
}

inline int unset_environment(const char* name) noexcept {
    return ::_putenv_s(name, "");
}

#else
using process_id = pid_t;

inline process_id fork_process() noexcept { return ::fork(); }

// Matches execv/execvp exactly: success never returns; failure returns -1 and
// preserves errno for the caller.  search_path selects execvp versus execv.
inline int exec_program(const char* path, char* const argv[], bool search_path) noexcept {
    return search_path ? ::execvp(path, argv) : ::execv(path, argv);
}

inline process_id wait_process(process_id pid, int* status, int options) noexcept {
    return ::waitpid(pid, status, options);
}

inline int terminate_process(process_id pid) noexcept { return ::kill(pid, SIGTERM); }
inline int force_kill_process(process_id pid) noexcept { return ::kill(pid, SIGKILL); }
inline int wait_nohang() noexcept { return WNOHANG; }

inline int decode_wait_status(int status) noexcept {
    if (WIFEXITED(status)) return WEXITSTATUS(status);
    if (WIFSIGNALED(status)) return 128 + WTERMSIG(status);
    return 127;
}

inline void exit_child(int code) noexcept { ::_exit(code); }
inline long long current_process_id() noexcept { return static_cast<long long>(::getpid()); }
inline int set_environment(const char* name, const char* value, int overwrite) noexcept {
    return ::setenv(name, value, overwrite);
}
inline int unset_environment(const char* name) noexcept { return ::unsetenv(name); }
#endif

} // namespace xstar_process

#endif
