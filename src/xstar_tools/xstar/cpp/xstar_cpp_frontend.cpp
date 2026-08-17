// xstar-cpp first-class native command-line frontend.
//
// Productization role only: this file contains no XSTAR science. It accepts
// standard XSTAR-style inputs, writes the same literal JSON parameter envelope
// consumed by the qualified sibling `xstar_cpp run-production` executable,
// verifies the linked public C/production-zone ABIs, and records optional
// orchestration/provenance artifacts. Scientific execution remains exclusively
// in the frozen native core.
// No Python interpreter or Python library is used by this frontend.

#include "xstar_api.h"
#include "xstar_parameter_contract.hpp"
#include "xstar_production_zone_bridge.h"

#include <array>
#include <cerrno>
#include <chrono>
#include <cstdint>
#include <cstdlib>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <optional>
#include <regex>
#include <set>
#include <sstream>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>

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
constexpr const char* kScienceRevision = XSTAR_API_VERSION_STRING;
constexpr std::uint32_t kExpectedCApiAbi = XSTAR_API_ABI_VERSION;
constexpr std::int32_t kExpectedZoneAbi = XSTAR_PRODUCTION_ZONE_ABI_V0648110;
constexpr int kAbiMismatchExit = 70;

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
    while (in) {
        in.read(reinterpret_cast<char*>(buf.data()), static_cast<std::streamsize>(buf.size()));
        const auto n=in.gcount();
        if(n>0) sha.update(buf.data(),static_cast<std::size_t>(n));
    }
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
                } else out << static_cast<char>(c);
        }
    }
    return out.str();
}

std::filesystem::path sibling_native(const char* argv0) {
    std::error_code ec;
    auto self = std::filesystem::absolute(std::filesystem::path(argv0), ec);
    if (ec) self = std::filesystem::path(argv0);
    return self.parent_path() / "xstar_cpp";
}

struct RuntimeAbi {
    std::uint32_t c_api = 0;
    std::int32_t zone = 0;
    std::string api_version;
};

RuntimeAbi runtime_abi() {
    RuntimeAbi result;
    result.c_api = xstar_api_abi_version();
    result.zone = xstar_production_zone_abi_version_v0648110();
    const char* version = xstar_api_version_string();
    if (version) result.api_version = version;
    return result;
}

bool verify_runtime_abi(std::ostream& err, RuntimeAbi* observed = nullptr) {
    const RuntimeAbi abi = runtime_abi();
    if (observed) *observed = abi;
    bool ok = true;
    if (abi.c_api != kExpectedCApiAbi) {
        err << "xstar-cpp: C API ABI mismatch: frontend expects " << kExpectedCApiAbi
            << " but linked libxstar_api reports " << abi.c_api << "\n";
        ok = false;
    }
    if (abi.zone != kExpectedZoneAbi) {
        err << "xstar-cpp: production-zone ABI mismatch: frontend expects " << kExpectedZoneAbi
            << " but linked libxstar_production_zone reports " << abi.zone << "\n";
        ok = false;
    }
    if (!abi.api_version.empty() && abi.api_version != kScienceRevision) {
        err << "xstar-cpp: science revision mismatch: frontend expects " << kScienceRevision
            << " but linked libxstar_api reports " << abi.api_version << "\n";
        ok = false;
    }
    return ok;
}

void print_version(std::ostream& out) {
    const auto abi = runtime_abi();
    out << "xstar-cpp package version " << kPackageVersion << "\n"
        << "xstar-cpp science revision " << kScienceRevision << "\n"
        << "xstar-cpp C API ABI " << abi.c_api << "\n"
        << "xstar-cpp production-zone ABI " << abi.zone << "\n";
}

void print_abi(std::ostream& out) {
    const auto abi = runtime_abi();
    out << "package_version=" << kPackageVersion << "\n"
        << "science_revision=" << kScienceRevision << "\n"
        << "expected_c_api_abi=" << kExpectedCApiAbi << "\n"
        << "runtime_c_api_abi=" << abi.c_api << "\n"
        << "expected_production_zone_abi=" << kExpectedZoneAbi << "\n"
        << "runtime_production_zone_abi=" << abi.zone << "\n"
        << "runtime_api_science_revision=" << abi.api_version << "\n";
}

