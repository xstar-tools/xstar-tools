// xstar-cpp stable native command-line frontend.
//
// Productization role only: this file contains no XSTAR science.  For normal
// native runs it preserves literal XSTAR-style name=value tokens in a small
// JSON parameter envelope, then execs the already-qualified sibling
// `xstar_cpp run-production` executable.  Existing native commands (including
// `run-production --parameters ...`) are passed through unchanged.
// No Python interpreter or Python library is used by this frontend.

#include <array>
#include <cerrno>
#include <cstdint>
#include <cstring>
#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <optional>
#include <regex>
#include <set>
#include <sstream>
#include <string>
#include <vector>
#include <iomanip>

#if defined(__unix__) || defined(__APPLE__)
#include <sys/wait.h>
#include <unistd.h>
#else
#error "xstar-cpp native frontend currently requires a POSIX execv environment"
#endif

namespace {

#ifndef XSTAR_TOOLS_PACKAGE_VERSION
#define XSTAR_TOOLS_PACKAGE_VERSION "unknown"
#endif
constexpr const char* kPackageVersion = XSTAR_TOOLS_PACKAGE_VERSION;
constexpr const char* kScienceRevision = "0.6.48.12.3.45.3.3.8";
constexpr std::uint32_t kCApiAbi = 60487u;
constexpr std::uint32_t kZoneAbi = 6048110u;

std::string json_escape(const std::string& value);

class Sha256 {
public:
    Sha256() : state_{0x6a09e667u,0xbb67ae85u,0x3c6ef372u,0xa54ff53au,0x510e527fu,0x9b05688cu,0x1f83d9abu,0x5be0cd19u} {}
    void update(const unsigned char* data, std::size_t len) {
        for (std::size_t i=0;i<len;++i) {
            block_[block_len_++] = data[i];
            if (block_len_ == 64u) { transform(); bit_len_ += 512u; block_len_=0u; }
        }
    }
    std::string final_hex() {
        std::size_t i=block_len_;
        block_[i++]=0x80u;
        if (i>56u) { while(i<64u) block_[i++]=0u; transform(); i=0u; }
        while(i<56u) block_[i++]=0u;
        bit_len_ += static_cast<std::uint64_t>(block_len_) * 8u;
        for (int j=7;j>=0;--j) block_[56u + static_cast<std::size_t>(7-j)] = static_cast<unsigned char>((bit_len_ >> (j*8)) & 0xffu);
        transform();
        std::ostringstream out; out << std::hex << std::setfill('0');
        for (auto v: state_) out << std::setw(8) << v;
        return out.str();
    }
private:
    static std::uint32_t rotr(std::uint32_t x, std::uint32_t n) { return (x>>n)|(x<<(32u-n)); }
    void transform() {
        static constexpr std::array<std::uint32_t,64> k={{
            0x428a2f98u,0x71374491u,0xb5c0fbcfu,0xe9b5dba5u,0x3956c25bu,0x59f111f1u,0x923f82a4u,0xab1c5ed5u,
            0xd807aa98u,0x12835b01u,0x243185beu,0x550c7dc3u,0x72be5d74u,0x80deb1feu,0x9bdc06a7u,0xc19bf174u,
            0xe49b69c1u,0xefbe4786u,0x0fc19dc6u,0x240ca1ccu,0x2de92c6fu,0x4a7484aau,0x5cb0a9dcu,0x76f988dau,
            0x983e5152u,0xa831c66du,0xb00327c8u,0xbf597fc7u,0xc6e00bf3u,0xd5a79147u,0x06ca6351u,0x14292967u,
            0x27b70a85u,0x2e1b2138u,0x4d2c6dfcu,0x53380d13u,0x650a7354u,0x766a0abbu,0x81c2c92eu,0x92722c85u,
            0xa2bfe8a1u,0xa81a664bu,0xc24b8b70u,0xc76c51a3u,0xd192e819u,0xd6990624u,0xf40e3585u,0x106aa070u,
            0x19a4c116u,0x1e376c08u,0x2748774cu,0x34b0bcb5u,0x391c0cb3u,0x4ed8aa4au,0x5b9cca4fu,0x682e6ff3u,
            0x748f82eeu,0x78a5636fu,0x84c87814u,0x8cc70208u,0x90befffau,0xa4506cebu,0xbef9a3f7u,0xc67178f2u}};
        std::uint32_t w[64]{};
        for (std::size_t j=0;j<16;++j) {
            const std::size_t o=j*4u;
            w[j]=(static_cast<std::uint32_t>(block_[o])<<24u)|(static_cast<std::uint32_t>(block_[o+1])<<16u)|
                 (static_cast<std::uint32_t>(block_[o+2])<<8u)|static_cast<std::uint32_t>(block_[o+3]);
        }
        for (std::size_t j=16;j<64;++j) {
            const auto s0=rotr(w[j-15],7u)^rotr(w[j-15],18u)^(w[j-15]>>3u);
            const auto s1=rotr(w[j-2],17u)^rotr(w[j-2],19u)^(w[j-2]>>10u);
            w[j]=w[j-16]+s0+w[j-7]+s1;
        }
        auto a=state_[0],b=state_[1],c=state_[2],d=state_[3],e=state_[4],f=state_[5],g=state_[6],h=state_[7];
        for (std::size_t j=0;j<64;++j) {
            const auto s1=rotr(e,6u)^rotr(e,11u)^rotr(e,25u);
            const auto ch=(e&f)^((~e)&g);
            const auto t1=h+s1+ch+k[j]+w[j];
            const auto s0=rotr(a,2u)^rotr(a,13u)^rotr(a,22u);
            const auto maj=(a&b)^(a&c)^(b&c);
            const auto t2=s0+maj;
            h=g;g=f;f=e;e=d+t1;d=c;c=b;b=a;a=t1+t2;
        }
        state_[0]+=a;state_[1]+=b;state_[2]+=c;state_[3]+=d;state_[4]+=e;state_[5]+=f;state_[6]+=g;state_[7]+=h;
    }
    std::array<std::uint32_t,8> state_;
    std::array<unsigned char,64> block_{};
    std::size_t block_len_=0u;
    std::uint64_t bit_len_=0u;
};

std::optional<std::string> sha256_file(const std::filesystem::path& path) {
    std::ifstream in(path, std::ios::binary);
    if (!in) return std::nullopt;
    Sha256 sha; std::array<unsigned char,65536> buf{};
    while (in) { in.read(reinterpret_cast<char*>(buf.data()), static_cast<std::streamsize>(buf.size())); const auto n=in.gcount(); if(n>0) sha.update(buf.data(),static_cast<std::size_t>(n)); }
    return sha.final_hex();
}

std::optional<std::string> json_string_field(const std::filesystem::path& path, const std::string& key) {
    std::ifstream in(path); if(!in) return std::nullopt;
    const std::string text((std::istreambuf_iterator<char>(in)), std::istreambuf_iterator<char>());
    const std::regex re("\\\""+key+"\\\"\\s*:\\s*\\\"([^\\\"]*)\\\""); std::smatch m;
    if(!std::regex_search(text,m,re)) return std::nullopt;
    return m[1].str();
}

bool cpu_has_avx2() {
#if (defined(__x86_64__) || defined(__i386__)) && (defined(__GNUC__) || defined(__clang__))
    __builtin_cpu_init(); return __builtin_cpu_supports("avx2");
#else
    return false;
#endif
}

int run_native_wait(const std::filesystem::path& native, const std::vector<std::string>& args) {
    const pid_t pid=::fork();
    if(pid<0) return 127;
    if(pid==0) {
        std::vector<std::string> storage; storage.reserve(args.size()+1); storage.push_back(native.string()); storage.insert(storage.end(),args.begin(),args.end());
        std::vector<char*> argv; argv.reserve(storage.size()+1); for(auto& item:storage) argv.push_back(item.data()); argv.push_back(nullptr);
        ::execv(native.c_str(),argv.data()); _exit(127);
    }
    int status=0; while(::waitpid(pid,&status,0)<0) { if(errno!=EINTR) return 127; }
    if(WIFEXITED(status)) return WEXITSTATUS(status);
    if(WIFSIGNALED(status)) return 128+WTERMSIG(status);
    return 127;
}

void write_execution_provenance(const std::filesystem::path& output_dir, int returncode,
                                const std::string& atdb, const std::string& coheat) {
    std::error_code ec; std::filesystem::create_directories(output_dir,ec); if(ec) return;
    std::ofstream out(output_dir/"xstar_execution_provenance.json"); if(!out) return;
    const auto atdb_hash=atdb.empty()?std::optional<std::string>{}:sha256_file(atdb);
    const auto coheat_hash=coheat.empty()?std::optional<std::string>{}:sha256_file(coheat);
    out << "{\n"
        << "  \"requested_mode\": \"xstar-cpp\",\n"
        << "  \"actual_mode\": \"xstar-cpp\",\n"
        << "  \"package_version\": \"" << kPackageVersion << "\",\n"
        << "  \"science_revision\": \"" << kScienceRevision << "\",\n"
        << "  \"c_api_abi\": " << kCApiAbi << ",\n"
        << "  \"zone_abi\": " << kZoneAbi << ",\n"
        << "  \"cpp\": {\"used\": true, \"executable\": \"xstar_cpp\", \"version\": \"" << kScienceRevision << "\"},\n"
        << "  \"cpu\": {\"avx2\": " << (cpu_has_avx2()?"true":"false") << ", \"type50_dispatch\": \"runtime-avx2-or-scalar\"},\n"
        << "  \"fallback_events\": [],\n"
        << "  \"atomic_data\": {";
    if(!atdb.empty()) out << "\"atdb_path\": \"" << json_escape(atdb) << "\", \"atdb_sha256\": " << (atdb_hash?"\""+*atdb_hash+"\"":"null");
    if(!coheat.empty()) { if(!atdb.empty()) out << ", "; out << "\"coheat_path\": \"" << json_escape(coheat) << "\", \"coheat_sha256\": " << (coheat_hash?"\""+*coheat_hash+"\"":"null"); }
    out << "},\n  \"native_returncode\": " << returncode << "\n}\n";
}

std::string json_escape(const std::string& value) {
    std::ostringstream out;
    for (unsigned char c : value) {
        switch (c) {
            case '\\': out << "\\\\"; break;
            case '"': out << "\\\""; break;
            case '\b': out << "\\b"; break;
            case '\f': out << "\\f"; break;
            case '\n': out << "\\n"; break;
            case '\r': out << "\\r"; break;
            case '\t': out << "\\t"; break;
            default:
                if (c < 0x20) {
                    static constexpr char hex[] = "0123456789abcdef";
                    out << "\\u00" << hex[(c >> 4) & 0xf] << hex[c & 0xf];
                } else {
                    out << static_cast<char>(c);
                }
        }
    }
    return out.str();
}

[[noreturn]] void exec_native(const std::filesystem::path& native, const std::vector<std::string>& args) {
    std::vector<std::string> storage;
    storage.reserve(args.size() + 1);
    storage.push_back(native.string());
    storage.insert(storage.end(), args.begin(), args.end());
    std::vector<char*> argv;
    argv.reserve(storage.size() + 1);
    for (auto& item : storage) argv.push_back(item.data());
    argv.push_back(nullptr);
    ::execv(native.c_str(), argv.data());
    std::cerr << "xstar-cpp: failed to exec " << native << ": errno=" << errno << "\n";
    std::exit(127);
}

std::filesystem::path sibling_native(const char* argv0) {
    std::error_code ec;
    auto self = std::filesystem::absolute(std::filesystem::path(argv0), ec);
    if (ec) self = std::filesystem::path(argv0);
    return self.parent_path() / "xstar_cpp";
}

void usage(std::ostream& out) {
    out <<
        "xstar-cpp - stable native XSTAR execution frontend\n\n"
        "Normal XSTAR-style run (no Python):\n"
        "  xstar-cpp [--atomic-db atdb.fits] [--coheat coheat.dat] [--output-dir DIR] name=value ...\n"
        "  xstar-cpp run-xstar [same options] name=value ...\n\n"
        "Machine-readable qualified path:\n"
        "  xstar-cpp run-production --parameters parameters.json --output-dir DIR\n\n"
        "Frontend options for XSTAR-style runs:\n"
        "  --atomic-db PATH       write atomic_database into the native parameter envelope\n"
        "  --coheat PATH          write coheat_file into the native parameter envelope\n"
        "  --output-dir DIR       native output directory (default: .)\n"
        "  --parameters-out PATH  keep/write the generated JSON at PATH\n"
        "  --help                 show this help\n\n"
        "All other existing xstar_cpp commands are passed through unchanged.\n";
}

bool is_passthrough_command(const std::string& arg) {
    static const std::set<std::string> commands = {
        "run-production", "run", "run-production-assets", "list-backends", "backend-info",
        "self-test", "element-self-test", "evaluation-self-test", "construction-self-test",
        "construction-evaluation-self-test", "spectral-self-test", "thermal-self-test",
        "convergence-self-test", "secant-ieee-self-test", "trajectory-alignment-self-test",
        "controller-canonical-e7-self-test", "fixed-state-self-test", "run-fixed-state",
        "fixed-state-batch-self-test", "run-fixed-trajectory", "run-fixed-evaluation",
        "standalone-capabilities", "--version", "-V"
    };
    return commands.count(arg) != 0;
}

struct FrontendInput {
    std::filesystem::path output_dir{"."};
    std::filesystem::path parameters_out;
    std::string atomic_db;
    std::string coheat;
    std::vector<std::pair<std::string, std::string>> parameters;
};

bool parse_xstar_style(int argc, char** argv, int start, FrontendInput& input, std::string& error) {
    for (int i = start; i < argc; ++i) {
        std::string arg = argv[i];
        auto value_after = [&](const char* flag) -> const char* {
            if (i + 1 >= argc) {
                error = std::string("missing value for ") + flag;
                return nullptr;
            }
            return argv[++i];
        };
        if (arg == "--atomic-db") {
            const char* v = value_after("--atomic-db"); if (!v) return false; input.atomic_db = v;
        } else if (arg == "--coheat") {
            const char* v = value_after("--coheat"); if (!v) return false; input.coheat = v;
        } else if (arg == "--output-dir") {
            const char* v = value_after("--output-dir"); if (!v) return false; input.output_dir = v;
        } else if (arg == "--parameters-out") {
            const char* v = value_after("--parameters-out"); if (!v) return false; input.parameters_out = v;
        } else if (arg == "--") {
            continue;
        } else {
            const auto pos = arg.find('=');
            if (pos == std::string::npos || pos == 0) {
                error = "expected XSTAR-style name=value token, got: " + arg;
                return false;
            }
            input.parameters.emplace_back(arg.substr(0, pos), arg.substr(pos + 1));
        }
    }
    if (input.parameters.empty()) {
        error = "no XSTAR-style name=value parameters were provided";
        return false;
    }
    return true;
}

std::filesystem::path write_envelope(const FrontendInput& input) {
    std::error_code ec;
    std::filesystem::create_directories(input.output_dir, ec);
    if (ec) throw std::runtime_error("could not create output directory: " + input.output_dir.string());
    auto path = input.parameters_out.empty() ? input.output_dir / ".xstar-cpp-parameters.json" : input.parameters_out;
    if (path.has_parent_path()) std::filesystem::create_directories(path.parent_path(), ec);
    if (ec) throw std::runtime_error("could not create parameter-envelope directory: " + path.parent_path().string());
    std::ofstream out(path);
    if (!out) throw std::runtime_error("could not write parameter envelope: " + path.string());
    out << "{\n";
    bool first = true;
    auto emit = [&](const std::string& key, const std::string& value) {
        if (!first) out << ",\n";
        first = false;
        out << "  \"" << json_escape(key) << "\": \"" << json_escape(value) << "\"";
    };
    for (const auto& [key, value] : input.parameters) emit(key, value);
    if (!input.atomic_db.empty()) emit("atomic_database", input.atomic_db);
    if (!input.coheat.empty()) emit("coheat_file", input.coheat);
    out << "\n}\n";
    return std::filesystem::absolute(path);
}

} // namespace

