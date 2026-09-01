// Serial native XSTAR2XSPEC orchestration for xstar_tools 0.6.84.
//
// This executable composes the already-qualified native components:
//   xstar-xspec-initable -> serial xstar-cpp jobs -> xstar-xspec-table.
// It does not implement or alter XSTAR science.  Each grid job is isolated in
// its own output directory, xout_step.log is concatenated in canonical job
// order, and final XSPEC tables are assembled only after every spectrum has
// completed successfully.

#include "xstar_process.hpp"

#include <cerrno>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <sstream>
#include <stdexcept>
#include <string>
#include <sys/types.h>
#include <sys/wait.h>
#include <unistd.h>
#include <vector>

namespace fs = std::filesystem;

namespace {

constexpr const char *kPackageVersion = "0.6.84";

struct Options {
    fs::path input_file;
    fs::path data_dir;
    fs::path output_dir{"."};
    fs::path initable_bin;
    fs::path xstar_cpp_bin;
    fs::path table_bin;
    bool save = false;
    bool restart = false;
    bool verbose = false;
    std::vector<std::string> overrides;
};

void usage(const char *argv0) {
    std::fprintf(stderr,
        "Usage:\n"
        "  %s --input xstinitable.par [--data-dir DIR] --output-dir DIR [options] [key=value ...]\n"
        "  %s --output-dir DIR [options] key=value [key=value ...]\n\n"
        "Complete serial native XSTAR2XSPEC pipeline:\n"
        "  xstar-xspec-initable -> serial xstar-cpp grid -> xstar-xspec-table\n\n"
        "Options:\n"
        "  --input PATH          HEASoft/IRAF-style xstinitable.par\n"
        "  --data-dir DIR       explicit XSTAR atomic-data directory (optional)\n"
        "  --output-dir DIR     final XSTAR2XSPEC output directory\n"
        "  --save               retain per-job work directories after success\n"
        "  --restart            reuse completed per-job spectra/STEP logs in work directory\n"
        "  --verbose            echo child output while also writing xstar2xspec.log\n"
        "  --initable-bin PATH  override xstar-xspec-initable executable\n"
        "  --xstar-cpp PATH     override xstar-cpp executable\n"
        "  --table-bin PATH     override xstar-xspec-table executable\n"
        "  --version            print package version\n"
        "  --help, -h           show this help\n\n"
        "Trailing key=value arguments override values loaded from --input.\n"
        "If --data-dir is omitted, each xstar-cpp job performs its normal data discovery\n"
        "(XSTAR_DATA, then $HEADAS/refdata, then legacy fallbacks).\n",
        argv0, argv0);
}

fs::path sibling(const char *argv0, const char *name) {
    std::error_code ec;
    fs::path self = fs::absolute(fs::path(argv0), ec);
    if (ec) self = fs::path(argv0);
    return self.parent_path() / name;
}

std::vector<std::string> shell_split(const std::string &line) {
    std::vector<std::string> out;
    std::string current;
    enum class Quote { none, single, dbl } quote = Quote::none;
    bool escape = false;
    auto flush = [&]() {
        if (!current.empty()) { out.push_back(current); current.clear(); }
    };
    for (char c : line) {
        if (escape) { current.push_back(c); escape = false; continue; }
        if (quote == Quote::single) {
            if (c == '\'') quote = Quote::none; else current.push_back(c);
            continue;
        }
        if (quote == Quote::dbl) {
            if (c == '"') quote = Quote::none;
            else if (c == '\\') escape = true;
            else current.push_back(c);
            continue;
        }
        if (c == '\'') quote = Quote::single;
        else if (c == '"') quote = Quote::dbl;
        else if (c == '\\') escape = true;
        else if (c == ' ' || c == '\t') flush();
        else current.push_back(c);
    }
    if (escape || quote != Quote::none) throw std::runtime_error("unterminated quote/escape in xstinitable.lis");
    flush();
    return out;
}

int run_capture(const std::vector<std::string> &args, const fs::path &cwd,
                std::ofstream &log, bool verbose) {
    if (args.empty()) return 127;
    int pipefd[2];
    if (::pipe(pipefd) != 0) throw std::runtime_error("pipe failed: " + std::string(std::strerror(errno)));
    const xstar_process::process_id pid = xstar_process::fork_process();
    if (pid < 0) {
        ::close(pipefd[0]); ::close(pipefd[1]);
        throw std::runtime_error("fork failed: " + std::string(std::strerror(errno)));
    }
    if (pid == 0) {
        ::close(pipefd[0]);
        if (!cwd.empty() && ::chdir(cwd.c_str()) != 0) xstar_process::exit_child(126);
        ::dup2(pipefd[1], STDOUT_FILENO);
        ::dup2(pipefd[1], STDERR_FILENO);
        ::close(pipefd[1]);
        std::vector<std::string> storage = args;
        std::vector<char *> av;
        av.reserve(storage.size() + 1);
        for (auto &item : storage) av.push_back(item.data());
        av.push_back(nullptr);
        xstar_process::exec_program(storage[0].c_str(), av.data(), storage[0].find('/') == std::string::npos);
        xstar_process::exit_child(127);
    }
    ::close(pipefd[1]);
    char buffer[8192];
    for (;;) {
        const ssize_t n = ::read(pipefd[0], buffer, sizeof(buffer));
        if (n > 0) {
            log.write(buffer, n); log.flush();
            if (verbose) { std::cout.write(buffer, n); std::cout.flush(); }
        } else if (n == 0) break;
        else if (errno != EINTR) break;
    }
    ::close(pipefd[0]);
    int status = 0;
    while (xstar_process::wait_process(pid, &status, 0) < 0) if (errno != EINTR) return 127;
    return xstar_process::decode_wait_status(status);
}

std::vector<std::string> load_lines(const fs::path &path) {
    std::ifstream in(path);
    if (!in) throw std::runtime_error("cannot read generated plan: " + path.string());
    std::vector<std::string> lines;
    std::string line;
    while (std::getline(in, line)) if (!line.empty()) lines.push_back(line);
    if (lines.empty()) throw std::runtime_error("generated xstinitable.lis contains no jobs");
    return lines;
}

void concatenate_step_logs(const std::vector<fs::path> &paths, const fs::path &destination) {
    std::ofstream out(destination, std::ios::binary | std::ios::trunc);
    if (!out) throw std::runtime_error("cannot create concatenated STEP log: " + destination.string());
    for (const auto &path : paths) {
        std::ifstream in(path, std::ios::binary);
        if (!in) throw std::runtime_error("missing job STEP log: " + path.string());
        out << in.rdbuf();
    }
}

std::string job_name(std::size_t index) {
    char buf[32];
    std::snprintf(buf, sizeof(buf), "%06zu", index);
    return buf;
}

Options parse_options(int argc, char **argv) {
    Options opt;
    for (int i = 1; i < argc; ++i) {
        const std::string arg = argv[i];
        auto need = [&](const char *flag) -> std::string {
            if (i + 1 >= argc) throw std::runtime_error(std::string("missing value for ") + flag);
            return argv[++i];
        };
        if (arg == "--input") opt.input_file = need("--input");
        else if (arg == "--data-dir" || arg == "-data-dir") opt.data_dir = need(arg.c_str());
        else if (arg == "--output-dir" || arg == "--output") opt.output_dir = need(arg.c_str());
        else if (arg == "--initable-bin") opt.initable_bin = need("--initable-bin");
        else if (arg == "--xstar-cpp") opt.xstar_cpp_bin = need("--xstar-cpp");
        else if (arg == "--table-bin") opt.table_bin = need("--table-bin");
        else if (arg == "--save") opt.save = true;
        else if (arg == "--restart") opt.restart = true;
        else if (arg == "--verbose") opt.verbose = true;
        else if (arg == "--version") { std::cout << "xstar-xspec package version " << kPackageVersion << "\n"; std::exit(0); }
        else if (arg == "--help" || arg == "-h") { usage(argv[0]); std::exit(0); }
        else if (!arg.empty() && arg[0] == '-') throw std::runtime_error("unknown option: " + arg);
        else if (arg.find('=') != std::string::npos) opt.overrides.push_back(arg);
        else throw std::runtime_error("expected xstinitable key=value override, got: " + arg);
    }
    if (opt.input_file.empty() && opt.overrides.empty()) throw std::runtime_error("provide --input or xstinitable key=value parameters");
    return opt;
}

void require_regular(const fs::path &path, const std::string &what) {
    if (!fs::is_regular_file(path)) throw std::runtime_error(what + " not produced: " + path.string());
}

}  // namespace

