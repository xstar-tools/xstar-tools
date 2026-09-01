#include <chrono>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <string>
#include <thread>

namespace fs = std::filesystem;

std::string value_after(int argc, char** argv, const std::string& key) {
    for (int i = 1; i + 1 < argc; ++i) if (argv[i] == key) return argv[i + 1];
    return {};
}

int main(int argc, char** argv) {
    const std::string name = fs::path(argv[0]).filename().string();
    if (name.find("initable") != std::string::npos) {
        const fs::path out = value_after(argc, argv, "--output-dir");
        fs::create_directories(out);
        std::ofstream lis(out / "xstinitable.lis");
        for (int i = 1; i <= 4; ++i) lis << "xstar-cpp loopcontrol=" << i << "\n";
        std::ofstream(out / "xstinitable.fits") << "synthetic-initable\n";
        return 0;
    }
    if (name.find("xstar-cpp") != std::string::npos) {
        const fs::path out = value_after(argc, argv, "--output");
        fs::create_directories(out);
        int loop = 1;
        for (int i = 1; i < argc; ++i) {
            const std::string arg = argv[i];
            if (arg.rfind("loopcontrol=", 0) == 0) loop = std::stoi(arg.substr(12));
        }
        std::this_thread::sleep_for(std::chrono::milliseconds((5 - loop) * 25));
        std::ofstream(out / "xout_spect1.fits") << "synthetic-spectrum " << loop << "\n";
        std::ofstream(out / "xout_step.log") << "synthetic-step " << loop << "\n";
        std::cout << "synthetic worker loopcontrol=" << loop << "\n";
        return 0;
    }
    if (name.find("table") != std::string::npos) {
        const fs::path out = value_after(argc, argv, "--output-dir");
        fs::create_directories(out);
        for (const char* file : {"xout_ain.fits", "xout_aout.fits", "xout_mtable.fits", "xout_etable.fits"})
            std::ofstream(out / file) << "synthetic-table\n";
        return 0;
    }
    return 64;
}
