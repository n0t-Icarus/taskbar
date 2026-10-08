# SPDX-License-Identifier: GPL-3.0-or-later
# Derived from windows-11-taskbar-styler (c) m417z, GPL-3.0.

# Single-header, vendored (see README.md for the pinned version and hash).
#
# SYSTEM: this is third-party code and we do not get to fix its warnings. Without
# it, the project's /W4 /WX would fail the build on someone else's header.
add_library(doctest INTERFACE)
target_include_directories(doctest SYSTEM INTERFACE "${CMAKE_CURRENT_SOURCE_DIR}")
add_library(doctest::doctest ALIAS doctest)
