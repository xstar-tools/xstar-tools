#include <algorithm>
#include <cmath>
#include <cstddef>
#include <cstring>
#include <exception>
#include <stdexcept>
#include <string>
#include <vector>

namespace {

struct SolveResult {
    std::vector<double> solution;
    std::vector<double> residual;
    double max_scaled_residual;
};

inline double& M(std::vector<double>& a, int n, int i, int j) {
    return a[static_cast<size_t>(i) * static_cast<size_t>(n) + static_cast<size_t>(j)];
}
inline const double& M(const std::vector<double>& a, int n, int i, int j) {
    return a[static_cast<size_t>(i) * static_cast<size_t>(n) + static_cast<size_t>(j)];
}

SolveResult leqt2f_kernel(const double* a_ptr, const double* b_ptr, int n, bool clamp) {
    if (a_ptr == nullptr || b_ptr == nullptr) {
        throw std::runtime_error("null input pointer in xstar_solver_leqt2f");
    }
    if (n <= 0) {
        throw std::runtime_error("xstar_solver_leqt2f requires n > 0");
    }
    const double tiny = 1.0e-20;
    std::vector<double> original(static_cast<size_t>(n) * static_cast<size_t>(n));
    std::vector<double> lu(static_cast<size_t>(n) * static_cast<size_t>(n));
    std::vector<double> rhs(static_cast<size_t>(n));
    std::memcpy(original.data(), a_ptr, original.size() * sizeof(double));
    std::memcpy(lu.data(), a_ptr, lu.size() * sizeof(double));
    std::memcpy(rhs.data(), b_ptr, rhs.size() * sizeof(double));

    std::vector<double> vv(static_cast<size_t>(n), 0.0);
    std::vector<int> pivots(static_cast<size_t>(n), 0);
    double d = 1.0;

    for (int i = 0; i < n; ++i) {
        double aamax = 0.0;
        for (int j = 0; j < n; ++j) {
            const double value = std::fabs(M(lu, n, i, j));
            if (value > aamax) aamax = value;
        }
        if (aamax == 0.0) {
            throw std::runtime_error("singular matrix row in C++ ludcmp: " + std::to_string(i + 1));
        }
        vv[static_cast<size_t>(i)] = 1.0 / aamax;
    }

    for (int j = 0; j < n; ++j) {
        if (j > 0) {
            for (int i = 0; i < j; ++i) {
                double total = M(lu, n, i, j);
                if (i > 0) {
                    for (int k = 0; k < i; ++k) {
                        total -= M(lu, n, i, k) * M(lu, n, k, j);
                    }
                    M(lu, n, i, j) = total;
                }
            }
        }
        double aamax = 0.0;
        int imax = -1;
        for (int i = j; i < n; ++i) {
            double total = M(lu, n, i, j);
            if (j > 0) {
                for (int k = 0; k < j; ++k) {
                    total -= M(lu, n, i, k) * M(lu, n, k, j);
                }
                M(lu, n, i, j) = total;
            }
            const double dum = vv[static_cast<size_t>(i)] * std::fabs(total);
            if (dum >= aamax) {
                imax = i;
                aamax = dum;
            }
        }
        if (imax < 0) imax = 0;
        if (j != imax) {
            for (int k = 0; k < n; ++k) {
                std::swap(M(lu, n, imax, k), M(lu, n, j, k));
            }
            d = -d;
            vv[static_cast<size_t>(imax)] = vv[static_cast<size_t>(j)];
        }
        pivots[static_cast<size_t>(j)] = imax;
        if (j != n - 1) {
            if (M(lu, n, j, j) == 0.0) M(lu, n, j, j) = tiny;
            const double dum = 1.0 / M(lu, n, j, j);
            for (int i = j + 1; i < n; ++i) M(lu, n, i, j) *= dum;
        }
    }
    if (n > 0 && M(lu, n, n - 1, n - 1) == 0.0) M(lu, n, n - 1, n - 1) = tiny;

    auto lubksb = [&](const std::vector<double>& in_b) -> std::vector<double> {
        std::vector<double> x = in_b;
        int ii = 0;
        for (int i = 0; i < n; ++i) {
            const int ll = pivots[static_cast<size_t>(i)];
            double total = x[static_cast<size_t>(ll)];
            x[static_cast<size_t>(ll)] = x[static_cast<size_t>(i)];
            if (ii != 0) {
                for (int jj = ii - 1; jj < i; ++jj) {
                    total -= M(lu, n, i, jj) * x[static_cast<size_t>(jj)];
                }
            } else if (total != 0.0) {
                ii = i + 1;
            }
            x[static_cast<size_t>(i)] = total;
        }
        for (int i = n - 1; i >= 0; --i) {
            double total = x[static_cast<size_t>(i)];
            if (i < n - 1) {
                for (int j = i + 1; j < n; ++j) {
                    total -= M(lu, n, i, j) * x[static_cast<size_t>(j)];
                }
            }
            x[static_cast<size_t>(i)] = total / M(lu, n, i, i);
        }
        return x;
    };

    std::vector<double> x = lubksb(rhs);

    std::vector<double> mprove_res(static_cast<size_t>(n), 0.0);
    for (int i = 0; i < n; ++i) {
        double sdp = -rhs[static_cast<size_t>(i)];
        for (int j = 0; j < n; ++j) {
            sdp += M(original, n, i, j) * x[static_cast<size_t>(j)];
        }
        mprove_res[static_cast<size_t>(i)] = sdp;
    }
    std::vector<double> correction = lubksb(mprove_res);
    for (int i = 0; i < n; ++i) {
        x[static_cast<size_t>(i)] -= correction[static_cast<size_t>(i)];
    }

    if (clamp) {
        for (int i = 0; i < n; ++i) {
            double& v = x[static_cast<size_t>(i)];
            if (v < 1.0e-36) v = 0.0;
            if (v > 1.0e36) v = 1.0e36;
        }
    }

    std::vector<double> residual(static_cast<size_t>(n), 0.0);
    double max_scaled = 0.0;
    for (int row = 0; row < n; ++row) {
        double total = 0.0;
        double tmpmx = 0.0;
        for (int col = 0; col < n; ++col) {
            const double btmp = x[static_cast<size_t>(col)];
            const double tmp = M(original, n, row, col) * std::max(0.0, btmp);
            if (std::fabs(tmp) >= tmpmx) tmpmx = std::max(tmpmx, std::fabs(tmp));
            total += tmp;
        }
        total -= rhs[static_cast<size_t>(row)];
        residual[static_cast<size_t>(row)] = total;
        const double err = total / std::max(1.0e-24, tmpmx);
        max_scaled = std::max(max_scaled, std::fabs(err));
    }
    return SolveResult{std::move(x), std::move(residual), max_scaled};
}

void write_error(char* err, size_t err_len, const std::string& msg) {
    if (err == nullptr || err_len == 0) return;
    const size_t ncopy = std::min(err_len - 1, msg.size());
    std::memcpy(err, msg.data(), ncopy);
    err[ncopy] = '\0';
}

} // namespace

extern "C" {

int xstar_solver_abi_version() {
    return 1;
}

const char* xstar_solver_backend_name() {
    return "xstar_solver_so_leqt2f_v1";
}

int xstar_solver_leqt2f(
    const double* a,
    const double* b,
    int n,
    int clamp,
    double* solution,
    double* residual,
    double* max_scaled_residual,
    char* error_message,
    size_t error_message_len
) {
    try {
        if (solution == nullptr || residual == nullptr || max_scaled_residual == nullptr) {
            throw std::runtime_error("null output pointer in xstar_solver_leqt2f");
        }
        SolveResult result = leqt2f_kernel(a, b, n, clamp != 0);
        std::memcpy(solution, result.solution.data(), result.solution.size() * sizeof(double));
        std::memcpy(residual, result.residual.data(), result.residual.size() * sizeof(double));
        *max_scaled_residual = result.max_scaled_residual;
        write_error(error_message, error_message_len, "");
        return 0;
    } catch (const std::exception& exc) {
        write_error(error_message, error_message_len, exc.what());
        return 1;
    } catch (...) {
        write_error(error_message, error_message_len, "unknown C++ exception in xstar_solver_leqt2f");
        return 2;
    }
}

} // extern "C"
