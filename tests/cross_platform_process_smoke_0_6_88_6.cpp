#include "xstar_process.hpp"
#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <string>
#include <vector>

int main(int argc, char** argv) {
    if (argc > 1 && std::string(argv[1]) == "--child") {
        const char* value = std::getenv("XSTAR_CROSS_PLATFORM_PROCESS_SMOKE");
        std::cout << "child_env=" << (value ? value : "") << "\n";
        return value && std::string(value) == "ok" ? 0 : 7;
    }
    if (xstar_process::set_environment("XSTAR_CROSS_PLATFORM_PROCESS_SMOKE", "ok", 1) != 0) return 2;
    const std::filesystem::path cwd = std::filesystem::current_path();
    const std::filesystem::path exe = std::filesystem::absolute(argv[0]);
    const std::filesystem::path log = cwd / "cross_platform_process_smoke.log";

#if defined(_WIN32)
    std::vector<std::string> args{exe.string(), "--child"};
    const auto pid = xstar_process::spawn_program(args, cwd, log);
    if (pid < 0) return 3;
#else
    const auto pid = xstar_process::fork_process();
    if (pid < 0) return 3;
    if (pid == 0) {
        std::string exe_text = exe.string();
        std::string child_arg = "--child";
        char* child_argv[] = {exe_text.data(), child_arg.data(), nullptr};
        xstar_process::exec_program(exe_text.c_str(), child_argv, false);
        xstar_process::exit_child(8);
    }
#endif

    int status = 0;
    if (xstar_process::wait_process(pid, &status, 0) < 0) return 4;
    if (xstar_process::decode_wait_status(status) != 0) return 5;
#if defined(_WIN32)
    std::ifstream in(log);
    std::string text((std::istreambuf_iterator<char>(in)), std::istreambuf_iterator<char>());
    if (text.find("child_env=ok") == std::string::npos) return 6;
#endif
    std::cout << "CROSS_PLATFORM_PROCESS_SMOKE_06886_RESULT=ACCEPT\n";
    return 0;
}