void usage(std::ostream& out) {
    out <<
        "xstar-cpp - first-class native XSTAR execution frontend\n\n"
        "Standard-compatible native run (no Python):\n"
        "  xstar-cpp --input xstar.par --data-dir /path/to/xstar/data --output run1\n"
        "  xstar-cpp xstar.par --data-dir /path/to/xstar/data --output run1\n"
        "  xstar-cpp --data-dir DATA --output run1 name=value [name=value ...]\n\n"
        "Standard input options:\n"
        "  --input PATH           HEASoft/IRAF-style .par parameter file\n"
        "  --data-dir DIR         directory containing atdb.fits and coheat.dat\n"
        "  --input-dir DIR        source-side directory for fixed-name files such as density.dat\n"
        "  --output DIR           output directory (alias: --output-dir)\n"
        "  --atomic-db PATH       explicit atdb.fits path\n"
        "  --coheat PATH          explicit coheat.dat path\n\n"
        "xstar-cpp orchestration extensions (not canonical XSTAR parameters):\n"
        "  --json-summary FILE    write machine-readable run summary\n"
        "  --provenance FILE      write provenance JSON to an additional path\n"
        "  --progress MODE        none, text, or json (default: text)\n"
        "  --threads N            set OMP_NUM_THREADS for this native run\n"
        "  --profile FILE         write frontend wall-time/profile JSON\n"
        "  --deterministic        record reproducible-run intent in provenance\n"
        "  --print-option N       print requested completed xout_step.log section\n"
        "  --parameters-out PATH  keep/write generated JSON parameter envelope\n"
        "  --abi                  show compiled/runtime ABI identities\n"
        "  --version              show package/science/ABI versions\n"
        "  --help                 show this help\n\n"
        "Compatibility interfaces remain available, including:\n"
        "  xstar-cpp run-production --parameters parameters.json --output-dir DIR\n"
        "  xstar-cpp run-xstar name=value ...\n\n"
        "All scientific execution delegates to the qualified sibling xstar_cpp core.\n";
}

bool is_passthrough_command(const std::string& arg) {
    static const std::set<std::string> commands = {
        "run-production", "run", "run-production-assets", "list-backends", "backend-info",
        "self-test", "element-self-test", "evaluation-self-test", "construction-self-test",
        "construction-evaluation-self-test", "spectral-self-test", "thermal-self-test",
        "convergence-self-test", "secant-ieee-self-test", "trajectory-alignment-self-test",
        "controller-canonical-e7-self-test", "fixed-state-self-test", "run-fixed-state",
        "fixed-state-batch-self-test", "run-fixed-trajectory", "run-fixed-evaluation",
        "standalone-capabilities"
    };
    return commands.count(arg) != 0;
}

std::vector<std::string> parse_csv_row(const std::string& line) {
    std::vector<std::string> fields;
    std::string current;
    bool quoted = false;
    for (std::size_t i=0;i<line.size();++i) {
        const char c=line[i];
        if (quoted) {
            if (c=='"') {
                if (i+1<line.size() && line[i+1]=='"') { current.push_back('"'); ++i; }
                else quoted=false;
            } else current.push_back(c);
        } else if (c=='"') quoted=true;
        else if (c==',') { fields.push_back(current); current.clear(); }
        else current.push_back(c);
    }
    if (quoted) throw std::runtime_error("unterminated quoted field in .par file");
    fields.push_back(current);
    return fields;
}

std::string trim(std::string value) {
    const auto first=value.find_first_not_of(" \t\r\n");
    if(first==std::string::npos) return {};
    const auto last=value.find_last_not_of(" \t\r\n");
    return value.substr(first,last-first+1u);
}

void set_parameter(std::vector<std::pair<std::string,std::string>>& parameters,
                   const std::string& key, const std::string& value) {
    for (auto& item : parameters) {
        if (item.first == key) { item.second = value; return; }
    }
    parameters.emplace_back(key,value);
}

void load_par_file(const std::filesystem::path& path,
                   std::vector<std::pair<std::string,std::string>>& parameters) {
    std::ifstream in(path);
    if(!in) throw std::runtime_error("could not read parameter file: " + path.string());
    std::string line;
    std::size_t lineno=0;
    while(std::getline(in,line)) {
        ++lineno;
        const std::string stripped=trim(line);
        if(stripped.empty() || stripped[0]=='#') continue;
        const auto fields=parse_csv_row(line);
        if(fields.size()>=4u) {
            const std::string key=trim(fields[0]);
            if(!key.empty()) set_parameter(parameters,key,trim(fields[3]));
        } else if(fields.size()==1u) {
            const auto pos=fields[0].find('=');
            if(pos==std::string::npos || pos==0u)
                throw std::runtime_error("unsupported parameter row " + std::to_string(lineno) + " in " + path.string());
            set_parameter(parameters,trim(fields[0].substr(0,pos)),trim(fields[0].substr(pos+1u)));
        } else {
            throw std::runtime_error("unsupported parameter row " + std::to_string(lineno) + " in " + path.string());
        }
    }
    if(parameters.empty()) throw std::runtime_error("no XSTAR parameters found in " + path.string());
}

