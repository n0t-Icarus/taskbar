# Standalone Taskbar Styler Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship the Windows 11 Taskbar Styler as a standalone tray app with its own injector and 54 built-in themes, running without Windhawk.

**Architecture:** A native x64 engine DLL is injected into `explorer.exe`. It installs 7 `GetProcAddress`-based detours, registers a XAML-diagnostics visual-tree consumer, and applies theme rules to the live taskbar tree. A Win32 tray host owns the injector, the config, and explorer liveness. The engine's decision-making core (selector matching, style parsing, expression evaluation) is deliberately Windows-free so it can be unit-tested without explorer.

**Tech Stack:** C++20, MSVC x64 (MSBuild generator or Ninja), CMake ≥ 3.21, MinHook, C++/WinRT headers, doctest (vendored single header, MIT), Python 3 for the theme-data generator.

**Spec:** [docs/SPEC.md](SPEC.md) — read it with this plan.

## Global Constraints

- **Licence:** GPL-3.0. Every new source file starts with `// SPDX-License-Identifier: GPL-3.0-or-later` and `// Derived from windows-11-taskbar-styler (c) m417z, GPL-3.0.`
- **No telemetry.** Never implement `Wh_GetUrlContent`, `Wh_GetBinaryValue`, `Wh_SetBinaryValue`, or `Wh_GetModStoragePath`.
- **No evasion.** No AV bypass, no manual-mapping, no PEB unlinking, no code obfuscation.
- **x64 only.** `explorer.exe` is x64; do not add 32-bit build paths.
- **Windows API floor:** Windows 11 (build 22000+). No downlevel shims.
- **Engine locale:** engine logging is UTF-8 on disk regardless of system codepage.
- **`src/core/` must not include any Windows header** — not even `<windows.h>`. It must compile and test on a machine with no SDK.
- **No new dependency** may be added without recording it in `docs/SPEC.md §10.4`.
- **Theme data is generated, never hand-edited.** `data/themes.json` is the source of truth; `tools/validate_themes.py` must pass.

## Review Focus

The five failure modes most likely to bite a user, each of which no task's tests
fully exercise on their own:

1. **Explorer restart while a theme is applied** — the user restarts explorer
   (or it crashes) and comes back to a *default* taskbar with no indication
   anything is wrong. Expected: styles reappear within a few seconds.
2. **`explorer.exe` re-creating the taskbar window without the process
   restarting** — e.g. after a resolution or DPI change, the old window is gone
   and the new one is unstyled. Expected: still styled.
3. **Config JSON that a human broke by hand** — a trailing comma or a wrong type.
   Expected: last-known-good config used, error logged, app still starts.
4. **A theme whose target matches nothing on this Windows build** — expected:
   the rest of the theme still applies and the unmatched target is logged once,
   not once per repaint.
5. **Two themes with overlapping targets, switched in sequence** — properties set
   by the first theme must be reverted, or colours leak across a switch.
   Expected: after switching to `None`, the taskbar is indistinguishable from
   never having run.

---

### Task 0: Toolchain bootstrap and build skeleton

**Files:**
- Create: `CMakeLists.txt`, `CMakePresets.json`, `cmake/toolchain-msvc-x64.cmake`, `third_party/doctest/doctest.h`, `.gitignore`
- Create: `src/core/CMakeLists.txt`, `tests/CMakeLists.txt`, `tests/core/test_smoke.cpp`

**Interfaces:**
- Consumes: nothing.
- Produces: CMake target `ts_core` (static lib, Windows-free), `ts_engine` (DLL), `ts_host` (exe), `ts_tests` (exe). Preset `msvc-x64`.

This task exists to fail fast if the toolchain is missing (see SPEC §10.3).

- [ ] **Step 1: Confirm the toolchain**

Run: `cmake --version` and `cl 2>&1 | head -1` from a *Developer Command Prompt*
Expected: CMake ≥ 3.21 and `Microsoft (R) C/C++ Optimizing Compiler`. If either is
missing, stop and report the blocker — do not write engine code.

- [ ] **Step 2: Vendor doctest**

Download the single header to `third_party/doctest/doctest.h` and record
SHA-256 in `third_party/doctest/README.md`. Confirm the banner is MIT.

