// SPDX-License-Identifier: GPL-2.0-or-later
#pragma once
#include <cstdlib>
#include <filesystem>
#include <string>
inline std::filesystem::path BbAtlasPath(const char* name,std::filesystem::path fallback={}) {
#ifdef _WIN32
    const std::wstring wide_name(name,name+std::char_traits<char>::length(name));
    const wchar_t* value=_wgetenv(wide_name.c_str());
    return value&&*value?std::filesystem::path(value):fallback;
#else
    const char* value=std::getenv(name);return value&&*value?std::filesystem::path(value):fallback;
#endif
}
