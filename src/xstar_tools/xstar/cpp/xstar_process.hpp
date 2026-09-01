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
#include <filesystem>
#include <map>
#include <mutex>
#include <string>
#include <vector>

#if defined(_WIN32)
#ifndef NOMINMAX
#define NOMINMAX
#endif
#include <windows.h>
#include <io.h>
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

namespace detail {
inline std::mutex& process_mutex() { static std::mutex m; return m; }
inline std::map<process_id,HANDLE>& processes() { static std::map<process_id,HANDLE> p; return p; }
inline std::wstring utf8_to_wide(const std::string& text) {
    if (text.empty()) return {};
    const int n=MultiByteToWideChar(CP_UTF8,MB_ERR_INVALID_CHARS,text.data(),static_cast<int>(text.size()),nullptr,0);
    if (n<=0) return std::wstring(text.begin(),text.end());
    std::wstring out(static_cast<std::size_t>(n),L'\0');
    MultiByteToWideChar(CP_UTF8,MB_ERR_INVALID_CHARS,text.data(),static_cast<int>(text.size()),out.data(),n);
    return out;
}
inline std::wstring quote_arg(const std::wstring& arg) {
    if (arg.empty()) return L"\"\"";
    bool quote=false; for (wchar_t c:arg) if (c==L' '||c==L'\t'||c==L'\n'||c==L'\v'||c==L'\"') { quote=true; break; }
    if (!quote) return arg;
    std::wstring out=L"\""; unsigned slashes=0;
    for (wchar_t c:arg) {
        if (c==L'\\') { ++slashes; continue; }
        if (c==L'\"') { out.append(slashes*2+1,L'\\'); out.push_back(L'\"'); slashes=0; continue; }
        out.append(slashes,L'\\'); slashes=0; out.push_back(c);
    }
    out.append(slashes*2,L'\\'); out.push_back(L'\"'); return out;
}
inline HANDLE inheritable_file(const std::filesystem::path& path, DWORD access, DWORD disposition) {
    SECURITY_ATTRIBUTES sa{}; sa.nLength=sizeof(sa); sa.bInheritHandle=TRUE;
    return CreateFileW(path.wstring().c_str(),access,FILE_SHARE_READ|FILE_SHARE_WRITE,&sa,disposition,FILE_ATTRIBUTE_NORMAL,nullptr);
}
inline HANDLE inheritable_stdin() {
    HANDLE h=GetStdHandle(STD_INPUT_HANDLE);
    if (h!=nullptr && h!=INVALID_HANDLE_VALUE) return h;
    SECURITY_ATTRIBUTES sa{}; sa.nLength=sizeof(sa); sa.bInheritHandle=TRUE;
    return CreateFileW(L"NUL",GENERIC_READ,FILE_SHARE_READ|FILE_SHARE_WRITE,&sa,OPEN_EXISTING,FILE_ATTRIBUTE_NORMAL,nullptr);
}
}

inline process_id fork_process() noexcept { errno=ENOSYS; return static_cast<process_id>(-1); }
inline int exec_program(const char* path,char* const argv[],bool search_path) noexcept {
    return search_path ? ::_execvp(path,const_cast<const char* const*>(argv)) : ::_execv(path,const_cast<const char* const*>(argv));
}

inline process_id spawn_program(const std::vector<std::string>& args,
                                const std::filesystem::path& cwd={},
                                const std::filesystem::path& stdout_log={}) noexcept {
    if (args.empty()) { errno=EINVAL; return -1; }
    try {
        std::vector<std::wstring> wide; wide.reserve(args.size());
        for (const auto& a:args) wide.push_back(detail::utf8_to_wide(a));
        std::wstring cmd;
        for (std::size_t i=0;i<wide.size();++i) { if (i) cmd.push_back(L' '); cmd += detail::quote_arg(wide[i]); }
        std::vector<wchar_t> mutable_cmd(cmd.begin(),cmd.end()); mutable_cmd.push_back(L'\0');
        STARTUPINFOW si{}; si.cb=sizeof(si); PROCESS_INFORMATION pi{};
        HANDLE output=INVALID_HANDLE_VALUE, input=INVALID_HANDLE_VALUE;
        BOOL inherit=FALSE;
        if (!stdout_log.empty()) {
            output=detail::inheritable_file(stdout_log,GENERIC_WRITE,CREATE_ALWAYS);
            if (output==INVALID_HANDLE_VALUE) { errno=EIO; return -1; }
            input=detail::inheritable_stdin();
            si.dwFlags|=STARTF_USESTDHANDLES; si.hStdOutput=output; si.hStdError=output; si.hStdInput=input;
            inherit=TRUE;
        }
        std::wstring wcwd; LPCWSTR cwdp=nullptr;
        if (!cwd.empty()) { wcwd=cwd.wstring(); cwdp=wcwd.c_str(); }
        const BOOL ok=CreateProcessW(nullptr,mutable_cmd.data(),nullptr,nullptr,inherit,0,nullptr,cwdp,&si,&pi);
        if (output!=INVALID_HANDLE_VALUE) CloseHandle(output);
        if (input!=INVALID_HANDLE_VALUE && input!=GetStdHandle(STD_INPUT_HANDLE)) CloseHandle(input);
        if (!ok) { errno=EIO; return -1; }
        CloseHandle(pi.hThread);
        const process_id pid=static_cast<process_id>(pi.dwProcessId);
        { std::lock_guard<std::mutex> lock(detail::process_mutex()); detail::processes()[pid]=pi.hProcess; }
        return pid;
    } catch (...) { errno=ENOMEM; return -1; }
}