struct FrontendInput {
    std::filesystem::path input_file;
    std::filesystem::path data_dir;
    std::filesystem::path input_dir{"."};
    std::filesystem::path output_dir{"."};
    std::filesystem::path parameters_out;
    std::filesystem::path json_summary;
    std::filesystem::path provenance_path;
    std::filesystem::path profile_path;
    std::string atomic_db;
    std::string coheat;
    std::string progress{"text"};
    int threads=0;
    int print_option=-1;
    bool deterministic=false;
    std::vector<std::pair<std::string,std::string>> parameters;
};

bool parse_int(const std::string& text, int minimum, int& result) {
    try {
        std::size_t used=0;
        const long value=std::stol(text,&used,10);
        if(used!=text.size() || value<minimum || value>2147483647L) return false;
        result=static_cast<int>(value); return true;
    } catch(...) { return false; }
}

bool parse_frontend(int argc, char** argv, int start, FrontendInput& input, std::string& error) {
    for (int i=start;i<argc;++i) {
        const std::string arg=argv[i];
        auto value_after = [&](const char* flag) -> const char* {
            if(i+1>=argc) { error=std::string("missing value for ")+flag; return nullptr; }
            return argv[++i];
        };
        if(arg=="--input") { const char* v=value_after("--input"); if(!v) return false; input.input_file=v; }
        else if(arg=="--data-dir") { const char* v=value_after("--data-dir"); if(!v) return false; input.data_dir=v; }
        else if(arg=="--input-dir") { const char* v=value_after("--input-dir"); if(!v) return false; input.input_dir=v; }
        else if(arg=="--output" || arg=="--output-dir") { const char* v=value_after(arg.c_str()); if(!v) return false; input.output_dir=v; }
        else if(arg=="--atomic-db") { const char* v=value_after("--atomic-db"); if(!v) return false; input.atomic_db=v; }
        else if(arg=="--coheat") { const char* v=value_after("--coheat"); if(!v) return false; input.coheat=v; }
        else if(arg=="--parameters-out") { const char* v=value_after("--parameters-out"); if(!v) return false; input.parameters_out=v; }
        else if(arg=="--json-summary") { const char* v=value_after("--json-summary"); if(!v) return false; input.json_summary=v; }
        else if(arg=="--provenance") { const char* v=value_after("--provenance"); if(!v) return false; input.provenance_path=v; }
        else if(arg=="--profile") { const char* v=value_after("--profile"); if(!v) return false; input.profile_path=v; }
        else if(arg=="--progress") {
            const char* v=value_after("--progress"); if(!v) return false; input.progress=v;
            if(input.progress!="none" && input.progress!="text" && input.progress!="json") { error="--progress must be none, text, or json"; return false; }
        } else if(arg=="--threads") {
            const char* v=value_after("--threads"); if(!v) return false;
            if(!parse_int(v,1,input.threads)) { error="--threads must be an integer >= 1"; return false; }
        } else if(arg=="--print-option") {
            const char* v=value_after("--print-option"); if(!v) return false;
            if(!parse_int(v,0,input.print_option)) { error="--print-option must be a non-negative integer"; return false; }
        } else if(arg=="--deterministic") input.deterministic=true;
        else if(arg=="--") continue;
        else if(arg.rfind("--",0)==0) { error="unknown xstar-cpp option: "+arg; return false; }
        else {
            const auto pos=arg.find('=');
            if(pos!=std::string::npos && pos>0u) set_parameter(input.parameters,arg.substr(0,pos),arg.substr(pos+1u));
            else if(input.input_file.empty() && std::filesystem::is_regular_file(arg)) input.input_file=arg;
            else { error="expected XSTAR-style name=value token or parameter file, got: "+arg; return false; }
        }
    }
    try {
        if(!input.input_file.empty()) {
            std::vector<std::pair<std::string,std::string>> from_file;
            load_par_file(input.input_file,from_file);
            for(auto it=from_file.rbegin();it!=from_file.rend();++it) {
                bool overridden=false;
                for(const auto& cli : input.parameters) if(cli.first==it->first) { overridden=true; break; }
                if(!overridden) input.parameters.insert(input.parameters.begin(),*it);
            }
        }
    } catch(const std::exception& exc) { error=exc.what(); return false; }
    if(input.parameters.empty()) { error="no XSTAR parameters were provided"; return false; }
    // 0.6.82.23: a partial native command receives the same fresh stock
    // xstar.par defaults as XPI.  This also makes the generated JSON envelope
    // and provenance a complete record of the public values used by science.
    for (const auto& rule : xstar_parameter_contract::kRules) {
        bool present=false;
        for (const auto& item : input.parameters) if (item.first==rule.name) { present=true; break; }
        if (!present) set_parameter(input.parameters,rule.name,rule.default_text);
    }
    try {
        for (const auto& item : input.parameters) {
            if (xstar_parameter_contract::find(item.first)) {
                xstar_parameter_contract::validate_text(item.first,item.second);
            } else {
                static const std::set<std::string> extensions = {
                    "atomic_database","atomic_db","atdb","coheat_file","coheat",
                    "temperature_k","initial_radius_cm","initial_electron_fraction","xee",
                    "standalone_charge_tolerance","standalone_thermal_tolerance","input_dir"
                };
                if (!extensions.count(item.first)) throw std::runtime_error("unknown XSTAR parameter: "+item.first);
            }
        }
    } catch(const std::exception& exc) { error=exc.what(); return false; }
    if(!input.data_dir.empty()) {
        if(input.atomic_db.empty()) input.atomic_db=(input.data_dir/"atdb.fits").string();
        if(input.coheat.empty()) input.coheat=(input.data_dir/"coheat.dat").string();
        if(!std::filesystem::is_regular_file(input.atomic_db)) { error="missing atomic database: "+input.atomic_db; return false; }
        if(!std::filesystem::is_regular_file(input.coheat)) { error="missing coheat data: "+input.coheat; return false; }
    }
    return true;
}

