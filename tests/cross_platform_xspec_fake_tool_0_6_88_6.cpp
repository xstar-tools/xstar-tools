#include <chrono>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <string>
#include <thread>
namespace fs = std::filesystem;

std::string value_after(int argc, char** argv, const std::string& flag, const std::string& fallback="") {
    for (int i=1;i+1<argc;++i) if (argv[i]==flag) return argv[i+1];
    return fallback;
}
int loopcontrol(int argc, char** argv) {
    for (int i=1;i<argc;++i) {
        std::string a=argv[i]; const std::string p="loopcontrol=";
        if (a.rfind(p,0)==0) return std::stoi(a.substr(p.size()));
    }
    return 0;
}
void touch(const fs::path& p, const std::string& text="fake\n") {
    fs::create_directories(p.parent_path()); std::ofstream o(p,std::ios::binary); o<<text;
}
int main(int argc, char** argv) {
    const std::string exe=fs::path(argv[0]).filename().string();
    if (exe.find("initable")!=std::string::npos) {
        fs::path out=value_after(argc,argv,"--output-dir","."); fs::create_directories(out);
        std::ofstream lis(out/"xstinitable.lis");
        for(int i=1;i<=4;++i) lis<<"xstar-cpp fake=1 loopcontrol="<<i<<"\n";
        touch(out/"xstinitable.fits"); return 0;
    }
    if (exe.find("table")!=std::string::npos) {
        fs::path out=value_after(argc,argv,"--output-dir",".");
        for(const char* n:{"xout_ain.fits","xout_aout.fits","xout_mtable.fits","xout_etable.fits"}) touch(out/n);
        return 0;
    }
    fs::path out=value_after(argc,argv,"--output","."); const int lc=loopcontrol(argc,argv);
    if(lc<=0) return 9;
    std::this_thread::sleep_for(std::chrono::milliseconds(80*(5-lc)));
    touch(out/"xout_spect1.fits", "spectrum "+std::to_string(lc)+"\n");
    touch(out/"xout_step.log", "step "+std::to_string(lc)+"\n");
    std::cout<<"fake_loopcontrol="<<lc<<"\n"; return 0;
}