- [ ] **Step 3: Write the smoke test**

```cpp
// tests/core/test_smoke.cpp
#define DOCTEST_CONFIG_IMPLEMENT_WITH_MAIN
#include <doctest/doctest.h>
TEST_CASE("tests run") { CHECK(1 + 1 == 2); }
```

- [ ] **Step 4: Configure, build and run**

Run: `cmake --preset msvc-x64 && cmake --build --preset msvc-x64 && ctest --preset msvc-x64 --output-on-failure`
Expected: build succeeds, `1 test case passed`.

- [ ] **Step 5: Commit**

```bash
git add CMakeLists.txt CMakePresets.json cmake third_party src tests .gitignore
git commit -m "build: add C++20 CMake skeleton with doctest and core/engine/host targets"
```

---

### Task 1: Generate the compiled-in theme pack

**Files:**
- Create: `tools/generate_theme_data.py`
- Create: `src/core/generated/theme_data.h`, `src/core/generated/theme_data.cpp` (generated)
- Modify: `src/core/CMakeLists.txt`, `tools/validate_themes.py`
- Test: `tools/test_generate_theme_data.py`

**Interfaces:**
- Consumes: `data/themes.json` (schema v1, produced by `tools/extract_themes.py`).
- Produces, in `ts::generated`:
  - `struct ThemeTargetStylesDef { const wchar_t* target; const wchar_t* const* styles; size_t styleCount; };`
  - `struct ThemeDef { const wchar_t* id; const wchar_t* name; const ThemeTargetStylesDef* targetStyles; size_t targetStyleCount; const wchar_t* const* styleConstants; size_t styleConstantCount; const wchar_t* const* themeResourceVariables; size_t themeResourceVariableCount; const ThemeDef* autoVariants; size_t autoVariantCount; };`
  - `extern const ThemeDef kThemes[]; extern const size_t kThemeCount;`

- [ ] **Step 1: Write the failing test**

```python
# tools/test_generate_theme_data.py
def test_generated_pack_round_trips(tmp_path):
    # generate from data/themes.json, then parse the generated .cpp back and
    # assert counts and three spot values match the JSON exactly
```

Assert on: `kThemeCount == 54`, the theme with id `LiquidGlass2` has the same
target count as the JSON, and the style `L"Text=\uE971 ..."` (the codepoint
escape) survives as the real character `\uE971` rather than `uE971`.

- [ ] **Step 2: Run it and watch it fail**

Run: `python tools/test_generate_theme_data.py`
Expected: FAIL — generator does not exist.

- [ ] **Step 3: Implement the generator**

Emit `wchar_t` literals with `\uXXXX` / `\UXXXXXXXX` escapes for non-ASCII, and
the `kBuiltInThemes`-style tables above. Escape `"` and `\`. Emit a comment
naming the source hash so drift is visible in diffs.

- [ ] **Step 4: Verify**

Run: `python tools/test_generate_theme_data.py && python tools/generate_theme_data.py && python tools/validate_themes.py`
Expected: all pass; `validate_themes.py` still reports `54 themes, 2376 targets, 7149 styles`.

- [ ] **Step 5: Commit**

```bash
git add tools/generate_theme_data.py tools/test_generate_theme_data.py src/core/generated src/core/CMakeLists.txt
git commit -m "feat(core): generate compiled-in theme pack from validated themes.json"
```

---

### Task 2: Target selector parser and matcher

**Files:**
- Create: `src/core/target_selector.h`, `src/core/target_selector.cpp`
- Test: `tests/core/test_target_selector.cpp`
- Modify: `src/core/CMakeLists.txt`, `tests/CMakeLists.txt`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `class VisualNode { public: virtual ~VisualNode() = default; virtual std::wstring TypeName() const = 0; virtual std::wstring Name() const = 0; virtual bool TryGetAttribute(std::wstring_view key, std::wstring* out) const = 0; virtual VisualNode* Parent() const = 0; };`
  - `struct AttributePredicate { std::wstring name; std::wstring value; };`
  - `struct SelectorPart { std::wstring type; std::wstring name; std::vector<AttributePredicate> attributes; bool childOfPrevious; };`
  - `struct TargetSelector { std::vector<std::vector<SelectorPart>> alternatives; };`
  - `std::optional<TargetSelector> ParseTargetSelector(std::wstring_view text, std::wstring* error);`
  - `bool MatchesTarget(const TargetSelector& selector, const VisualNode* node);`
- Alignment requirement: this matcher must accept every one of the 2376 targets
  in `data/themes.json`. That set is the corpus, and Task 2's test loads it.

- [ ] **Step 1: Write the failing tests**

Cases, taken from real themes in `data/themes.json`:
- `Taskbar.TaskbarFrame > Grid#RootGrid` matches a `Grid` named `RootGrid` whose
  parent is `Taskbar.TaskbarFrame`; fails when the parent differs.