inline process_id wait_process(process_id pid,int* status,int options) noexcept {
    const bool nohang=(options!=0);
    for (;;) {
        std::lock_guard<std::mutex> lock(detail::process_mutex());
        auto& procs=detail::processes();
        if (pid>=0) {
            auto it=procs.find(pid); if (it==procs.end()) { errno=ECHILD; return -1; }
            const DWORD wr=WaitForSingleObject(it->second,nohang?0:INFINITE);
            if (wr == WAIT_TIMEOUT) return 0;
            if (wr != WAIT_OBJECT_0) { errno=ECHILD; return -1; }
            DWORD code=127; GetExitCodeProcess(it->second,&code); if(status) *status=static_cast<int>(code);
            CloseHandle(it->second); procs.erase(it); return pid;
        }
        if (procs.empty()) { errno=ECHILD; return -1; }
        for (auto it=procs.begin();it!=procs.end();++it) {
            if (WaitForSingleObject(it->second,0)==WAIT_OBJECT_0) {
                DWORD code=127; GetExitCodeProcess(it->second,&code); if(status) *status=static_cast<int>(code);
                const process_id done=it->first; CloseHandle(it->second); procs.erase(it); return done;
            }
        }
        if (nohang) return 0;
        Sleep(10);
    }
}
inline int terminate_process(process_id pid) noexcept {
    std::lock_guard<std::mutex> lock(detail::process_mutex()); auto it=detail::processes().find(pid);
    if(it==detail::processes().end()){errno=ESRCH;return -1;} return TerminateProcess(it->second,143)?0:(errno=EIO,-1);
}
inline int force_kill_process(process_id pid) noexcept {
    std::lock_guard<std::mutex> lock(detail::process_mutex()); auto it=detail::processes().find(pid);
    if(it==detail::processes().end()){errno=ESRCH;return -1;} return TerminateProcess(it->second,137)?0:(errno=EIO,-1);
}
inline int wait_nohang() noexcept { return 1; }
inline int decode_wait_status(int status) noexcept { return status; }
inline void exit_child(int code) noexcept { std::_Exit(code); }
inline long long current_process_id() noexcept { return static_cast<long long>(::_getpid()); }
inline int set_environment(const char* name,const char* value,int overwrite) noexcept {
    if (!overwrite && std::getenv(name) != nullptr) return 0;
    return ::_putenv_s(name,value);
}
inline int unset_environment(const char* name) noexcept { return ::_putenv_s(name,""); }

#else
using process_id = pid_t;
inline process_id fork_process() noexcept { return ::fork(); }
inline int exec_program(const char* path,char* const argv[],bool search_path) noexcept { return search_path ? ::execvp(path,argv) : ::execv(path,argv); }
inline process_id wait_process(process_id pid,int* status,int options) noexcept { return ::waitpid(pid,status,options); }
inline int terminate_process(process_id pid) noexcept { return ::kill(pid,SIGTERM); }
inline int force_kill_process(process_id pid) noexcept { return ::kill(pid,SIGKILL); }
inline int wait_nohang() noexcept { return WNOHANG; }
inline int decode_wait_status(int status) noexcept { if(WIFEXITED(status))return WEXITSTATUS(status); if(WIFSIGNALED(status))return 128+WTERMSIG(status); return 127; }
inline void exit_child(int code) noexcept { ::_exit(code); }
inline long long current_process_id() noexcept { return static_cast<long long>(::getpid()); }
inline int set_environment(const char* name,const char* value,int overwrite) noexcept { return ::setenv(name,value,overwrite); }
inline int unset_environment(const char* name) noexcept { return ::unsetenv(name); }
#endif
} // namespace xstar_process
#endif
