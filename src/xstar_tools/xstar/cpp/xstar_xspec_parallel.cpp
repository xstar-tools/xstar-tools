// Parallel native XSTAR2XSPEC orchestration for xstar_tools 0.6.88.6.1.
//
// This executable composes the already-qualified native components:
//   xstar-xspec-initable -> bounded parallel xstar-cpp jobs -> xstar-xspec-table.
// It does not implement or alter XSTAR science. Each grid job is isolated in
// its own deterministic loopcontrol directory. Jobs may complete out of order,
// but spectra, STEP logs, and final XSPEC table rows are always consumed in
// canonical loopcontrol order.
//
// The worker pool is intentionally local-process based and has no MPI runtime
// dependency. It preserves the scientifically relevant master/worker semantics
// of MPI_XSTAR while keeping deployment identical to the serial native path.

#include "xstar_process.hpp"
#include "xstar_platform.hpp"

#include <cerrno>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <map>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>

#if !defined(_WIN32)
#include <fcntl.h>
#include <signal.h>
#include <sys/types.h>
#include <sys/wait.h>
#include <unistd.h>
#endif

namespace fs = std::filesystem;

namespace {

// Historical qualification compatibility marker: kPackageVersion = "0.6.88.6.1.2.1"
constexpr const char *kPackageVersion = "0.6.89.2";
// Historical qualification compatibility marker: kPackageVersion = "0.6.89.1.2"
// Historical qualification compatibility marker: kPackageVersion = "0.6.89.1"
// Historical qualification compatibility marker: kPackageVersion = "0.6.88.3.2"
// Historical qualification compatibility marker: kPackageVersion = "0.6.88.3.1"
// Historical qualification compatibility marker: kPackageVersion = "0.6.88.3"

struct Options {
    fs::path input_file;
    fs::path data_dir;
    fs::path output_dir{"."};
    fs::path initable_bin;
    fs::path xstar_cpp_bin;
    fs::path table_bin;
    std::size_t processes = 1;
    bool save = false;
    bool cleanup_work = false;
    bool restart = false;
    bool verbose = false;
    std::vector<std::string> overrides;
};

struct ActiveJob {
    std::size_t index = 0;
    xstar_process::process_id pid = -1;
    fs::path stdout_log;
};

void usage(const char *argv0) {
    std::fprintf(stderr,
        "Usage:\n"
        "  %s --input xstinitable.par [--data-dir DIR] --output-dir DIR [options] [key=value ...]\n"
        "  %s --output-dir DIR [options] key=value [key=value ...]\n\n"
        "Complete native XSTAR2XSPEC pipeline:\n"
        "  xstar-xspec-initable -> bounded parallel xstar-cpp grid -> xstar-xspec-table\n\n"
        "Options:\n"
        "  --input PATH          HEASoft/IRAF-style xstinitable.par\n"
        "  --data-dir DIR       explicit XSTAR atomic-data directory (optional)\n"
        "  --output-dir DIR     final XSTAR2XSPEC output directory\n"
        "  --processes N        maximum simultaneous xstar-cpp OS processes (not threads; default: 1)\n"
        "  --workers N, -j N    compatibility aliases for --processes\n"
        "  --save               compatibility flag; work/products are preserved by default\n"
        "  --cleanup-work       explicitly remove xstar2xspec-work/ only after full success\n"
        "  --restart            reuse completed per-job spectra/STEP logs in work directory\n"
        "  --verbose            replay child output while assembling deterministic root log\n"
        "  --initable-bin PATH  override xstar-xspec-initable executable\n"
        "  --xstar-cpp PATH     override xstar-cpp executable\n"
        "  --table-bin PATH     override xstar-xspec-table executable\n"
        "  --version            print package version\n"
        "  --help, -h           show this help\n\n"
        "Trailing key=value arguments override values loaded from --input.\n"
        "If --data-dir is omitted, each xstar-cpp job performs its normal data discovery\n"
        "(XSTAR_DATA, then $HEADAS/refdata, then legacy fallbacks).\n"
        "Each process is a separate xstar-cpp OS process; the OS schedules processes on available logical CPUs.\n"
        "Parallel completion order never controls scientific/table placement; loopcontrol does.\n",
        argv0, argv0);
}

fs::path sibling(const char *argv0, const char *name) {
    std::error_code ec;
    fs::path self = fs::absolute(fs::path(argv0), ec);
    if (ec) self = fs::path(argv0);
    return self.parent_path() / xstar_platform::executable_filename(name);
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
#if defined(_WIN32)
    const fs::path capture = cwd / (".xstar-capture-" + std::to_string(xstar_process::current_process_id()) + ".log");
    const auto pid = xstar_process::spawn_program(args, cwd, capture);
    if (pid < 0) throw std::runtime_error("CreateProcessW failed");
    int status=0; while (xstar_process::wait_process(pid,&status,0)<0) if(errno!=EINTR) return 127;
    std::ifstream in(capture,std::ios::binary); char buffer[8192];
    while(in){ in.read(buffer,sizeof(buffer)); auto n=in.gcount(); if(n>0){log.write(buffer,n); if(verbose) std::cout.write(buffer,n);} }
    log.flush(); if(verbose) std::cout.flush(); std::error_code ec; fs::remove(capture,ec);
    return xstar_process::decode_wait_status(status);
#else
    int pipefd[2];
    if (::pipe(pipefd) != 0) throw std::runtime_error("pipe failed: " + std::string(std::strerror(errno)));
    const xstar_process::process_id pid = xstar_process::fork_process();
    if (pid < 0) { ::close(pipefd[0]); ::close(pipefd[1]); throw std::runtime_error("fork failed: " + std::string(std::strerror(errno))); }
    if (pid == 0) {
        ::close(pipefd[0]); if (!cwd.empty() && ::chdir(cwd.c_str()) != 0) xstar_process::exit_child(126);
        ::dup2(pipefd[1], STDOUT_FILENO); ::dup2(pipefd[1], STDERR_FILENO); ::close(pipefd[1]);
        std::vector<std::string> storage=args; std::vector<char*> av; for(auto& item:storage) av.push_back(item.data()); av.push_back(nullptr);
        xstar_process::exec_program(storage[0].c_str(),av.data(),storage[0].find('/')==std::string::npos); xstar_process::exit_child(127);
    }
    ::close(pipefd[1]); char buffer[8192]; for(;;){const ssize_t n=::read(pipefd[0],buffer,sizeof(buffer)); if(n>0){log.write(buffer,n);log.flush();if(verbose){std::cout.write(buffer,n);std::cout.flush();}} else if(n==0)break; else if(errno!=EINTR)break;} ::close(pipefd[0]);
    int status=0; while(xstar_process::wait_process(pid,&status,0)<0) if(errno!=EINTR)return 127; return xstar_process::decode_wait_status(status);
#endif
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

std::size_t parse_positive_size(const std::string &value, const char *flag) {
    if (value.empty()) throw std::runtime_error(std::string("empty value for ") + flag);
    char *end = nullptr;
    errno = 0;
    const unsigned long long n = std::strtoull(value.c_str(), &end, 10);
    if (errno != 0 || end == value.c_str() || *end != '\0' || n == 0)
        throw std::runtime_error(std::string(flag) + " requires a positive integer");
    return static_cast<std::size_t>(n);
}

std::size_t extract_loopcontrol(const std::vector<std::string> &job) {
    constexpr const char *prefix = "loopcontrol=";
    for (const auto &arg : job) {
        if (arg.rfind(prefix, 0) == 0)
            return parse_positive_size(arg.substr(std::strlen(prefix)), "loopcontrol");
    }
    throw std::runtime_error("generated job has no loopcontrol parameter");
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
        else if (arg == "--processes" || arg == "--workers" || arg == "-j") opt.processes = parse_positive_size(need(arg.c_str()), arg.c_str());
        else if (arg == "--initable-bin") opt.initable_bin = need("--initable-bin");
        else if (arg == "--xstar-cpp") opt.xstar_cpp_bin = need("--xstar-cpp");
        else if (arg == "--table-bin") opt.table_bin = need("--table-bin");
        else if (arg == "--save") opt.save = true;
        else if (arg == "--cleanup-work") opt.cleanup_work = true;
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

xstar_process::process_id spawn_job(const std::vector<std::string> &args, const fs::path &cwd, const fs::path &stdout_log) {
    if (args.empty()) throw std::runtime_error("cannot spawn empty job command");
#if defined(_WIN32)
    const auto pid=xstar_process::spawn_program(args,cwd,stdout_log);
    if(pid<0) throw std::runtime_error("CreateProcessW failed");
    return pid;
#else
    const xstar_process::process_id pid=xstar_process::fork_process(); if(pid<0) throw std::runtime_error("fork failed: "+std::string(std::strerror(errno)));
    if(pid==0){ if(!cwd.empty()&&::chdir(cwd.c_str())!=0)xstar_process::exit_child(126); const int fd=::open(stdout_log.c_str(),O_WRONLY|O_CREAT|O_TRUNC,0666); if(fd<0)xstar_process::exit_child(125); ::dup2(fd,STDOUT_FILENO);::dup2(fd,STDERR_FILENO);::close(fd); std::vector<std::string> storage=args; std::vector<char*> av; for(auto& item:storage)av.push_back(item.data());av.push_back(nullptr); xstar_process::exec_program(storage[0].c_str(),av.data(),storage[0].find('/')==std::string::npos);xstar_process::exit_child(127);} return pid;
#endif
}

int decode_wait_status(int status) {
    return xstar_process::decode_wait_status(status);
}

void terminate_active(std::map<xstar_process::process_id, ActiveJob> &active) {
    for (const auto &entry : active) xstar_process::terminate_process(entry.first);
    for (const auto &entry : active) {
        int status = 0;
        while (xstar_process::wait_process(entry.first, &status, 0) < 0 && errno == EINTR) {}
    }
    active.clear();
}

void append_file(std::ofstream &out, const fs::path &path, bool echo) {
    std::ifstream in(path, std::ios::binary);
    if (!in) throw std::runtime_error("cannot read job stdout log: " + path.string());
    char buffer[8192];
    while (in) {
        in.read(buffer, sizeof(buffer));
        const std::streamsize n = in.gcount();
        if (n > 0) {
            out.write(buffer, n);
            if (echo) std::cout.write(buffer, n);
        }
    }
    out.flush();
    if (echo) std::cout.flush();
}

std::string join_indices(const std::vector<std::size_t> &values) {
    if (values.empty()) return "NONE";
    std::ostringstream out;
    for (std::size_t i = 0; i < values.size(); ++i) {
        if (i) out << ',';
        out << values[i];
    }
    return out.str();
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
        const fs::path work_dir = opt.output_dir / "xstar2xspec-work";
        const fs::path jobs_dir = work_dir / "jobs";
        fs::create_directories(jobs_dir);

        // 0.6.85.1: never delete pre-existing XSTAR/XSPEC products automatically.
        // A failed rerun must leave prior and partially-written products available
        // for forensic inspection. Current-run success/failure is communicated by
        // return status and logs, not by destructive cleanup.

        std::ofstream log(opt.output_dir / "xstar2xspec.log", std::ios::out | std::ios::trunc);
        if (!log) throw std::runtime_error("cannot create xstar2xspec.log");
        std::ofstream scheduler(opt.output_dir / "xstar2xspec_scheduler.log", std::ios::out | std::ios::trunc);
        if (!scheduler) throw std::runtime_error("cannot create xstar2xspec_scheduler.log");
        log << "xstar_tools " << kPackageVersion << " parallel native XSTAR2XSPEC\n";
        for (const char *name : {"xout_ain.fits", "xout_aout.fits", "xout_mtable.fits", "xout_etable.fits", "xout_step.log"}) {
            if (fs::is_regular_file(opt.output_dir / name))
                log << "[preserve] pre_existing_root_product=" << name << "\n";
        }

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

        std::vector<fs::path> spectra(lines.size());
        std::vector<fs::path> steps(lines.size());
        std::vector<fs::path> stdout_logs(lines.size());
        std::vector<fs::path> success_markers(lines.size());
        std::vector<std::vector<std::string>> commands(lines.size());
        std::vector<std::size_t> pending;
        std::size_t reused = 0;

        for (std::size_t i = 0; i < lines.size(); ++i) {
            const std::size_t job_index = i + 1;
            const fs::path job_dir = jobs_dir / job_name(job_index);
            fs::create_directories(job_dir);
            spectra[i] = job_dir / "xout_spect1.fits";
            steps[i] = job_dir / "xout_step.log";
            stdout_logs[i] = job_dir / "xstar-cpp.stdout.log";
            success_markers[i] = job_dir / "xstar-cpp.success";

            std::vector<std::string> job = shell_split(lines[i]);
            if (job.empty() || job[0] != "xstar-cpp") throw std::runtime_error("native parallel pipeline requires cpp xstinitable plan");
            const std::size_t loopcontrol = extract_loopcontrol(job);
            if (loopcontrol != job_index)
                throw std::runtime_error("xstinitable plan order/loopcontrol mismatch at job " + std::to_string(job_index));
            job[0] = opt.xstar_cpp_bin.string();
            job.insert(job.begin() + 1, {"--output", job_dir.string()});
            commands[i] = std::move(job);

            const bool complete = fs::is_regular_file(spectra[i]) && fs::is_regular_file(steps[i]) &&
                fs::is_regular_file(success_markers[i]);
            if (opt.restart && complete) {
                ++reused;
                scheduler << "reuse loopcontrol=" << job_index << "\n";
            } else {
                pending.push_back(i);
            }
        }

        const std::size_t effective_processes = pending.empty() ? 0 : std::min(opt.processes, pending.size());
        scheduler << "processes_requested=" << opt.processes << "\n";
        scheduler << "processes_effective=" << effective_processes << "\n";
        scheduler << "workers_requested=" << opt.processes << "\n";  // legacy telemetry alias
        scheduler << "workers_effective=" << effective_processes << "\n";  // legacy telemetry alias
        scheduler << "jobs_total=" << lines.size() << "\n";
        scheduler << "jobs_pending=" << pending.size() << "\n";
        scheduler << "jobs_reused=" << reused << "\n";

        std::map<xstar_process::process_id, ActiveJob> active;
        std::vector<std::size_t> completion_order;
        std::size_t next = 0;
        std::size_t max_active = 0;
        try {
            while (next < pending.size() || !active.empty()) {
                while (next < pending.size() && active.size() < effective_processes) {
                    const std::size_t i = pending[next++];
                    const std::size_t job_index = i + 1;
                    // Invalidate only the non-product success marker. Any XSTAR
                    // products from an earlier/failed attempt are intentionally
                    // retained until the new solver overwrites them.
                    std::error_code marker_ec;
                    fs::remove(success_markers[i], marker_ec);
                    const xstar_process::process_id pid = spawn_job(commands[i], invocation_dir, stdout_logs[i]);
                    active.emplace(pid, ActiveJob{job_index, pid, stdout_logs[i]});
                    max_active = std::max(max_active, active.size());
                    scheduler << "launch loopcontrol=" << job_index << " pid=" << pid << "\n";
                    scheduler.flush();
                }
                if (active.empty()) continue;
                int status = 0;
                xstar_process::process_id pid;
                do { pid = xstar_process::wait_process(-1, &status, 0); } while (pid < 0 && errno == EINTR);
                if (pid < 0) throw std::runtime_error("waitpid failed: " + std::string(std::strerror(errno)));
                const auto it = active.find(pid);
                if (it == active.end()) throw std::runtime_error("waitpid returned unknown child");
                const std::size_t job_index = it->second.index;
                const int rc = decode_wait_status(status);
                scheduler << "complete loopcontrol=" << job_index << " pid=" << pid << " return_code=" << rc << "\n";
                scheduler.flush();
                active.erase(it);
                if (rc != 0) {
                    terminate_active(active);
                    throw std::runtime_error("xstar-cpp job " + std::to_string(job_index) + " failed with return code " + std::to_string(rc));
                }
                require_regular(spectra[job_index - 1], "job xout_spect1.fits");
                require_regular(steps[job_index - 1], "job xout_step.log");
                {
                    std::ofstream success(success_markers[job_index - 1], std::ios::out | std::ios::trunc);
                    if (!success) throw std::runtime_error("cannot write xstar-cpp success marker");
                    success << "package=" << kPackageVersion << "\n"
                            << "loopcontrol=" << job_index << "\n"
                            << "return_code=0\n";
                }
                completion_order.push_back(job_index);
            }
        } catch (...) {
            terminate_active(active);
            throw;
        }

        log << "[scheduler] processes_requested=" << opt.processes
            << " processes_effective=" << effective_processes
            << " max_active=" << max_active
            << " executed=" << pending.size()
            << " reused=" << reused << "\n";
        log << "[scheduler] completion_order=" << join_indices(completion_order) << "\n";
        for (std::size_t i = 0; i < lines.size(); ++i) {
            log << "[job " << (i + 1) << "/" << lines.size() << "] canonical_output\n";
            if (fs::is_regular_file(stdout_logs[i])) append_file(log, stdout_logs[i], opt.verbose);
            else if (opt.restart) log << "[job " << (i + 1) << "] restart_reuse (no stdout replay)\n";
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

        if (opt.cleanup_work) {
            std::error_code ec;
            fs::remove_all(work_dir, ec);
            if (ec) log << "[cleanup] warning=" << ec.message() << "\n";
            else log << "[cleanup] explicit --cleanup-work removed xstar2xspec-work after success\n";
        } else {
            log << "[preserve] xstar2xspec-work retained; XSTAR products are never auto-deleted\n";
        }

        std::cout << "XSTAR_XSPEC_06851_JOBS=" << lines.size() << "\n";
        std::cout << "XSTAR_XSPEC_0687_PROCESSES_REQUESTED=" << opt.processes << "\n";
        std::cout << "XSTAR_XSPEC_0687_PROCESSES_EFFECTIVE=" << effective_processes << "\n";
        std::cout << "XSTAR_XSPEC_06851_WORKERS_REQUESTED=" << opt.processes << "\n";  // legacy marker
        std::cout << "XSTAR_XSPEC_06851_WORKERS_EFFECTIVE=" << effective_processes << "\n";  // legacy marker
        std::cout << "XSTAR_XSPEC_06851_MAX_ACTIVE=" << max_active << "\n";
        std::cout << "XSTAR_XSPEC_06851_EXECUTED=" << pending.size() << "\n";
        std::cout << "XSTAR_XSPEC_06851_REUSED=" << reused << "\n";
        std::cout << "XSTAR_XSPEC_06851_COMPLETION_ORDER=" << join_indices(completion_order) << "\n";
        std::cout << "XSTAR_XSPEC_06851_LOOPCONTROL_FIRST=1\n";
        std::cout << "XSTAR_XSPEC_06851_LOOPCONTROL_LAST=" << lines.size() << "\n";
        std::cout << "XSTAR_XSPEC_06851_TABLES=4\n";
        std::cout << "XSTAR_XSPEC_06851_WORKDIR=xstar2xspec-work\n";
        std::cout << "XSTAR_XSPEC_0687_RESULT=ACCEPT\n";
        std::cout << "XSTAR_XSPEC_06851_RESULT=ACCEPT\n";  // legacy marker
        return 0;
    } catch (const std::exception &exc) {
        std::fprintf(stderr, "xstar-xspec: %s\n", exc.what());
        return 1;
    }
}

// Historical predecessor marker: kPackageVersion = "0.6.89.1.1"