- `StackPanel#SystemTrayFrameGrid, Grid#SystemTrayFrameGrid` matches either
  alternative.
- `TextBlock#InnerTextBlock[Text=]` requires the attribute predicate, and fails
  when the attribute is absent.
- `Grid#DynamicSearchBoxGleamContainer` matches by name regardless of type when
  the type part is absent.
- `Taskbar.TaskbarBackground#HoverFlyoutBackgroundControl > Grid > Rectangle#BackgroundFill`
  is a three-level chain and must not match a two-level near miss.

Plus a corpus test: parse every target in `data/themes.json` (read via a
test-only path constant) and assert zero parse failures.

- [ ] **Step 2: Run and watch them fail**

Run: `ctest --preset msvc-x64 -R target_selector --output-on-failure`
Expected: FAIL — `ParseTargetSelector` undefined.

- [ ] **Step 3: Implement**

Split on `,` for alternatives, then on ` > ` for child relations and on a bare
space for descendant relations, then parse `Type#Name` and `[Attr=Value]`. Match
right-to-left from the node upwards so a chain is satisfied by the nearest
ancestor. Nearest-match wins, as upstream.

- [ ] **Step 4: Verify**

Run: `ctest --preset msvc-x64 -R target_selector --output-on-failure`
Expected: PASS, including `2376 targets parsed, 0 failures`.

- [ ] **Step 5: Commit**

```bash
git add src/core/target_selector.* tests/core/test_target_selector.cpp src/core/CMakeLists.txt tests/CMakeLists.txt
git commit -m "feat(core): parse and match XAML target selectors"
```

---

### Task 3: Style declaration parser

**Files:**
- Create: `src/core/style_declaration.h`, `src/core/style_declaration.cpp`
- Test: `tests/core/test_style_declaration.cpp`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `enum class StyleValueKind { Property, XamlValue };`
  - `struct StyleDeclaration { std::wstring property; std::vector<std::wstring> states; StyleValueKind kind; std::wstring value; };`
  - `std::optional<StyleDeclaration> ParseStyleDeclaration(std::wstring_view text, std::wstring* error);`
- `states` comes from `@` suffixes; upstream uses both single states
  (`Background@ActivePointerOver`) and compound ones
  (`Background@ActivePressed_SearchIcon`), so keep the raw suffix list.

- [ ] **Step 1: Write the failing tests**

Every case below is a real string from `data/themes.json`:
- `Fill:=$CommonBgBrush` → property `Fill`, kind `XamlValue`, value `$CommonBgBrush`.
- `Visibility=Collapsed` → kind `Property`.
- `CornerRadius=14` and `Padding=3,4,3,4` → values kept verbatim, commas intact.
- `Background@ActivePointerOver:=<SolidColorBrush Color="$activeColor" Opacity="0.5"/>`
  → states `[ActivePointerOver]`, kind `XamlValue`, `<`/`>` and quotes preserved.
- `Tag=>taskbarDock` → value `>taskbarDock` (the *first* `=` terminates the property).
- `Background:=<WindhawkBlur BlurAmount="18" TintColor="#25323232"/>` → not split on the `=` inside quotes.
- `Width={{taskbarDock==`vertical`?skip():`Auto`}}` → value kept whole; `==` inside `{{}}` must not terminate the property.
- Empty string `""` → parses to a declaration with an empty property (upstream uses
  this to clear a property); assert it is accepted, not an error.
