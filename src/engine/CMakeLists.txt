# SPDX-License-Identifier: GPL-3.0-or-later
# Derived from windows-11-taskbar-styler (c) m417z, GPL-3.0.

# The one shipped binary. Note it links the static CRT (set in the root
# CMakeLists) because it is injected into explorer.exe.
add_library(ts_engine SHARED
    dllmain.cpp
)

target_include_directories(ts_engine PRIVATE "${CMAKE_SOURCE_DIR}/src")
target_link_libraries(ts_engine PRIVATE ts_core ts_project_options)

set_target_properties(ts_engine PROPERTIES
    OUTPUT_NAME "TaskbarStyler"
)
