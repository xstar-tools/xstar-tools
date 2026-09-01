#include "xstar_process.hpp"
#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <string>
#include <vector>

int main(int argc, char** argv) {
    if (argc > 1 && std::string(argv[1]) == "--child") {
        const char* value = std::getenv("XSTAR_WINDOWS_PROCESS_SMOKE");
        std::cout << "child_env=" << (value ? value : "") << "\n";
        return value && std::string(value) == "ok" ? 0 : 7;
    }
    if (xstar_process::set_environment("XSTAR_WINDOWS_PROCESS_SMOKE", "ok", 1) != 0) return 2;
    const std::filesystem::path cwd = std::filesystem::current_path();
    const std::filesystem::path log = cwd / "windows_process_smoke.log";
    std::vector<std::string> args{std::filesystem::absolute(argv[0]).string(), "--child"};
    const auto pid = xstar_process::spawn_program(args, cwd, log);
    if (pid < 0) return 3;
    int status = 0;
    if (xstar_process::wait_process(pid, &status, 0) < 0) return 4;
    if (xstar_process::decode_wait_status(status) != 0) return 5;
    std::ifstream in(log);
    std::string text((std::istreambuf_iterator<char>(in)), std::istreambuf_iterator<char>());
    if (text.find("child_env=ok") == std::string::npos) return 6;
    std::cout << "WINDOWS_PROCESS_SMOKE_068854_RESULT=ACCEPT\n";
    return 0;
}