std::filesystem::path write_envelope(const FrontendInput& input) {
    std::error_code ec;
    std::filesystem::create_directories(input.output_dir,ec);
    if(ec) throw std::runtime_error("could not create output directory: "+input.output_dir.string());

    // The native production operator deliberately validates artifact_profile=none
    // before returning: only XSTAR science products may exist in the requested
    // output directory at that boundary.  A frontend-generated parameter
    // envelope is orchestration state, not an XSTAR product, so keep the default
    // envelope in the system temporary directory and remove it after the run.
    // --parameters-out remains the explicit opt-in for retaining the envelope.
    std::filesystem::path path;
    if(input.parameters_out.empty()) {
        const auto temp_dir=std::filesystem::temp_directory_path(ec);
        if(ec) throw std::runtime_error("could not resolve temporary directory for parameter envelope");
        path=temp_dir/("xstar-cpp-parameters-"+std::to_string(static_cast<long long>(::getpid()))+".json");
        std::filesystem::remove(path,ec);
        ec.clear();
    } else {
        path=input.parameters_out;
    }
    if(path.has_parent_path()) std::filesystem::create_directories(path.parent_path(),ec);
    if(ec) throw std::runtime_error("could not create parameter-envelope directory: "+path.parent_path().string());
    std::ofstream out(path); if(!out) throw std::runtime_error("could not write parameter envelope: "+path.string());
    out << "{\n";
    bool first=true;
    auto emit=[&](const std::string& key,const std::string& value) {
        if(!first) out << ",\n";
        first=false;
        out << "  \"" << json_escape(key) << "\": \"" << json_escape(value) << "\"";
    };
    for(const auto& item:input.parameters) emit(item.first,item.second);
    emit("input_dir", std::filesystem::absolute(input.input_dir).string());
    if(!input.atomic_db.empty()) emit("atomic_database",input.atomic_db);
    if(!input.coheat.empty()) emit("coheat_file",input.coheat);
    out << "\n}\n";
    return std::filesystem::absolute(path);
}

