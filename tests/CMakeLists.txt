# SPDX-License-Identifier: GPL-3.0-or-later
# Derived from windows-11-taskbar-styler (c) m417z, GPL-3.0.

add_executable(ts_tests
    core/test_smoke.cpp
)

target_link_libraries(ts_tests PRIVATE ts_core doctest::doctest ts_project_options)

add_test(NAME ts_tests COMMAND ts_tests)