- A corpus test over all 7149 style strings: zero unexpected failures.

- [ ] **Step 2: Run and watch them fail**

Run: `ctest --preset msvc-x64 -R style_declaration --output-on-failure`
Expected: FAIL.

- [ ] **Step 3: Implement**

Scan left to right tracking `{{`/`}}` nesting and double-quoted regions; the
first `=` or `:=` outside both terminates the property-and-state part.

- [ ] **Step 4: Verify**

Run: `ctest --preset msvc-x64 -R style_declaration --output-on-failure`
Expected: PASS, including `7149 style strings parsed`.

- [ ] **Step 5: Commit**

```bash
git add src/core/style_declaration.* tests/core/test_style_declaration.cpp
git commit -m "feat(core): parse property, state and XAML-value style declarations"
```

---

### Task 4: Expression evaluator

**Files:**
- Create: `src/core/expression.h`, `src/core/expression.cpp`
- Test: `tests/core/test_expression.cpp`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `struct EvalValue { enum class Kind { Null, String, Number, Bool }; static EvalValue Skip(); bool IsSkip() const; ... };`
  - `struct EvalContext { std::function<std::optional<EvalValue>(std::wstring_view)> lookup; };`
  - `class Expression { public: static std::optional<Expression> Parse(std::wstring_view body, std::wstring* error); EvalValue Evaluate(const EvalContext& ctx) const; };`
  - `Expression` parses the *inside* of `{{ }}`; callers strip the braces.
- Backticks are string literals in this grammar (upstream writes
  `` `vertical` ``), and `skip()` yields the skipped sentinel rather than a value.

- [ ] **Step 1: Write the failing tests**

Real expressions from `data/themes.json`:
- `` taskbarDock==`vertical`?skip():`Auto` `` with `taskbarDock` = `vertical` →
  `IsSkip()` is true; with `left` → string `Auto`.
- `` max(68, min(90, (AltTabHeight / 5) * 1.75)) `` with `AltTabHeight` = 40 →
  `min(90, 14)` = 14 → `max(68, 14)` = 68.
- `` (AltTabHeight / 5) * 1.75 `` with `AltTabHeight` = 41 → 14.35 (assert the
  documented rounding, whatever Task 4 chooses, and pin it in the test).
- A false condition with two string branches selects the second branch.
- An unknown identifier evaluates to Null rather than throwing.
- Unbalanced parentheses → `Parse` returns `nullopt` with a non-empty error.

- [ ] **Step 2: Run and watch them fail**

Run: `ctest --preset msvc-x64 -R expression --output-on-failure`
Expected: FAIL.

- [ ] **Step 3: Implement**

Recursive-descent: ternary → logical → comparison → additive → multiplicative →
unary → primary, with `min`, `max`, `skip`, and bare identifiers resolved through
`EvalContext::lookup`.

- [ ] **Step 4: Verify**

