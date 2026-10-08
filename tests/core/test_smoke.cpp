// SPDX-License-Identifier: GPL-3.0-or-later
// Derived from windows-11-taskbar-styler (c) m417z, GPL-3.0.

#define DOCTEST_CONFIG_IMPLEMENT_WITH_MAIN
#include <doctest/doctest.h>

#include "version.h"

TEST_CASE("tests run") {
    CHECK(1 + 1 == 2);
}

// Proves ts_core is actually linked, not just present, so a broken library
// target cannot pass the suite by contributing nothing.
TEST_CASE("core links and reports its version") {
    CHECK(ts::VersionString() == "0.1.0");
    CHECK(ts::kProductName == "TaskbarStyler");
}
