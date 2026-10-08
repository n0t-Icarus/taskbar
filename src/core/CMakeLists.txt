# SPDX-License-Identifier: GPL-3.0-or-later
# Derived from windows-11-taskbar-styler (c) m417z, GPL-3.0.

# Windows-free by rule (see docs/PLAN.md global constraints). CI greps this
# directory for Windows includes, and the build must work with no SDK present.
add_library(ts_core STATIC
    version.cpp
)

target_include_directories(ts_core PUBLIC "${CMAKE_CURRENT_SOURCE_DIR}")
target_link_libraries(ts_core PRIVATE ts_project_options)