Run: `ctest --preset msvc-x64 -R expression --output-on-failure`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/core/expression.* tests/core/test_expression.cpp
git commit -m "feat(core): evaluate {{ }} style expressions"
```

---

### Task 5: Theme registry and constant resolution

**Files:**
- Create: `src/core/theme_registry.h`, `src/core/theme_registry.cpp`, `src/core/constant_resolver.h`, `src/core/constant_resolver.cpp`
- Test: `tests/core/test_theme_registry.cpp`

**Interfaces:**
- Consumes: `ts::generated::kThemes`/`kThemeCount` (Task 1); `StyleDeclaration` (Task 3).
- Produces:
  - `const ts::generated::ThemeDef* FindTheme(std::wstring_view id);`
  - `std::vector<std::wstring_view> ThemeIds();`
  - `class ConstantResolver { public: void Add(std::wstring_view declaration);  // "name=value" std::optional<std::wstring> Resolve(std::wstring_view name) const; };`
  - `ConstantResolver BuildResolver(const std::vector<std::wstring>& userStyleConstants, const ts::generated::ThemeDef& theme);`

- [ ] **Step 1: Write the failing tests**

- `FindTheme(L"TranslucentTaskbar")` is non-null and `FindTheme(L"None")` is null.
- `ThemeIds()` has 54 entries and contains `LiquidGlass2` and `Oversimplified&Accentuated`.
- `BuildResolver` with the theme's own constants resolves `CommonBgBrush` to the
  `WindhawkBlur` string, and a user constant with the same name overrides it.
- Resolving an unknown constant returns `nullopt` (not empty string), so callers
  can log "unknown constant" once.
- `g_themeSquircle`'s auto-variant is reachable and has a different target count
  from its parent.

- [ ] **Step 2: Run and watch them fail**

Run: `ctest --preset msvc-x64 -R theme_registry --output-on-failure`
Expected: FAIL.

- [ ] **Step 3: Implement**

Thin lookups over the generated tables. `BuildResolver` applies user constants
after theme constants so user wins, matching upstream.

- [ ] **Step 4: Verify**

Run: `ctest --preset msvc-x64 -R theme_registry --output-on-failure`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/core/theme_registry.* src/core/constant_resolver.* tests/core/test_theme_registry.cpp
git commit -m "feat(core): registry lookup and style-constant resolution"
```

---

### Task 6: Windhawk shim — logging and settings

**Files:**
- Create: `src/shim/windhawk_api.h`, `src/shim/wh_log.cpp`, `src/shim/wh_settings.cpp`, `src/shim/wh_settings.h`
- Create: `src/shim/config.h`, `src/shim/config.cpp`
- Test: `tests/shim/test_config.cpp`

**Interfaces:**
- Consumes: nothing Windows-free-portable beyond Win32 (this shim is Windows-only).
- Produces:
  - The `Wh_*` declarations the ported mod code calls: `Wh_Log`, `Wh_Log` variadic
    form, `Wh_GetStringSetting`, `Wh_GetIntSetting`, `Wh_FreeStringSetting`.
    No telemetry symbols (Global Constraints).
  - `struct AppSettings { std::wstring theme; std::vector<std::wstring> styleConstants; std::vector<ControlStyle> controlStyles; std::vector<std::wstring> themeResourceVariables; bool clickThroughTaskbar; std::string xamlDiagnosticsHandling; };`
  - `std::optional<AppSettings> ParseConfigJson(std::string_view utf8, std::wstring* error);`
  - `std::wstring ConfigPath();` → `%APPDATA%\TaskbarStyler\config.json`
  - `std::wstring LogPath();` → `%LOCALAPPDATA%\TaskbarStyler\log.txt`

- [ ] **Step 1: Write the failing tests**

- Parses the SPEC §7 example verbatim; every field round-trips.
- Missing `theme` → defaults to empty (None), no error.
- Malformed JSON (trailing comma) → returns `nullopt` with a non-empty error, and
  **does not throw**.
- `xamlDiagnosticsHandling` of `block` or `allow` parses but a following
  `NormalizeXamlDiagnosticsHandling` downgrades both to `notify` and reports the
  downgrade (SPEC §4.4).
- Unknown keys are preserved by `SerializeConfigJson` (write-then-read round trip).
- The UTF-8→UTF-16 conversion handles the `\uE971` private-use character.

- [ ] **Step 2: Run and watch them fail**

Run: `ctest --preset msvc-x64 -R config --output-on-failure`
Expected: FAIL.

- [ ] **Step 3: Implement**

Use `nlohmann/json` (already recorded in SPEC §10.4) for parsing, and hand-write the
serializer so key order and unknown keys are preserved.

- [ ] **Step 4: Verify**

Run: `ctest --preset msvc-x64 -R config --output-on-failure`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/shim tests/shim
git commit -m "feat(shim): config-backed Wh_* settings shim and logging"
```

---

### Task 7: Detour wrapper and the seven hooks

**Files:**
- Create: `src/engine/hooks.h`, `src/engine/hooks.cpp`, `src/engine/dllmain.cpp`
- Modify: `CMakeLists.txt`
- Test: `tests/engine/test_hooks.cpp` (host-side, exercises only the resolution table)

**Interfaces:**
- Consumes: `src/shim/windhawk_api.h`.
- Produces:
  - `bool InstallHooks(); void RemoveHooks();`
  - A resolution table mirroring SPEC §4.1 exactly, in this order:
    `CreateWindowExW`, `CreateWindowInBand`, `CreateWindowInBandEx`,
    `LoadLibraryExW`, `RegOpenKeyExW`, `RegQueryValueExW`,
    `InitializeXamlDiagnosticsEx`.
  - `struct HookInstallReport { int installed; int unavailable; std::vector<std::wstring> missing; };`
  - `HookInstallReport LastHookInstallReport();`

- [ ] **Step 1: Write the failing test**

- `LastHookInstallReport()` is defined and its `missing` list names only hooks
  that are genuinely absent (assert `CreateWindowExW` and `LoadLibraryExW` are
  never reported missing on this machine).
- Assert `InstallHooks()` is idempotent: calling it twice reports the same
  installed count, not double the hooks.

- [ ] **Step 2: Run and watch it fail**

Run: `ctest --preset msvc-x64 -R hooks --output-on-failure`
Expected: FAIL.

- [ ] **Step 3: Implement**

MinHook: `MH_Initialize`, one `MH_CreateHook` per resolvable export,
`MH_EnableHook(MH_ALL_HOOKS)`. Hooks 2/3/7 log and skip when unresolved
(SPEC §4.1). `dllmain.cpp` runs `Wh_ModInit` on attach and `Wh_ModUninit` on
detach, and must not do hook work under the loader lock beyond what upstream does.

- [ ] **Step 4: Verify**

Run: `ctest --preset msvc-x64 -R hooks --output-on-failure`
Expected: PASS. Then confirm manually that injecting the DLL into a scratch
process does not crash it and writes a log line.

- [ ] **Step 5: Commit**

```bash
git add src/engine tests/engine CMakeLists.txt
git commit -m "feat(engine): MinHook detours for the seven taskbar exports"
```

---

### Task 8: Visual-tree consumer and style applier

**Files:**
- Create: `src/engine/visual_tree_watcher.h`, `src/engine/visual_tree_watcher.cpp`, `src/engine/style_applier.h`, `src/engine/style_applier.cpp`, `src/engine/windhawk_blur.h`
- Test: `tests/engine/test_style_applier.cpp`

**Interfaces:**
- Consumes: `TargetSelector` (Task 2), `StyleDeclaration` (Task 3), `Expression` (Task 4), `ConstantResolver` (Task 5).
- Produces:
  - `class StyleApplier { public: void Apply(const ts::generated::ThemeDef& theme, const AppSettings& settings); void RevertAll(); size_t AppliedRuleCount() const; };`
  - `struct AppliedStyle { VSMP_PROPERTYKEY property; EvalValue value; };` — the
    recorded set `RevertAll` needs to undo a theme.
  - `void OnVisualTreeChanged(IVisualTreeWatcher*, IInspectable*, VisualTreeChangeType);`

- [ ] **Step 1: Write the failing tests**

Against a fake `VisualNode` tree shaped like a real taskbar:
- Applying `SimplyTransparent` sets `Fill` to `Transparent` on
  `Rectangle#BackgroundFill` and on `Rectangle#BackgroundStroke`.
- `RevertAll()` after that leaves both properties unset — the peer case for
  Review Focus #5.
- Applying `DockLike` then `None` leaves no residual properties (same focus).
- A theme target that matches nothing increments a
  `UnmatchedTargetCount()` and logs exactly once, not once per apply — Review
  Focus #4.
- An expression producing `skip()` results in **no** property being written.

- [ ] **Step 2: Run and watch them fail**

Run: `ctest --preset msvc-x64 -R style_applier --output-on-failure`
Expected: FAIL.

- [ ] **Step 3: Implement**

Resolve constant references, evaluate expressions, translate `WindhawkBlur` into
the real brush type, and write properties via the XAML API — recording every
write in a revert log. Port the sibling `WindhawkBlur` brush from upstream.

- [ ] **Step 4: Verify**

Run: `ctest --preset msvc-x64 -R style_applier --output-on-failure`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/engine tests/engine/test_style_applier.cpp
git commit -m "feat(engine): apply and revert theme styles on the live taskbar tree"
```

---

### Task 9: XAML diagnostics consumer and taskbar discovery

**Files:**
- Create: `src/engine/xaml_diagnostics.h`, `src/engine/xaml_diagnostics.cpp`, `src/engine/taskbar_window.h`, `src/engine/taskbar_window.cpp`

**Interfaces:**
- Consumes: Task 7's `InitializeXamlDiagnosticsEx` detour, Task 8's `OnVisualTreeChanged`.
- Produces:
  - `bool RegisterVisualTreeConsumer();` — returns false when another consumer
    holds the single XAML-diagnostics slot.
  - `enum class ConflictState { None, OtherConsumerDetected };`
  - `ConflictState CurrentConflictState();`
  - `HWND FindTaskbarWindow();`

- [ ] **Step 1: Write the failing test**

- `RegisterVisualTreeConsumer()` returns a bool, and calling it twice does not
  leak a second registration.
- `CurrentConflictState()` starts as `None` in a scratch process and flips to
  `OtherConsumerDetected` when the slot is pre-taken — simulate the pre-taken
  case by stubbing the COM activation, since we cannot install TranslucentTB in
  a test.

- [ ] **Step 2: Run and watch it fail**

Run: `ctest --preset msvc-x64 -R xaml_diagnostics --output-on-failure`
Expected: FAIL.

- [ ] **Step 3: Implement**

Port the `IVisualTreeWatcher` consumer and the `InitializeXamlDiagnosticsEx`
handshake from upstream, including the `CLSID_WindhawkTAP` → local CLSID rename.
Notify-only on conflict (SPEC §4.4): log and set `CurrentConflictState()`, never
block or unregister another process's consumer.

- [ ] **Step 4: Verify**

Run: `ctest --preset msvc-x64 -R xaml_diagnostics --output-on-failure`
Expected: PASS, then a manual pass: inject into a real explorer and confirm the
log shows a taskbar window found and a watcher attached.

- [ ] **Step 5: Commit**

```bash
git add src/engine/xaml_diagnostics.* src/engine/taskbar_window.*
git commit -m "feat(engine): register XAML diagnostics consumer and find the taskbar"
```

---

### Task 10: Live reload, lifecycle and safety

**Files:**
- Create: `src/engine/reload_channel.h`, `src/engine/reload_channel.cpp`, `src/engine/safety.h`, `src/engine/safety.cpp`
- Test: `tests/engine/test_safety.cpp`, `tests/host/test_reload_channel.cpp`

**Interfaces:**
- Consumes: `ParseConfigJson` (Task 6), `StyleApplier` (Task 8).
- Produces:
  - `constexpr wchar_t kReloadEventName[] = L"Local\\TaskbarStylerReload";`
  - `bool SignalReload();` (host side) and `bool StartReloadListener();` (engine side).
  - `enum class KillSwitchState { Clear, Tripped };`
  - `class CrashTracker { public: void RecordExplorerExit(bool crashed); KillSwitchState State() const; };` — 3 crashes in 60 s trips it.
  - `bool IsSafeModeRequested();` — true when Shift is held at host start.

- [ ] **Step 1: Write the failing tests**

- `CrashTracker`: two crashes inside 60 s → `Clear`; three → `Tripped`.
- Three crashes spread over 5 minutes → `Clear`.
- `SignalReload()` then `StartReloadListener()` receives exactly one notification.
- Exceptions thrown from a style callback are caught, logged, and counted —
  `ContainedExceptionCount()` increments and the process stays alive.
- A malformed config on reload keeps the previously applied theme applied
  (Review Focus #3).

- [ ] **Step 2: Run and watch them fail**

Run: `ctest --preset msvc-x64 -R "safety|reload_channel" --output-on-failure`
Expected: FAIL.

- [ ] **Step 3: Implement**

Named event (`CreateEventW`/`SetEvent`/`WaitForSingleObject`), crash tracking by
recording explorer exit times, `__try`/`__except`-equivalent containment around
every callback, and reload that reverts then re-applies.

- [ ] **Step 4: Verify**

Run: `ctest --preset msvc-x64 -R "safety|reload_channel" --output-on-failure`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/engine/reload_channel.* src/engine/safety.* tests/engine tests/host
git commit -m "feat(engine): live theme reload, crash kill switch and safe mode"
```

---

### Task 11: Tray host

**Files:**
- Create: `src/host/main.cpp`, `src/host/tray_icon.h`, `src/host/tray_icon.cpp`, `src/host/injector.h`, `src/host/injector.cpp`, `src/host/explorer_watcher.h`, `src/host/explorer_watcher.cpp`, `src/host/config_store.h`, `src/host/config_store.cpp`
- Test: `tests/host/test_injector.cpp`, `tests/host/test_explorer_watcher.cpp`

**Interfaces:**
- Consumes: `ParseConfigJson`/`SerializeConfigJson` (Task 6), `SignalReload()` (Task 10), generated theme list (Task 1).
- Produces:
  - `bool InjectDllIntoProcess(DWORD pid, const std::wstring& dllPath, std::wstring* error);`
  - `class ExplorerWatcher { public: void Start(std::function<void(DWORD pid)> onStart, std::function<void()> onExit); void Stop(); };`
  - `bool WriteThemeSelection(const std::wstring& themeId, std::wstring* error);`
  - `bool SetRunAtLogon(bool enabled, std::wstring* error);`

- [ ] **Step 1: Write the failing tests**

- `WriteThemeSelection` changes only `theme` and preserves every other key,
  including unknown ones.
- `WriteThemeSelection` rejects an id not in `ts::generated::kThemes`.
- `ExplorerWatcher` fires `onStart` with a fresh explorer PID after the watched
  process exits — the peer case for Review Focus #1.
- `SetRunAtLogon(false)` then `(true)` is idempotent and writes to the per-user
  `Run` key only (assert nothing under `HKLM` is touched).

- [ ] **Step 2: Run and watch them fail**

Run: `ctest --preset msvc-x64 -R "injector|explorer_watcher" --output-on-failure`
Expected: FAIL.

- [ ] **Step 3: Implement**

Tray via `Shell_NotifyIconW` with a menu built from `kThemes` plus `None`.
Injection via `OpenProcess`/`VirtualAllocEx`/`WriteProcessMemory`/
`CreateRemoteThread(LoadLibraryW)`. Single-instance via a named mutex;
a second launch exits quietly.

- [ ] **Step 4: Verify**

Run: `ctest --preset msvc-x64 -R "injector|explorer_watcher" --output-on-failure`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/host tests/host
git commit -m "feat(host): tray UI, DLL injector and explorer liveness watcher"
```

---

### Task 12: End-to-end pass, packaging and GPL compliance

**Files:**
- Create: `docs/TESTING.md`, `docs/UNBLOCKING.md`, `installer/build.ps1`
- Modify: `README.md`, `docs/SPEC.md` (record new dependencies in §10.4)

**Interfaces:**
- Consumes: every previous task.
- Produces: a `dist/` folder with `TaskbarStyler.exe`, `TaskbarStyler.dll`, and `LICENSE`.

- [ ] **Step 1: Write the manual test script**

Author `docs/TESTING.md` as the exact checklist from SPEC §9.2 steps 3–4, with
what to look at and what a failure looks like. Confirm the first two must be done
on a real Windows 11 machine.

- [ ] **Step 2: Run the ladder**

Run: `ctest --preset msvc-x64 --output-on-failure`
Expected: all pass. Then: apply `TranslucentTaskbar` and screenshot-diff against
the upstream Windhawk mod's output; switch themes live; kill explorer and confirm
re-styling; select `None` and confirm a clean restore; run the 15-minute soak.
Record each result in `docs/TESTING.md` with a date — including any that fail.

- [ ] **Step 3: Write the AV unblocking doc**

`docs/UNBLOCKING.md` documents the legitimate Defender exclusion steps and states
plainly what the tool does that triggers it. No evasion content (Global Constraints).

- [ ] **Step 4: Verify GPL compliance**

Confirm every source file has the SPDX header, `LICENSE` is present in `dist/`,
`mod/reference/` retains the upstream notices unmodified, and the README names
upstream. Run: `grep -rL "SPDX-License-Identifier" src tools | grep -v generated`
Expected: no output.

- [ ] **Step 5: Commit**

```bash
git add docs README.md installer dist
git commit -m "docs: testing ladder, AV unblocking guide and GPL compliance pass"
```
