// XSTAR-SOURCE-CORRESPONDENCE-BEGIN
// Fortran: No direct Fortran routine.
// Role: Cross-platform process/environment portability boundary.
// Relation: Infrastructure only; no scientific operation.
// Concordance: ARCH-001
// Qualification: 0.6.88.5 WINDOWS_MINGW_NATIVE_BUILD
// XSTAR-SOURCE-CORRESPONDENCE-END

#ifndef XSTAR_PROCESS_HPP
#define XSTAR_PROCESS_HPP

#include <cerrno>
#include <cstdlib>
#include <cstdint>

#if defined(_WIN32)
#ifndef NOMINMAX
#define NOMINMAX
#endif
#include <windows.h>
#include <process.h>
#include <algorithm>
#include <chrono>
#include <filesystem>
#include <mutex>
#include <string>
#include <thread>
#include <utility>
#include <vector>
#else
#include <signal.h>
#include <sys/types.h>
#include <sys/wait.h>
#include <unistd.h>
#endif

namespace xstar_process {

#if defined(_WIN32)
using process_id = std::int64_t;

namespace detail {

inline std::mutex& process_registry_mutex() {
    static std::mutex value;
    return value;
}

inline std::vector<std::pair<process_id,HANDLE>>& process_registry() {
    static std::vector<std::pair<process_id,HANDLE>> value;
    return value;
}

inline void set_errno_from_windows(DWORD code) noexcept {
    switch (code) {
        case ERROR_FILE_NOT_FOUND:
        case ERROR_PATH_NOT_FOUND:
        case ERROR_INVALID_DRIVE:
            errno = ENOENT;
            break;
        case ERROR_ACCESS_DENIED:
        case ERROR_PRIVILEGE_NOT_HELD:
            errno = EACCES;
            break;
        case ERROR_NOT_ENOUGH_MEMORY:
        case ERROR_OUTOFMEMORY:
            errno = ENOMEM;
            break;
        default:
            errno = EIO;
            break;
    }
}

inline std::wstring widen_utf8(const char* text) {
    if (text == nullptr || *text == '\0') return {};
    const int needed = MultiByteToWideChar(CP_UTF8, MB_ERR_INVALID_CHARS, text, -1, nullptr, 0);
    if (needed <= 0) {
        const int fallback = MultiByteToWideChar(CP_ACP, 0, text, -1, nullptr, 0);
        if (fallback <= 0) return {};
        std::wstring out(static_cast<std::size_t>(fallback), L'\0');
        if (MultiByteToWideChar(CP_ACP, 0, text, -1, out.data(), fallback) <= 0) return {};
        if (!out.empty() && out.back() == L'\0') out.pop_back();
        return out;
    }
    std::wstring out(static_cast<std::size_t>(needed), L'\0');
    if (MultiByteToWideChar(CP_UTF8, MB_ERR_INVALID_CHARS, text, -1, out.data(), needed) <= 0) return {};
    if (!out.empty() && out.back() == L'\0') out.pop_back();
    return out;
}

inline std::wstring quote_windows_argument(const std::wstring& arg) {
    if (arg.empty()) return L"\"\"";
    const bool needs_quotes = arg.find_first_of(L" \t\n\v\"") != std::wstring::npos;
    if (!needs_quotes) return arg;
    std::wstring out;
    out.push_back(L'\"');
    std::size_t backslashes = 0;
    for (wchar_t ch : arg) {
        if (ch == L'\\') {
            ++backslashes;
            continue;
        }
        if (ch == L'\"') {
            out.append(backslashes * 2 + 1, L'\\');
            out.push_back(L'\"');
            backslashes = 0;
            continue;
        }
        out.append(backslashes, L'\\');
        backslashes = 0;
        out.push_back(ch);
    }
    out.append(backslashes * 2, L'\\');
    out.push_back(L'\"');
    return out;
}

inline std::wstring build_command_line(char* const argv[]) {
    std::wstring command;
    if (argv == nullptr) return command;
    for (std::size_t i = 0; argv[i] != nullptr; ++i) {
        if (i != 0) command.push_back(L' ');
        command += quote_windows_argument(widen_utf8(argv[i]));
    }
    return command;
}

inline std::wstring resolve_application(const char* path, bool search_path) {
    std::filesystem::path requested(widen_utf8(path));
    if (!search_path) {
        if (requested.extension().empty()) {
            std::error_code ec;
            auto with_exe = requested;
            with_exe += L".exe";
            if (std::filesystem::is_regular_file(with_exe, ec)) requested = with_exe;
        }
        return requested.wstring();
    }
    std::wstring name = requested.wstring();
    std::vector<wchar_t> buffer(32768, L'\0');
    DWORD length = SearchPathW(nullptr, name.c_str(), L".exe", static_cast<DWORD>(buffer.size()), buffer.data(), nullptr);
    if (length > 0 && length < buffer.size()) return std::wstring(buffer.data(), length);
    return name;
}

inline process_id register_process(HANDLE handle, DWORD native_pid) {
    const process_id pid = static_cast<process_id>(native_pid);
    std::lock_guard<std::mutex> lock(process_registry_mutex());
    process_registry().push_back({pid, handle});
    return pid;
}

inline HANDLE lookup_process(process_id pid) {
    std::lock_guard<std::mutex> lock(process_registry_mutex());
    for (const auto& item : process_registry()) if (item.first == pid) return item.second;
    return nullptr;
}

inline void close_registered_process(process_id pid) noexcept {
    std::lock_guard<std::mutex> lock(process_registry_mutex());
    auto& values = process_registry();
    const auto it = std::find_if(values.begin(), values.end(), [pid](const auto& item) { return item.first == pid; });
    if (it == values.end()) return;
    CloseHandle(it->second);
    values.erase(it);
}

inline std::vector<std::pair<process_id,HANDLE>> registered_processes() {
    std::lock_guard<std::mutex> lock(process_registry_mutex());
    return process_registry();
}

} // namespace detail

// Native Windows does not provide fork(). Windows callers use spawn_program()
// below; retaining this fail-closed entry point keeps accidental fork usage
// visible during qualification rather than silently changing semantics.
inline process_id fork_process() noexcept {
    errno = ENOSYS;
    return static_cast<process_id>(-1);
}

// Direct process-image replacement remains available for the xstar-cpp
// passthrough path. The normal Windows orchestration path uses CreateProcessW.
inline int exec_program(const char* path, char* const argv[], bool search_path) {
    std::vector<const char*> av;
    if (argv != nullptr) {
        for (std::size_t i = 0; argv[i] != nullptr; ++i) av.push_back(argv[i]);
    }
    av.push_back(nullptr);
    return search_path ? ::_execvp(path, av.data()) : ::_execv(path, av.data());
}

inline process_id spawn_program(
    const char* path,
    char* const argv[],
    bool search_path,
    const char* cwd = nullptr,
    const char* stdout_stderr_path = nullptr) {
    if (path == nullptr || argv == nullptr || argv[0] == nullptr) {
        errno = EINVAL;
        return static_cast<process_id>(-1);
    }

    std::wstring application = detail::resolve_application(path, search_path);
    std::wstring command = detail::build_command_line(argv);
    std::vector<wchar_t> command_buffer(command.begin(), command.end());
    command_buffer.push_back(L'\0');
    std::wstring cwd_w = detail::widen_utf8(cwd);

    STARTUPINFOW startup{};
    startup.cb = sizeof(startup);
    PROCESS_INFORMATION process{};
    HANDLE redirected = INVALID_HANDLE_VALUE;
    HANDLE null_input = INVALID_HANDLE_VALUE;
    BOOL inherit_handles = FALSE;

    if (stdout_stderr_path != nullptr && *stdout_stderr_path != '\0') {
        SECURITY_ATTRIBUTES security{};
        security.nLength = sizeof(security);
        security.bInheritHandle = TRUE;
        security.lpSecurityDescriptor = nullptr;
        const std::wstring log_w = detail::widen_utf8(stdout_stderr_path);
        redirected = CreateFileW(
            log_w.c_str(), GENERIC_WRITE,
            FILE_SHARE_READ | FILE_SHARE_WRITE | FILE_SHARE_DELETE,
            &security, CREATE_ALWAYS, FILE_ATTRIBUTE_NORMAL, nullptr);
        if (redirected == INVALID_HANDLE_VALUE) {
            detail::set_errno_from_windows(GetLastError());
            return static_cast<process_id>(-1);
        }
        startup.dwFlags |= STARTF_USESTDHANDLES;
        startup.hStdOutput = redirected;
        startup.hStdError = redirected;
        startup.hStdInput = GetStdHandle(STD_INPUT_HANDLE);
        if (startup.hStdInput == nullptr || startup.hStdInput == INVALID_HANDLE_VALUE) {
            null_input = CreateFileW(
                L"NUL", GENERIC_READ, FILE_SHARE_READ | FILE_SHARE_WRITE,
                &security, OPEN_EXISTING, FILE_ATTRIBUTE_NORMAL, nullptr);
            if (null_input == INVALID_HANDLE_VALUE) {
                const DWORD error = GetLastError();
                CloseHandle(redirected);
                detail::set_errno_from_windows(error);
                return static_cast<process_id>(-1);
            }
            startup.hStdInput = null_input;
        }
        inherit_handles = TRUE;
    }

    const BOOL ok = CreateProcessW(
        application.empty() ? nullptr : application.c_str(),
        command_buffer.data(), nullptr, nullptr, inherit_handles, 0, nullptr,
        cwd_w.empty() ? nullptr : cwd_w.c_str(), &startup, &process);
    if (redirected != INVALID_HANDLE_VALUE) CloseHandle(redirected);
    if (null_input != INVALID_HANDLE_VALUE) CloseHandle(null_input);
    if (!ok) {
        detail::set_errno_from_windows(GetLastError());
        return static_cast<process_id>(-1);
    }
    CloseHandle(process.hThread);
    return detail::register_process(process.hProcess, process.dwProcessId);
}

inline process_id wait_process(process_id pid, int* status, int options) {
    const bool nohang = options != 0;
    if (pid != static_cast<process_id>(-1)) {
        HANDLE handle = detail::lookup_process(pid);
        if (handle == nullptr) { errno = ECHILD; return static_cast<process_id>(-1); }
        const DWORD wait = WaitForSingleObject(handle, nohang ? 0u : INFINITE);
        if (wait == WAIT_TIMEOUT) return 0;
        if (wait != WAIT_OBJECT_0) {
            detail::set_errno_from_windows(GetLastError());
            return static_cast<process_id>(-1);
        }
        DWORD code = 127u;
        if (!GetExitCodeProcess(handle, &code)) {
            detail::set_errno_from_windows(GetLastError());
            return static_cast<process_id>(-1);
        }
        if (status != nullptr) *status = static_cast<int>(code);
        detail::close_registered_process(pid);
        return pid;
    }

    for (;;) {
        const auto processes = detail::registered_processes();
        if (processes.empty()) { errno = ECHILD; return static_cast<process_id>(-1); }
        for (const auto& item : processes) {
            const DWORD wait = WaitForSingleObject(item.second, 0u);
            if (wait == WAIT_OBJECT_0) {
                DWORD code = 127u;
                if (!GetExitCodeProcess(item.second, &code)) {
                    detail::set_errno_from_windows(GetLastError());
                    return static_cast<process_id>(-1);
                }
                if (status != nullptr) *status = static_cast<int>(code);
                detail::close_registered_process(item.first);
                return item.first;
            }
        }
        if (nohang) return 0;
        std::this_thread::sleep_for(std::chrono::milliseconds(2));
    }
}

inline int terminate_process(process_id pid) noexcept {
    HANDLE handle = detail::lookup_process(pid);
    if (handle == nullptr) { errno = ECHILD; return -1; }
    if (!TerminateProcess(handle, 143u)) { detail::set_errno_from_windows(GetLastError()); return -1; }
    return 0;
}

inline int force_kill_process(process_id pid) noexcept {
    HANDLE handle = detail::lookup_process(pid);
    if (handle == nullptr) { errno = ECHILD; return -1; }
    if (!TerminateProcess(handle, 137u)) { detail::set_errno_from_windows(GetLastError()); return -1; }
    return 0;
}

inline int wait_nohang() noexcept { return 1; }
inline int decode_wait_status(int status) noexcept { return status; }
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
