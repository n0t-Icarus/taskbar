# SPDX-License-Identifier: GPL-3.0-or-later
# Derived from windows-11-taskbar-styler (c) m417z, GPL-3.0.

cmake_minimum_required(VERSION 3.21)

project(TaskbarStyler
    VERSION 0.1.0
    DESCRIPTION "Standalone Windows 11 taskbar styler"
    LANGUAGES CXX)

# explorer.exe is a 64-bit process on every supported build of Windows 11, so a
# 32-bit engine could never be injected into it. Fail during configure rather
# than at MH_CreateHook time inside explorer.
if(NOT CMAKE_SIZEOF_VOID_P EQUAL 8)
    message(FATAL_ERROR
        "TaskbarStyler is x64-only: the engine is injected into 64-bit explorer.exe.")
endif()

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

# Static CRT: the engine is injected into explorer.exe, which does not ship the
# matching runtime DLL, and we have no business installing one.
set(CMAKE_MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>")

# All binaries land in one directory with no per-config subdirectory, so the CI
# artifact path is stable whatever generator is used.
foreach(_cfg "" _DEBUG _RELEASE _RELWITHDEBINFO _MINSIZEREL)
    set(CMAKE_RUNTIME_OUTPUT_DIRECTORY${_cfg} "${CMAKE_BINARY_DIR}/dist")
    set(CMAKE_LIBRARY_OUTPUT_DIRECTORY${_cfg} "${CMAKE_BINARY_DIR}/dist")
endforeach()

option(TS_BUILD_TESTS "Build the test suite" ON)
option(TS_WARNINGS_AS_ERRORS "Treat compiler warnings as errors" ON)

# Shared warning settings. /utf-8 is not cosmetic: the theme pack carries
# codepoint escapes such as \uE971, and the wrong source charset mangles them.
#
# Deliberately a plain if/else rather than generator expressions: an unquoted `;`
# inside `$<...>` splits into two malformed arguments at parse time, and every
# genex here would need quoting to be safe.
add_library(ts_project_options INTERFACE)

if(MSVC)
    target_compile_options(ts_project_options INTERFACE /W4 /permissive- /utf-8 /Zc:__cplusplus)
    if(TS_WARNINGS_AS_ERRORS)
        target_compile_options(ts_project_options INTERFACE /WX)
    endif()
else()
    target_compile_options(ts_project_options INTERFACE -Wall -Wextra -Wpedantic)
    if(TS_WARNINGS_AS_ERRORS)
        target_compile_options(ts_project_options INTERFACE -Werror)
    endif()
endif()

add_subdirectory(third_party/doctest)
add_subdirectory(src/core)

if(WIN32)
    add_subdirectory(src/engine)
endif()

if(TS_BUILD_TESTS)
    enable_testing()
    add_subdirectory(tests)
endif()
