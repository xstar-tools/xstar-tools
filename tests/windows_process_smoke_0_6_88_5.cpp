#include "xstar_process.hpp"
#include <cstdlib>
#include <fstream>
#include <iostream>
#include <string>
#include <vector>

int main(int argc, char** argv) {
#if !defined(_WIN32)
    (void)argc; (void)argv;
    return 77;
#else
    if (argc != 2) return 2;
    const std::string log = argv[1];
    if (xstar_process::set_environment("XSTAR_WINDOWS_PROCESS_SMOKE", "present", 1) != 0) return 3;
    const char* value = std::getenv("XSTAR_WINDOWS_PROCESS_SMOKE");
    if (value == nullptr || std::string(value) != "present") return 4;
    if (xstar_process::unset_environment("XSTAR_WINDOWS_PROCESS_SMOKE") != 0) return 5;
    if (std::getenv("XSTAR_WINDOWS_PROCESS_SMOKE") != nullptr) return 6;

    std::vector<std::string> storage{"cmd.exe", "/c", "echo XSTAR_WINDOWS_PROCESS_SMOKE_OK & exit /b 7"};
    std::vector<char*> av;
    for (auto& item : storage) av.push_back(item.data());
    av.push_back(nullptr);
    auto pid = xstar_process::spawn_program(storage[0].c_str(), av.data(), true, nullptr, log.c_str());
    if (pid < 0) return 8;
    int status = 0;
    if (xstar_process::wait_process(pid, &status, 0) != pid) return 9;
    if (xstar_process::decode_wait_status(status) != 7) return 10;
    std::ifstream in(log);
    std::string contents((std::istreambuf_iterator<char>(in)), std::istreambuf_iterator<char>());
    if (contents.find("XSTAR_WINDOWS_PROCESS_SMOKE_OK") == std::string::npos) return 11;
    std::cout << "WINDOWS_PROCESS_SMOKE=ACCEPT\n";
    return 0;
#endif
}
