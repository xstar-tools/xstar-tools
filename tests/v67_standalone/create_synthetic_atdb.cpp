#include <fitsio.h>
#include <cstdint>
#include <filesystem>
#include <iostream>
#include <stdexcept>
#include <string>
#include <vector>

struct Rec {
    int data_type;
    int rate_type;
    std::vector<double> reals;
    std::vector<long long> ints;
    std::string chars;
};

static void check(int status, const char* where) {
    if (!status) return;
    char text[FLEN_STATUS]{};
    fits_get_errstatus(status, text);
    throw std::runtime_error(std::string(where) + ": " + text);
}

int main(int argc, char** argv) {
    if (argc != 2) {
        std::cerr << "usage: create_synthetic_atdb OUTPUT.fits\n";
        return 64;
    }
    const std::filesystem::path output = argv[1];
    std::error_code ec;
    std::filesystem::remove(output, ec);

    // Packed ATDB topology: H element, H I and H II ions, two levels per ion,
    // one radiative line and one scalar thermal record per ion.
    std::vector<Rec> recs = {
        {0, 11, {}, {1}, "h"},
        {0, 12, {}, {1}, "h_i"},
        {13,13, {0.0,2.0,0.0,13.5984}, {1,1,0}, "1s"},
        {13,13, {13.5984,1.0,0.0,13.5984}, {2,2,0}, "continuum"},
        {50,4, {911.267,0.0,6.25e8}, {1,2}, "Ly edge test"},
        {1,3, {1.0e-13,0.5}, {}, "scalar h_i"},
        {0, 12, {}, {2}, "h_ii"},
        {13,13, {0.0,1.0,0.0,0.0}, {1,1,0}, "ground"},
        {13,13, {10.2,3.0,0.0,0.0}, {2,2,1}, "excited"},
        {50,4, {1215.67,0.0,6.265e8}, {1,2}, "Ly alpha test"},
        {1,3, {5.0e-14,0.25}, {}, "scalar h_ii"},
    };

    std::vector<long long> pointers;
    std::vector<double> reals;
    std::vector<long long> ints;
    std::vector<unsigned char> chars;
    pointers.reserve(recs.size() * 10);
    for (std::size_t i = 0; i < recs.size(); ++i) {
        const auto& r = recs[i];
        const long long real_ptr = static_cast<long long>(reals.size()) + 1;
        const long long int_ptr = static_cast<long long>(ints.size()) + 1;
        const long long char_ptr = static_cast<long long>(chars.size()) + 1;
        pointers.push_back(static_cast<long long>(i + 1));
        pointers.push_back(r.data_type);
        pointers.push_back(r.rate_type);
        pointers.push_back(0);
        pointers.push_back(static_cast<long long>(r.reals.size()));
        pointers.push_back(static_cast<long long>(r.ints.size()));
        pointers.push_back(static_cast<long long>(r.chars.size()));
        pointers.push_back(real_ptr);
        pointers.push_back(int_ptr);
        pointers.push_back(char_ptr);
        reals.insert(reals.end(), r.reals.begin(), r.reals.end());
        ints.insert(ints.end(), r.ints.begin(), r.ints.end());
        chars.insert(chars.end(), r.chars.begin(), r.chars.end());
    }
    if (reals.empty()) reals.push_back(0.0);
    if (ints.empty()) ints.push_back(0);
    if (chars.empty()) chars.push_back(0);

    fitsfile* f = nullptr;
    int status = 0;
    const std::string create = "!" + output.string();
    fits_create_file(&f, create.c_str(), &status); check(status, "create file");
    fits_create_img(f, BYTE_IMG, 0, nullptr, &status); check(status, "create primary");

    auto write_vector_hdu = [&](const char* extname, const char* tform, int typecode,
                                void* data, long long count, bool length_keyword) {
        char* ttype[] = {const_cast<char*>("DATA")};
        char* tforms[] = {const_cast<char*>(tform)};
        fits_create_tbl(f, BINARY_TBL, 1, 1, ttype, tforms, nullptr,
                        const_cast<char*>(extname), &status);
        check(status, "create table");
        fits_write_col(f, typecode, 1, 1, 1, count, data, &status);
        check(status, "write table");
        if (length_keyword) {
            long long length = static_cast<long long>(recs.size());
            fits_update_key(f, TLONGLONG, const_cast<char*>("LENGTH"), &length,
                            const_cast<char*>("number of ATDB records"), &status);
            check(status, "write LENGTH");
        }
    };

    const std::string pform = std::to_string(pointers.size()) + "K";
    write_vector_hdu("POINTERS", pform.c_str(), TLONGLONG, pointers.data(), pointers.size(), true);
    const std::string rform = std::to_string(reals.size()) + "D";
    write_vector_hdu("REALS", rform.c_str(), TDOUBLE, reals.data(), reals.size(), false);
    const std::string iform = std::to_string(ints.size()) + "K";
    write_vector_hdu("INTEGERS", iform.c_str(), TLONGLONG, ints.data(), ints.size(), false);
    const std::string cform = std::to_string(chars.size()) + "B";
    write_vector_hdu("CHARS", cform.c_str(), TBYTE, chars.data(), chars.size(), false);

    fits_close_file(f, &status); check(status, "close file");
    std::cout << output << "\n";
    return 0;
}