int run_native_wait(const std::filesystem::path& native,const std::vector<std::string>& args) {
    const pid_t pid=::fork();
    if(pid<0) return 127;
    if(pid==0) {
        std::vector<std::string> storage; storage.reserve(args.size()+1u); storage.push_back(native.string()); storage.insert(storage.end(),args.begin(),args.end());
        std::vector<char*> av; av.reserve(storage.size()+1u); for(auto& item:storage) av.push_back(item.data()); av.push_back(nullptr);
        ::execv(native.c_str(),av.data()); _exit(127);
    }
    int status=0; while(::waitpid(pid,&status,0)<0) { if(errno!=EINTR) return 127; }
    if(WIFEXITED(status)) return WEXITSTATUS(status);
    if(WIFSIGNALED(status)) return 128+WTERMSIG(status);
    return 127;
}

[[noreturn]] void exec_native(const std::filesystem::path& native,const std::vector<std::string>& args) {
    std::vector<std::string> storage; storage.reserve(args.size()+1u); storage.push_back(native.string()); storage.insert(storage.end(),args.begin(),args.end());
    std::vector<char*> av; av.reserve(storage.size()+1u); for(auto& item:storage) av.push_back(item.data()); av.push_back(nullptr);
    ::execv(native.c_str(),av.data());
    std::cerr << "xstar-cpp: failed to exec " << native << ": errno=" << errno << "\n";
    std::exit(127);
}

void progress_event(const FrontendInput& input,const std::string& event,const std::string& detail="") {
    if(input.progress=="none") return;
    if(input.progress=="json") {
        std::cout << "{\"schema\":\"xstar-cpp-progress-v1\",\"event\":\"" << json_escape(event) << "\"";
        if(!detail.empty()) std::cout << ",\"detail\":\"" << json_escape(detail) << "\"";
        std::cout << "}\n" << std::flush;
    } else {
        std::cout << "xstar-cpp: " << event;
        if(!detail.empty()) std::cout << " " << detail;
        std::cout << "\n" << std::flush;
    }
}

std::vector<std::string> principal_products(const std::filesystem::path& output_dir) {
    static const std::array<const char*,9> names={{
        "xout_abund1.fits","xout_lines1.fits","xout_rrc1.fits","xout_cont1.fits","xout_spect1.fits",
        "xo01_detail.fits","xo01_detal2.fits","xo01_detal3.fits","xo01_detal4.fits"}};
    std::vector<std::string> found;
    for(const char* name:names) if(std::filesystem::is_regular_file(output_dir/name)) found.emplace_back(name);
    return found;
}

void ensure_parent(const std::filesystem::path& path) {
    if(!path.has_parent_path()) return;
    std::error_code ec; std::filesystem::create_directories(path.parent_path(),ec);
    if(ec) throw std::runtime_error("could not create directory: "+path.parent_path().string());
}

void write_execution_provenance(const std::filesystem::path& path,const FrontendInput& input,
                                const RuntimeAbi& abi,int returncode,double wall_seconds) {
    ensure_parent(path);
    std::ofstream out(path); if(!out) throw std::runtime_error("could not write provenance: "+path.string());
    const auto atdb_hash=input.atomic_db.empty()?std::optional<std::string>{}:sha256_file(input.atomic_db);
    const auto coheat_hash=input.coheat.empty()?std::optional<std::string>{}:sha256_file(input.coheat);
    out << "{\n"
        << "  \"schema\": \"xstar-cpp-provenance-v1\",\n"
        << "  \"requested_mode\": \"xstar-cpp\",\n"
        << "  \"actual_mode\": \"xstar-cpp\",\n"
        << "  \"package_version\": \"" << kPackageVersion << "\",\n"
        << "  \"science_revision\": \"" << kScienceRevision << "\",\n"
        << "  \"c_api_abi\": " << abi.c_api << ",\n"
        << "  \"zone_abi\": " << abi.zone << ",\n"
        << "  \"runtime_api_science_revision\": \"" << json_escape(abi.api_version) << "\",\n"
        << "  \"threads\": " << input.threads << ",\n"
        << "  \"deterministic_requested\": " << (input.deterministic?"true":"false") << ",\n"
        << "  \"cpp\": {\"used\": true, \"executable\": \"xstar_cpp\", \"version\": \"" << kScienceRevision << "\"},\n"
        << "  \"cpu\": {\"avx2\": " << (cpu_has_avx2()?"true":"false") << ", \"type50_dispatch\": \"runtime-avx2-or-scalar\"},\n"
        << "  \"fallback_events\": [],\n"
        << "  \"atomic_data\": {";
    bool first=true;
    if(!input.atomic_db.empty()) { out << "\"atdb_path\": \"" << json_escape(input.atomic_db) << "\", \"atdb_sha256\": " << (atdb_hash?"\""+*atdb_hash+"\"":"null"); first=false; }
    if(!input.coheat.empty()) { if(!first) out << ", "; out << "\"coheat_path\": \"" << json_escape(input.coheat) << "\", \"coheat_sha256\": " << (coheat_hash?"\""+*coheat_hash+"\"":"null"); }
    out << "},\n  \"parameter_contract\": {\"version\": \"0.6.82.23\", \"validation_envelope\": \"stock xstar.par/XPI\"},\n"
        << "  \"parameters_used\": {";
    for (std::size_t i=0;i<input.parameters.size();++i) {
        if (i) out << ", ";
        out << "\"" << json_escape(input.parameters[i].first) << "\": \""
            << json_escape(input.parameters[i].second) << "\"";
    }
    out << "},\n  \"wall_seconds\": " << std::setprecision(12) << wall_seconds << ",\n"
        << "  \"native_returncode\": " << returncode << "\n}\n";
}