int main(int argc, char **argv) {
    if (argc == 1) { usage(argv[0]); return 0; }
    try {
        Options opt = parse_options(argc, argv);
        if (opt.initable_bin.empty()) opt.initable_bin = sibling(argv[0], "xstar-xspec-initable");
        if (opt.xstar_cpp_bin.empty()) opt.xstar_cpp_bin = sibling(argv[0], "xstar-cpp");
        if (opt.table_bin.empty()) opt.table_bin = sibling(argv[0], "xstar-xspec-table");

        fs::create_directories(opt.output_dir);
        opt.output_dir = fs::absolute(opt.output_dir);
        const fs::path invocation_dir = fs::current_path();
        const fs::path work_dir = opt.output_dir / ".xstar2xspec-work";
        const fs::path jobs_dir = work_dir / "jobs";
        fs::create_directories(jobs_dir);

        std::ofstream log(opt.output_dir / "xstar2xspec.log", std::ios::out | std::ios::trunc);
        if (!log) throw std::runtime_error("cannot create xstar2xspec.log");
        log << "xstar_tools " << kPackageVersion << " serial native XSTAR2XSPEC\n";

        std::vector<std::string> planner{opt.initable_bin.string(), "--xstar", "cpp", "--output-dir", opt.output_dir.string()};
        if (!opt.input_file.empty()) { planner.push_back("--input"); planner.push_back(fs::absolute(opt.input_file).string()); }
        if (!opt.data_dir.empty()) { planner.push_back("--data-dir"); planner.push_back(fs::absolute(opt.data_dir).string()); }
        planner.insert(planner.end(), opt.overrides.begin(), opt.overrides.end());
        log << "[planner] " << opt.initable_bin << "\n";
        if (run_capture(planner, invocation_dir, log, opt.verbose) != 0) throw std::runtime_error("xstar-xspec-initable failed");

        const fs::path lis_path = opt.output_dir / "xstinitable.lis";
        const fs::path initable_path = opt.output_dir / "xstinitable.fits";
        require_regular(lis_path, "xstinitable.lis");
        require_regular(initable_path, "xstinitable.fits");
        const auto lines = load_lines(lis_path);

        std::vector<fs::path> spectra;
        std::vector<fs::path> steps;
        spectra.reserve(lines.size());
        steps.reserve(lines.size());

        for (std::size_t i = 0; i < lines.size(); ++i) {
            const std::size_t job_index = i + 1;
            const fs::path job_dir = jobs_dir / job_name(job_index);
            fs::create_directories(job_dir);
            const fs::path spectrum = job_dir / "xout_spect1.fits";
            const fs::path step = job_dir / "xout_step.log";
            const bool complete = fs::is_regular_file(spectrum) && fs::is_regular_file(step);
            if (!(opt.restart && complete)) {
                std::vector<std::string> job = shell_split(lines[i]);
                if (job.empty() || job[0] != "xstar-cpp") throw std::runtime_error("native serial pipeline requires cpp xstinitable plan");
                job[0] = opt.xstar_cpp_bin.string();
                job.insert(job.begin() + 1, {"--output", job_dir.string()});
                log << "[job " << job_index << "/" << lines.size() << "] begin\n";
                const int rc = run_capture(job, invocation_dir, log, opt.verbose);
                log << "[job " << job_index << "/" << lines.size() << "] return_code=" << rc << "\n";
                if (rc != 0) throw std::runtime_error("xstar-cpp job " + std::to_string(job_index) + " failed with return code " + std::to_string(rc));
                require_regular(spectrum, "job xout_spect1.fits");
                require_regular(step, "job xout_step.log");
            } else {
                log << "[job " << job_index << "/" << lines.size() << "] restart_reuse\n";
            }
            spectra.push_back(spectrum);
            steps.push_back(step);
        }

        concatenate_step_logs(steps, opt.output_dir / "xout_step.log");

        std::vector<std::string> table{opt.table_bin.string(), "--initable", initable_path.string(), "--output-dir", opt.output_dir.string()};
        for (const auto &path : spectra) table.push_back(path.string());
        log << "[table] begin\n";
        const int table_rc = run_capture(table, invocation_dir, log, opt.verbose);
        log << "[table] return_code=" << table_rc << "\n";
        if (table_rc != 0) throw std::runtime_error("xstar-xspec-table failed with return code " + std::to_string(table_rc));

        for (const char *name : {"xout_ain.fits", "xout_aout.fits", "xout_mtable.fits", "xout_etable.fits", "xout_step.log"})
            require_regular(opt.output_dir / name, name);

        if (!opt.save) {
            std::error_code ec;
            fs::remove_all(work_dir, ec);
            if (ec) log << "[cleanup] warning=" << ec.message() << "\n";
        }

        std::cout << "XSTAR_XSPEC_0684_JOBS=" << lines.size() << "\n";
        std::cout << "XSTAR_XSPEC_0684_LOOPCONTROL_FIRST=1\n";
        std::cout << "XSTAR_XSPEC_0684_LOOPCONTROL_LAST=" << lines.size() << "\n";
        std::cout << "XSTAR_XSPEC_0684_TABLES=4\n";
        std::cout << "XSTAR_XSPEC_0684_RESULT=ACCEPT\n";
        return 0;
    } catch (const std::exception &exc) {
        std::fprintf(stderr, "xstar-xspec: %s\n", exc.what());
        return 1;
    }
}
