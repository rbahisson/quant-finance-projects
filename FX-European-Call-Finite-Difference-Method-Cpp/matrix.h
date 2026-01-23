// matrix.h
#pragma once
#include <vector>

template <typename T>
using matrix = std::vector<std::vector<T>>;

template <typename T>
inline void matrix_resize(matrix<T>& m, int rows, int cols, const T& val = T()) {
    m.assign(rows, std::vector<T>(cols, val));
}