void write_summary(const std::filesystem::path& path,const FrontendInput& input,const RuntimeAbi& abi,
                   int returncode,double wall_seconds,const std::filesystem::path& parameter_path) {
    ensure_parent(path); std::ofstream out(path); if(!out) throw std::runtime_error("could not write summary: "+path.string());
    const auto products=principal_products(input.output_dir);
    out << "{\n  \"schema\": \"xstar-cpp-summary-v1\",\n"
        << "  \"success\": " << (returncode==0?"true":"false") << ",\n"
        << "  \"return_code\": " << returncode << ",\n"
        << "  \"package_version\": \"" << kPackageVersion << "\",\n"
        << "  \"science_revision\": \"" << kScienceRevision << "\",\n"
        << "  \"c_api_abi\": " << abi.c_api << ",\n  \"zone_abi\": " << abi.zone << ",\n"
        << "  \"output_dir\": \"" << json_escape(std::filesystem::absolute(input.output_dir).string()) << "\",\n"
        << "  \"parameters\": \"" << json_escape(parameter_path.string()) << "\",\n"
        << "  \"step_log\": " << (std::filesystem::is_regular_file(input.output_dir/"xout_step.log")?"\"xout_step.log\"":"null") << ",\n"
        << "  \"produced_fits\": [";
    for(std::size_t i=0;i<products.size();++i) { if(i) out << ", "; out << "\"" << json_escape(products[i]) << "\""; }
    out << "],\n  \"wall_seconds\": " << std::setprecision(12) << wall_seconds << "\n}\n";
}

void write_profile(const std::filesystem::path& path,const FrontendInput& input,int returncode,double wall_seconds) {
    ensure_parent(path); std::ofstream out(path); if(!out) throw std::runtime_error("could not write profile: "+path.string());
    out << "{\n  \"schema\": \"xstar-cpp-profile-v1\",\n"
        << "  \"scope\": \"frontend-orchestration\",\n"
        << "  \"wall_seconds\": " << std::setprecision(12) << wall_seconds << ",\n"
        << "  \"threads\": " << input.threads << ",\n"
        << "  \"return_code\": " << returncode << "\n}\n";
}

bool line_is_print_marker(const std::string& line,int* option=nullptr) {
    static const std::regex re("print\\s+option\\s*:\\s*([0-9]+)",std::regex::icase);
    std::smatch m; if(!std::regex_search(line,m,re)) return false;
    if(option) *option=std::stoi(m[1].str());
    return true;
}

bool print_step_option(const std::filesystem::path& step_log,int requested,std::ostream& out) {
    std::ifstream in(step_log); if(!in) return false;
    bool active=false,found=false; std::string line;
    while(std::getline(in,line)) {
        int option=-1;
        if(line_is_print_marker(line,&option)) {
            if(active && option!=requested) break;
            active=(option==requested); if(active) found=true;
        }
        if(active) out << line << "\n";
    }
    return found;
}