int main(int argc, char** argv) {
    const auto native = sibling_native(argc > 0 ? argv[0] : "xstar-cpp");
    if (argc == 1) {
        usage(std::cout);
        return 0;
    }
    const std::string first = argv[1];
    if (first == "--help" || first == "-h" || first == "help") {
        usage(std::cout);
        return 0;
    }
    if (is_passthrough_command(first)) {
        std::vector<std::string> args;
        for (int i = 1; i < argc; ++i) args.emplace_back(argv[i]);
        if (first != "run-production") exec_native(native, args);
        std::filesystem::path output_dir{"."};
        std::filesystem::path parameters;
        for (int i=2;i<argc;++i) {
            const std::string arg=argv[i];
            if(arg=="--output-dir" && i+1<argc) output_dir=argv[++i];
            else if(arg=="--parameters" && i+1<argc) parameters=argv[++i];
        }
        std::string atdb,coheat;
        if(!parameters.empty()) {
            if(auto v=json_string_field(parameters,"atomic_database")) atdb=*v;
            if(auto v=json_string_field(parameters,"coheat_file")) coheat=*v;
        }
        const int rc=run_native_wait(native,args);
        write_execution_provenance(output_dir,rc,atdb,coheat);
        return rc;
    }

    const int start = first == "run-xstar" ? 2 : 1;
    FrontendInput input;
    std::string error;
    if (!parse_xstar_style(argc, argv, start, input, error)) {
        std::cerr << "xstar-cpp: " << error << "\n";
        usage(std::cerr);
        return 2;
    }
    try {
        const auto parameters = write_envelope(input);
        const int rc=run_native_wait(native,{"run-production", "--parameters", parameters.string(), "--output-dir", input.output_dir.string()});
        write_execution_provenance(input.output_dir,rc,input.atomic_db,input.coheat);
        return rc;
    } catch (const std::exception& exc) {
        std::cerr << "xstar-cpp: " << exc.what() << "\n";
        return 2;
    }
}
