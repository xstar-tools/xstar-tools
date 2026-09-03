// True MPI native XSTAR2XSPEC orchestration for xstar_tools 0.6.88.6.1.
//
// Rank 0 creates the canonical xstinitable plan.  All ranks then claim grid
// jobs from an MPI-3 RMA counter and execute exactly one xstar-cpp child at a
// time.  The work tree is shared and job identity is always loopcontrol based.
// Rank/completion order never controls STEP concatenation, PARAMVAL placement,
// spectrum ordering, or final XSPEC table rows.  Rank 0 performs the final
// canonical gather and xstar-xspec-table invocation after all jobs succeed.
//
// The executable intentionally contains no XSTAR scientific arithmetic.  It
// composes the already-qualified xstar-xspec-initable, xstar-cpp, and
// xstar-xspec-table executables.

#include "xstar_process.hpp"

#include <mpi.h>

#include <algorithm>
#include <cerrno>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <filesystem>
#include <fcntl.h>
#include <fstream>
#include <iostream>
#include <sstream>
#include <stdexcept>
#include <string>
#include <sys/types.h>
#include <sys/wait.h>
#include <unistd.h>
#include <vector>
#include <signal.h>

namespace fs = std::filesystem;

namespace {

// Historical qualification compatibility marker: kPackageVersion = "0.6.88.6.1.2.1"
constexpr const char *kPackageVersion = "0.6.89";
// Historical qualification compatibility marker: kPackageVersion = "0.6.88.3.2"
// Historical qualification compatibility marker: kPackageVersion = "0.6.88.3.1"
// Historical qualification compatibility marker: kPackageVersion = "0.6.88.3"
constexpr int kQueueNextSlot = 0;
constexpr int kQueueFailed = 1;
constexpr int kQueueInts = 2;

struct Options {
    fs::path input_file;
    fs::path data_dir;
    fs::path output_dir{"."};
    fs::path initable_bin;
    fs::path xstar_cpp_bin;
    fs::path table_bin;
    bool save = false;
    bool cleanup_work = false;
    bool restart = false;
    bool verbose = false;
    bool show_help = false;
    bool show_version = false;
    std::vector<std::string> overrides;
};

void usage(const char *argv0) {
    std::fprintf(stderr,
        "Usage:\n"
        "  mpirun -np N %s --input xstinitable.par [--data-dir DIR] --output-dir DIR [options] [key=value ...]\n"
        "  mpirun -np N %s --output-dir DIR [options] key=value [key=value ...]\n\n"
        "True-MPI native XSTAR2XSPEC pipeline:\n"
        "  rank 0 xstar-xspec-initable -> MPI-distributed xstar-cpp grid -> rank 0 xstar-xspec-table\n\n"
        "MPI model:\n"
        "  - MPI rank count is selected by mpirun/mpiexec -np N.\n"
        "  - Each rank executes at most one xstar-cpp process at a time.\n"
        "  - There is no --processes option; MPI concurrency is selected by mpirun/mpiexec -np N.\n"
        "  - Rank 0 also executes XSTAR jobs, then owns final canonical gather/table publication.\n"
        "  - The executable/output/data paths must be visible on every participating node.\n\n"
        "Options:\n"
        "  --input PATH          HEASoft/IRAF-style xstinitable.par\n"
        "  --data-dir DIR       explicit XSTAR atomic-data directory (optional)\n"
        "  --output-dir DIR     final XSTAR2XSPEC output directory\n"
        "  --save               compatibility flag; work/products are preserved by default\n"
        "  --cleanup-work       remove xstar2xspec-work/ only after full success\n"
        "  --restart            reuse jobs with spectrum + STEP + xstar-cpp.success\n"
        "  --verbose            replay child output in canonical root-log order\n"
        "  --initable-bin PATH  override xstar-xspec-initable executable\n"
        "  --xstar-cpp PATH     override xstar-cpp executable\n"
        "  --table-bin PATH     override xstar-xspec-table executable\n"
        "  --version            print package version\n"
        "  --help, -h           show this help\n\n"
        "Trailing key=value arguments override values loaded from --input.\n"
        "If --data-dir is omitted, every xstar-cpp process performs the normal\n"
        "atomic-data discovery (explicit environment, XSTAR_DATA, $HEADAS/refdata,\n"
        "XSTAR_HOME, then executable/package/current-directory fallbacks).\n",
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

int decode_wait_status(int status) {
    return xstar_process::decode_wait_status(status);
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
    return decode_wait_status(status);
}

xstar_process::process_id spawn_job(const std::vector<std::string> &args, const fs::path &cwd,
                const fs::path &stdout_log) {
    if (args.empty()) throw std::runtime_error("empty xstar-cpp command");
    const xstar_process::process_id pid = xstar_process::fork_process();
    if (pid < 0) throw std::runtime_error("fork failed: " + std::string(std::strerror(errno)));
    if (pid == 0) {
        if (!cwd.empty() && ::chdir(cwd.c_str()) != 0) xstar_process::exit_child(126);
        const int fd = ::open(stdout_log.c_str(), O_WRONLY | O_CREAT | O_TRUNC, 0666);
        if (fd < 0) xstar_process::exit_child(126);
        ::dup2(fd, STDOUT_FILENO);
        ::dup2(fd, STDERR_FILENO);
        ::close(fd);
        std::vector<std::string> storage = args;
        std::vector<char *> av;
        av.reserve(storage.size() + 1);
        for (auto &item : storage) av.push_back(item.data());
        av.push_back(nullptr);
        xstar_process::exec_program(storage[0].c_str(), av.data(), storage[0].find('/') == std::string::npos);
        xstar_process::exit_child(127);
    }
    return pid;
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

void append_file(std::ofstream &out, const fs::path &path, bool also_stdout) {
    std::ifstream in(path, std::ios::binary);
    if (!in) return;
    char buffer[8192];
    while (in) {
        in.read(buffer, sizeof(buffer));
        const std::streamsize n = in.gcount();
        if (n <= 0) break;
        out.write(buffer, n);
        if (also_stdout) std::cout.write(buffer, n);
    }
    if (also_stdout) std::cout.flush();
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

void require_regular(const fs::path &path, const std::string &what) {
    if (!fs::is_regular_file(path)) throw std::runtime_error("missing " + what + ": " + path.string());
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
        else if (arg == "--processes" || arg == "--workers" || arg == "-j")
            throw std::runtime_error("xstar-xspec-mpi does not use local process-count options; select MPI ranks with mpirun/mpiexec -np N");
        else if (arg == "--initable-bin") opt.initable_bin = need("--initable-bin");
        else if (arg == "--xstar-cpp") opt.xstar_cpp_bin = need("--xstar-cpp");
        else if (arg == "--table-bin") opt.table_bin = need("--table-bin");
        else if (arg == "--save") opt.save = true;
        else if (arg == "--cleanup-work") opt.cleanup_work = true;
        else if (arg == "--restart") opt.restart = true;
        else if (arg == "--verbose") opt.verbose = true;
        else if (arg == "--version") opt.show_version = true;
        else if (arg == "--help" || arg == "-h") opt.show_help = true;
        else if (!arg.empty() && arg[0] == '-') throw std::runtime_error("unknown option: " + arg);
        else if (arg.find('=') != std::string::npos) opt.overrides.push_back(arg);
        else throw std::runtime_error("expected xstinitable key=value override, got: " + arg);
    }
    if (!opt.show_help && !opt.show_version && opt.input_file.empty() && opt.overrides.empty())
        throw std::runtime_error("provide --input or xstinitable key=value parameters");
    return opt;
}

void make_absolute(fs::path &path) {
    if (path.empty()) return;
    std::error_code ec;
    fs::path abs = fs::absolute(path, ec);
    if (!ec) path = abs;
}

int read_failed(MPI_Win win) {
    int failed = 0;
    MPI_Get(&failed, 1, MPI_INT, 0, kQueueFailed, 1, MPI_INT, win);
    MPI_Win_flush(0, win);
    return failed;
}

void set_failed(MPI_Win win) {
    const int one = 1;
    MPI_Accumulate(&one, 1, MPI_INT, 0, kQueueFailed, 1, MPI_INT, MPI_REPLACE, win);
    MPI_Win_flush(0, win);
}

int claim_slot(MPI_Win win) {
    const int one = 1;
    int slot = 0;
    MPI_Fetch_and_op(&one, &slot, MPI_INT, 0, kQueueNextSlot, MPI_SUM, win);
    MPI_Win_flush(0, win);
    return slot;
}

void terminate_child(xstar_process::process_id pid) {
    if (pid <= 0) return;
    xstar_process::terminate_process(pid);
    for (int i = 0; i < 20; ++i) {
        int status = 0;
        const xstar_process::process_id got = xstar_process::wait_process(pid, &status, xstar_process::wait_nohang());
        if (got == pid || (got < 0 && errno == ECHILD)) return;
        ::usleep(50000);
    }
    xstar_process::force_kill_process(pid);
    int status = 0;
    while (xstar_process::wait_process(pid, &status, 0) < 0 && errno == EINTR) {}
}

int run_mpi_job(const std::vector<std::string> &command,
                const fs::path &cwd,
                const fs::path &stdout_log,
                const fs::path &spectrum,
                const fs::path &step,
                const fs::path &success_marker,
                std::size_t job_index,
                MPI_Win win) {
    std::error_code ec;
    fs::remove(success_marker, ec);
    const xstar_process::process_id pid = spawn_job(command, cwd, stdout_log);
    int rc = 127;
    for (;;) {
        int status = 0;
        const xstar_process::process_id got = xstar_process::wait_process(pid, &status, xstar_process::wait_nohang());
        if (got == pid) { rc = decode_wait_status(status); break; }
        if (got < 0 && errno != EINTR) { rc = 127; break; }
        if (read_failed(win)) {
            terminate_child(pid);
            return 125;
        }
        ::usleep(100000);
    }
    if (rc != 0) return rc;
    try {
        require_regular(spectrum, "job xout_spect1.fits");
        require_regular(step, "job xout_step.log");
        std::ofstream success(success_marker, std::ios::out | std::ios::trunc);
        if (!success) throw std::runtime_error("cannot write xstar-cpp success marker");
        success << "package=" << kPackageVersion << "\n"
                << "loopcontrol=" << job_index << "\n"
                << "return_code=0\n";
    } catch (const std::exception &exc) {
        std::ofstream out(stdout_log, std::ios::out | std::ios::app);
        out << "xstar-xspec-mpi validation failure: " << exc.what() << "\n";
        return 90;
    }
    return 0;
}

std::string join_indices(std::vector<int> values) {
    if (values.empty()) return "NONE";
    std::sort(values.begin(), values.end());
    std::ostringstream out;
    for (std::size_t i = 0; i < values.size(); ++i) {
        if (i) out << ',';
        out << values[i];
    }
    return out.str();
}

}  // namespace

int main(int argc, char **argv) {
    MPI_Init(&argc, &argv);
    int rank = 0;
    int world = 1;
    MPI_Comm_rank(MPI_COMM_WORLD, &rank);
    MPI_Comm_size(MPI_COMM_WORLD, &world);

    int final_rc = 1;
    try {
        Options opt = parse_options(argc, argv);
        if (opt.show_version) {
            if (rank == 0) std::cout << "xstar-xspec-mpi package version " << kPackageVersion << "\n";
            MPI_Finalize();
            return 0;
        }
        if (opt.show_help) {
            if (rank == 0) usage(argv[0]);
            MPI_Finalize();
            return 0;
        }

        const fs::path invocation_dir = fs::current_path();
        if (opt.initable_bin.empty()) opt.initable_bin = sibling(argv[0], "xstar-xspec-initable");
        if (opt.xstar_cpp_bin.empty()) opt.xstar_cpp_bin = sibling(argv[0], "xstar-cpp");
        if (opt.table_bin.empty()) opt.table_bin = sibling(argv[0], "xstar-xspec-table");
        make_absolute(opt.input_file);
        make_absolute(opt.data_dir);
        make_absolute(opt.output_dir);
        make_absolute(opt.initable_bin);
        make_absolute(opt.xstar_cpp_bin);
        make_absolute(opt.table_bin);

        int root_plan_ok = 1;
        std::string root_plan_error;
        if (rank == 0) {
            try {
                fs::create_directories(opt.output_dir);
                const fs::path work_dir = opt.output_dir / "xstar2xspec-work";
                fs::create_directories(work_dir / "jobs");
                std::ofstream log(opt.output_dir / "xstar2xspec-mpi.log", std::ios::out | std::ios::trunc);
                if (!log) throw std::runtime_error("cannot create xstar2xspec-mpi.log");
                log << "xstar_tools " << kPackageVersion << " true MPI native XSTAR2XSPEC\n";
                log << "[mpi] ranks=" << world << "\n";
                for (const char *name : {"xout_ain.fits", "xout_aout.fits", "xout_mtable.fits", "xout_etable.fits", "xout_step.log"}) {
                    if (fs::is_regular_file(opt.output_dir / name))
                        log << "[preserve] pre_existing_root_product=" << name << "\n";
                }
                std::vector<std::string> planner{opt.initable_bin.string(), "--xstar", "cpp", "--output-dir", opt.output_dir.string()};
                if (!opt.input_file.empty()) { planner.push_back("--input"); planner.push_back(opt.input_file.string()); }
                if (!opt.data_dir.empty()) { planner.push_back("--data-dir"); planner.push_back(opt.data_dir.string()); }
                planner.insert(planner.end(), opt.overrides.begin(), opt.overrides.end());
                log << "[planner] " << opt.initable_bin << "\n";
                if (run_capture(planner, invocation_dir, log, opt.verbose) != 0)
                    throw std::runtime_error("xstar-xspec-initable failed");
                require_regular(opt.output_dir / "xstinitable.lis", "xstinitable.lis");
                require_regular(opt.output_dir / "xstinitable.fits", "xstinitable.fits");
            } catch (const std::exception &exc) {
                root_plan_ok = 0;
                root_plan_error = exc.what();
            }
        }
        MPI_Bcast(&root_plan_ok, 1, MPI_INT, 0, MPI_COMM_WORLD);
        if (!root_plan_ok) {
            if (rank == 0) std::fprintf(stderr, "xstar-xspec-mpi: %s\n", root_plan_error.c_str());
            MPI_Finalize();
            return 1;
        }
        MPI_Barrier(MPI_COMM_WORLD);

        std::vector<std::string> lines;
        int local_plan_read_ok = 1;
        std::string local_plan_error;
        try {
            lines = load_lines(opt.output_dir / "xstinitable.lis");
        } catch (const std::exception &exc) {
            local_plan_read_ok = 0;
            local_plan_error = exc.what();
        }
        int all_plan_read_ok = 0;
        MPI_Allreduce(&local_plan_read_ok, &all_plan_read_ok, 1, MPI_INT, MPI_MIN, MPI_COMM_WORLD);
        if (!all_plan_read_ok) {
            if (!local_plan_read_ok)
                std::fprintf(stderr, "xstar-xspec-mpi rank %d: %s (shared filesystem is required)\n", rank, local_plan_error.c_str());
            MPI_Finalize();
            return 1;
        }
        const int local_job_count = static_cast<int>(lines.size());
        int min_job_count = 0, max_job_count = 0;
        MPI_Allreduce(&local_job_count, &min_job_count, 1, MPI_INT, MPI_MIN, MPI_COMM_WORLD);
        MPI_Allreduce(&local_job_count, &max_job_count, 1, MPI_INT, MPI_MAX, MPI_COMM_WORLD);
        if (min_job_count != max_job_count) {
            if (rank == 0) std::fprintf(stderr, "xstar-xspec-mpi: ranks observed inconsistent xstinitable plans\n");
            MPI_Finalize();
            return 1;
        }

        const fs::path jobs_dir = opt.output_dir / "xstar2xspec-work" / "jobs";
        std::vector<fs::path> spectra(lines.size());
        std::vector<fs::path> steps(lines.size());
        std::vector<fs::path> stdout_logs(lines.size());
        std::vector<fs::path> success_markers(lines.size());
        std::vector<std::vector<std::string>> commands(lines.size());
        int local_commands_ok = 1;
        std::string local_commands_error;
        try {
            for (std::size_t i = 0; i < lines.size(); ++i) {
                const std::size_t job_index = i + 1;
                const fs::path job_dir = jobs_dir / job_name(job_index);
                if (rank == 0) fs::create_directories(job_dir);
                spectra[i] = job_dir / "xout_spect1.fits";
                steps[i] = job_dir / "xout_step.log";
                stdout_logs[i] = job_dir / "xstar-cpp.stdout.log";
                success_markers[i] = job_dir / "xstar-cpp.success";
                std::vector<std::string> job = shell_split(lines[i]);
                if (job.empty() || job[0] != "xstar-cpp")
                    throw std::runtime_error("native MPI pipeline requires cpp xstinitable plan");
                const std::size_t loopcontrol = extract_loopcontrol(job);
                if (loopcontrol != job_index)
                    throw std::runtime_error("xstinitable plan order/loopcontrol mismatch at job " + std::to_string(job_index));
                job[0] = opt.xstar_cpp_bin.string();
                job.insert(job.begin() + 1, {"--output", job_dir.string()});
                commands[i] = std::move(job);
            }
        } catch (const std::exception &exc) {
            local_commands_ok = 0;
            local_commands_error = exc.what();
        }
        MPI_Barrier(MPI_COMM_WORLD);
        int all_commands_ok = 0;
        MPI_Allreduce(&local_commands_ok, &all_commands_ok, 1, MPI_INT, MPI_MIN, MPI_COMM_WORLD);
        if (!all_commands_ok) {
            if (!local_commands_ok) std::fprintf(stderr, "xstar-xspec-mpi rank %d: %s\n", rank, local_commands_error.c_str());
            MPI_Finalize();
            return 1;
        }

        std::vector<int> pending;
        int reused = 0;
        if (rank == 0) {
            for (std::size_t i = 0; i < lines.size(); ++i) {
                const bool complete = fs::is_regular_file(spectra[i]) && fs::is_regular_file(steps[i]) &&
                    fs::is_regular_file(success_markers[i]);
                if (opt.restart && complete) ++reused;
                else pending.push_back(static_cast<int>(i));
            }
        }
        int pending_count = rank == 0 ? static_cast<int>(pending.size()) : 0;
        MPI_Bcast(&pending_count, 1, MPI_INT, 0, MPI_COMM_WORLD);
        if (rank != 0) pending.resize(static_cast<std::size_t>(pending_count));
        if (pending_count > 0) MPI_Bcast(pending.data(), pending_count, MPI_INT, 0, MPI_COMM_WORLD);
        MPI_Bcast(&reused, 1, MPI_INT, 0, MPI_COMM_WORLD);

        char processor[MPI_MAX_PROCESSOR_NAME];
        int processor_len = 0;
        MPI_Get_processor_name(processor, &processor_len);
        char rank_log_name[64];
        std::snprintf(rank_log_name, sizeof(rank_log_name), "xstar2xspec-mpi-rank-%06d.log", rank);
        std::ofstream rank_log(opt.output_dir / rank_log_name, std::ios::out | std::ios::trunc);
        int local_log_ok = rank_log ? 1 : 0;
        int all_log_ok = 0;
        MPI_Allreduce(&local_log_ok, &all_log_ok, 1, MPI_INT, MPI_MIN, MPI_COMM_WORLD);
        if (!all_log_ok) {
            if (rank == 0) std::fprintf(stderr, "xstar-xspec-mpi: one or more ranks cannot create output logs; shared writable output is required\n");
            MPI_Finalize();
            return 1;
        }
        rank_log << "rank=" << rank << " world=" << world << " processor=" << std::string(processor, processor_len) << "\n";

        int *queue_state = nullptr;
        MPI_Win queue_win;
        const MPI_Aint queue_bytes = rank == 0 ? static_cast<MPI_Aint>(kQueueInts * sizeof(int)) : 0;
        MPI_Win_allocate(queue_bytes, sizeof(int), MPI_INFO_NULL, MPI_COMM_WORLD, &queue_state, &queue_win);
        if (rank == 0) {
            queue_state[kQueueNextSlot] = 0;
            queue_state[kQueueFailed] = 0;
            MPI_Win_sync(queue_win);
        }
        MPI_Barrier(MPI_COMM_WORLD);
        MPI_Win_lock_all(0, queue_win);

        std::vector<int> local_completed;
        int local_attempted = 0;
        int local_failure_rc = 0;
        for (;;) {
            if (read_failed(queue_win)) break;
            const int slot = claim_slot(queue_win);
            if (slot < 0 || slot >= pending_count) break;
            if (read_failed(queue_win)) break;
            const int job_zero = pending[static_cast<std::size_t>(slot)];
            const std::size_t job_index = static_cast<std::size_t>(job_zero + 1);
            rank_log << "claim loopcontrol=" << job_index << "\n";
            rank_log.flush();
            ++local_attempted;
            const int rc = run_mpi_job(commands[static_cast<std::size_t>(job_zero)], invocation_dir,
                                       stdout_logs[static_cast<std::size_t>(job_zero)],
                                       spectra[static_cast<std::size_t>(job_zero)],
                                       steps[static_cast<std::size_t>(job_zero)],
                                       success_markers[static_cast<std::size_t>(job_zero)],
                                       job_index, queue_win);
            rank_log << "complete loopcontrol=" << job_index << " return_code=" << rc << "\n";
            rank_log.flush();
            if (rc != 0) {
                local_failure_rc = rc;
                set_failed(queue_win);
                break;
            }
            local_completed.push_back(static_cast<int>(job_index));
        }
        const int observed_failed = read_failed(queue_win);
        MPI_Win_unlock_all(queue_win);
        MPI_Win_free(&queue_win);
        const int local_failed = local_failure_rc != 0 ? 1 : 0;
        int global_failed = 0;
        MPI_Allreduce(&local_failed, &global_failed, 1, MPI_INT, MPI_MAX, MPI_COMM_WORLD);
        rank_log << "attempted=" << local_attempted << " completed=" << local_completed.size()
                 << " local_failure_rc=" << local_failure_rc << " observed_failed=" << observed_failed
                 << " global_failed=" << global_failed << "\n";
        rank_log.close();

        int total_attempted = 0;
        int local_completed_count = static_cast<int>(local_completed.size());
        std::vector<int> completed_counts;
        if (rank == 0) completed_counts.resize(static_cast<std::size_t>(world));
        MPI_Reduce(&local_attempted, &total_attempted, 1, MPI_INT, MPI_SUM, 0, MPI_COMM_WORLD);
        MPI_Gather(&local_completed_count, 1, MPI_INT,
                   rank == 0 ? completed_counts.data() : nullptr, 1, MPI_INT, 0, MPI_COMM_WORLD);
        std::vector<int> displacements;
        std::vector<int> all_completed;
        if (rank == 0) {
            displacements.resize(static_cast<std::size_t>(world));
            int total = 0;
            for (int r = 0; r < world; ++r) {
                displacements[static_cast<std::size_t>(r)] = total;
                total += completed_counts[static_cast<std::size_t>(r)];
            }
            all_completed.resize(static_cast<std::size_t>(total));
        }
        MPI_Gatherv(local_completed.empty() ? nullptr : local_completed.data(), local_completed_count, MPI_INT,
                    rank == 0 && !all_completed.empty() ? all_completed.data() : nullptr,
                    rank == 0 ? completed_counts.data() : nullptr,
                    rank == 0 ? displacements.data() : nullptr,
                    MPI_INT, 0, MPI_COMM_WORLD);
        MPI_Barrier(MPI_COMM_WORLD);

        int root_final_ok = global_failed ? 0 : 1;
        std::string root_final_error;
        if (rank == 0) {
            try {
                std::ofstream log(opt.output_dir / "xstar2xspec-mpi.log", std::ios::out | std::ios::app);
                if (!log) throw std::runtime_error("cannot reopen xstar2xspec-mpi.log");
                std::ofstream scheduler(opt.output_dir / "xstar2xspec-mpi-scheduler.log", std::ios::out | std::ios::trunc);
                if (!scheduler) throw std::runtime_error("cannot create xstar2xspec-mpi-scheduler.log");
                scheduler << "ranks_requested=" << world << "\n";
                scheduler << "ranks_effective=" << (pending_count == 0 ? 0 : std::min(world, pending_count)) << "\n";
                scheduler << "jobs_total=" << lines.size() << "\n";
                scheduler << "jobs_pending=" << pending_count << "\n";
                scheduler << "jobs_reused=" << reused << "\n";
                scheduler << "jobs_attempted=" << total_attempted << "\n";
                scheduler << "successful_loopcontrols=" << join_indices(all_completed) << "\n";
                for (int r = 0; r < world; ++r) {
                    char name[64];
                    std::snprintf(name, sizeof(name), "xstar2xspec-mpi-rank-%06d.log", r);
                    scheduler << "rank_log=" << name << "\n";
                }
                if (global_failed) throw std::runtime_error("one or more MPI ranks reported xstar-cpp failure");

                for (std::size_t i = 0; i < lines.size(); ++i) {
                    require_regular(spectra[i], "job xout_spect1.fits");
                    require_regular(steps[i], "job xout_step.log");
                    require_regular(success_markers[i], "job xstar-cpp.success");
                    log << "[job " << (i + 1) << "/" << lines.size() << "] canonical_output\n";
                    if (fs::is_regular_file(stdout_logs[i])) append_file(log, stdout_logs[i], opt.verbose);
                    else if (opt.restart) log << "[job " << (i + 1) << "] restart_reuse (no stdout replay)\n";
                }

                concatenate_step_logs(steps, opt.output_dir / "xout_step.log");
                const fs::path initable_path = opt.output_dir / "xstinitable.fits";
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
                    fs::remove_all(opt.output_dir / "xstar2xspec-work", ec);
                    if (ec) log << "[cleanup] warning=" << ec.message() << "\n";
                    else log << "[cleanup] explicit --cleanup-work removed xstar2xspec-work after success\n";
                } else {
                    log << "[preserve] xstar2xspec-work retained; XSTAR products are never auto-deleted\n";
                }
            } catch (const std::exception &exc) {
                root_final_ok = 0;
                root_final_error = exc.what();
            }
        }
        MPI_Bcast(&root_final_ok, 1, MPI_INT, 0, MPI_COMM_WORLD);
        if (!root_final_ok) {
            if (rank == 0) std::fprintf(stderr, "xstar-xspec-mpi: %s\n", root_final_error.c_str());
            final_rc = 1;
        } else {
            if (rank == 0) {
                std::cout << "XSTAR_XSPEC_MPI_0686_JOBS=" << lines.size() << "\n";
                std::cout << "XSTAR_XSPEC_MPI_0686_RANKS_REQUESTED=" << world << "\n";
                std::cout << "XSTAR_XSPEC_MPI_0686_RANKS_EFFECTIVE=" << (pending_count == 0 ? 0 : std::min(world, pending_count)) << "\n";
                std::cout << "XSTAR_XSPEC_MPI_0686_EXECUTED=" << total_attempted << "\n";
                std::cout << "XSTAR_XSPEC_MPI_0686_REUSED=" << reused << "\n";
                std::cout << "XSTAR_XSPEC_MPI_0686_SUCCESSFUL_LOOPCONTROLS=" << join_indices(all_completed) << "\n";
                std::cout << "XSTAR_XSPEC_MPI_0686_LOOPCONTROL_FIRST=1\n";
                std::cout << "XSTAR_XSPEC_MPI_0686_LOOPCONTROL_LAST=" << lines.size() << "\n";
                std::cout << "XSTAR_XSPEC_MPI_0686_TABLES=4\n";
                std::cout << "XSTAR_XSPEC_MPI_0686_WORKDIR=xstar2xspec-work\n";
                std::cout << "XSTAR_XSPEC_MPI_0686_RESULT=ACCEPT\n";
            }
            final_rc = 0;
        }
    } catch (const std::exception &exc) {
        if (rank == 0) {
            std::fprintf(stderr, "xstar-xspec-mpi: %s\n", exc.what());
            usage(argv[0]);
        }
        final_rc = 1;
    }

    MPI_Finalize();
    return final_rc;
}