int run_frontend(const std::filesystem::path& native,FrontendInput& input) {
    RuntimeAbi abi;
    if(!verify_runtime_abi(std::cerr,&abi)) return kAbiMismatchExit;
    if(input.threads>0) ::setenv("OMP_NUM_THREADS",std::to_string(input.threads).c_str(),1);
    if(input.deterministic) ::setenv("XSTAR_TOOLS_REPRODUCIBLE","1",1);
    // 0.6.82.3: propagate the public progress mode to the native production
    // process.  The standalone controller uses this only for live textual
    // zone observability; no scientific state consumes the variable.
    ::setenv("XSTAR_CPP_PROGRESS_MODE", input.progress.c_str(), 1);
    const bool retain_parameters=!input.parameters_out.empty();
    const auto parameters=write_envelope(input);
    auto remove_ephemeral_parameters=[&]() {
        if(retain_parameters) return;
        std::error_code ec;
        std::filesystem::remove(parameters,ec);
    };
    progress_event(input,"run_started",input.output_dir.string());
    const auto start=std::chrono::steady_clock::now();
    const int rc=run_native_wait(native,{"run-production","--parameters",parameters.string(),"--output-dir",input.output_dir.string()});
    const double wall=std::chrono::duration<double>(std::chrono::steady_clock::now()-start).count();
    try {
        const auto default_provenance=input.output_dir/"xstar_execution_provenance.json";
        write_execution_provenance(default_provenance,input,abi,rc,wall);
        if(!input.provenance_path.empty() && std::filesystem::absolute(input.provenance_path)!=std::filesystem::absolute(default_provenance))
            write_execution_provenance(input.provenance_path,input,abi,rc,wall);
        if(!input.json_summary.empty()) write_summary(input.json_summary,input,abi,rc,wall,parameters);
        if(!input.profile_path.empty()) write_profile(input.profile_path,input,rc,wall);
        remove_ephemeral_parameters();
    } catch(...) {
        remove_ephemeral_parameters();
        throw;
    }
    progress_event(input,rc==0?"run_completed":"run_failed","return_code="+std::to_string(rc));
    if(rc==0 && input.print_option>=0) {
        if(!print_step_option(input.output_dir/"xout_step.log",input.print_option,std::cout)) {
            std::cerr << "xstar-cpp: requested print option " << input.print_option << " was not found in xout_step.log\n";
            return 3;
        }
    }
    return rc;
}

} // namespace

int main(int argc,char** argv) {
    const auto native=sibling_native(argc>0?argv[0]:"xstar-cpp");
    if(argc==1) { usage(std::cout); return 0; }
    const std::string first=argv[1];
    if(first=="--help" || first=="-h" || first=="help") { usage(std::cout); return 0; }
    if(first=="--version" || first=="-V") { print_version(std::cout); return 0; }
    if(first=="--abi") {
        print_abi(std::cout);
        return verify_runtime_abi(std::cerr)?0:kAbiMismatchExit;
    }
    if(is_passthrough_command(first)) {
        if(!verify_runtime_abi(std::cerr)) return kAbiMismatchExit;
        std::vector<std::string> args; for(int i=1;i<argc;++i) args.emplace_back(argv[i]);
        if(first!="run-production") exec_native(native,args);
        FrontendInput input; std::filesystem::path parameters;
        for(int i=2;i<argc;++i) {
            const std::string arg=argv[i];
            if(arg=="--output-dir" && i+1<argc) input.output_dir=argv[++i];
            else if(arg=="--parameters" && i+1<argc) parameters=argv[++i];
        }
        if(!parameters.empty()) {
            if(auto v=json_string_field(parameters,"atomic_database")) input.atomic_db=*v;
            if(auto v=json_string_field(parameters,"coheat_file")) input.coheat=*v;
        }
        RuntimeAbi abi=runtime_abi();
        const auto start=std::chrono::steady_clock::now();
        const int rc=run_native_wait(native,args);
        const double wall=std::chrono::duration<double>(std::chrono::steady_clock::now()-start).count();
        try { write_execution_provenance(input.output_dir/"xstar_execution_provenance.json",input,abi,rc,wall); }
        catch(const std::exception& exc) { std::cerr << "xstar-cpp: " << exc.what() << "\n"; }
        return rc;
    }

    const int start=first=="run-xstar"?2:1;
    FrontendInput input; std::string error;
    if(!parse_frontend(argc,argv,start,input,error)) {
        std::cerr << "xstar-cpp: " << error << "\n"; usage(std::cerr); return 2;
    }
    try { return run_frontend(native,input); }
    catch(const std::exception& exc) { std::cerr << "xstar-cpp: " << exc.what() << "\n"; return 2; }
}
