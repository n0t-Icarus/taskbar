// SPDX-License-Identifier: GPL-3.0-or-later
// Derived from windows-11-taskbar-styler (c) m417z, GPL-3.0.

#pragma once

#include <string_view>

namespace ts {

// This header, and everything else under src/core/, must stay free of every
// Windows header. The selector matcher, style parser and expression evaluator
// live here precisely so they can be built and tested without a Windows SDK.
inline constexpr std::string_view kProductName = "TaskbarStyler";
inline constexpr std::string_view kVersion = "0.1.0";

// Defined out of line so ts_core always has at least one translation unit.
std::string_view VersionString();

}  // namespace ts
