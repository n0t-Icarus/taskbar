# Standalone Windows 11 Taskbar Styler — Specification

Status: **approved design, ready to implement.** Nothing in this document is a
guess: the hook inventory, the theme pack, the settings schema and the required
Windhawk API surface were all mined from the vendored upstream source and
machine-validated (see [Verification](#9-verification)).

## 1. Goal

Ship the *Windows 11 Taskbar Styler* experience as a **standalone application**
that the user installs and runs directly, with **no Windhawk installation**.

Today the mod only runs under Windhawk, which supplies three things the mod
assumes: a DLL injector for `explorer.exe`, a `Wh_*` host API, and a settings UI.
This project reimplements those three things and drops the Windhawk dependency,
keeping the mod's actual styling engine and its 54 built-in themes.

### Non-goals (v1)

- No style-editor GUI. `config.json` is the advanced escape hatch and is edited
  by hand.
- No Start Menu Styler, Notification Center Styler, or any other Windhawk mod.
- No Windhawk usage-statistics reporting (see §4.4).
- No per-monitor or multi-user profile management.

## 2. Provenance and licensing

The engine is a **port of GPL-3.0 code**, so this project is a derivative work
and must ship under **GPL-3.0** with complete corresponding source.

| Item | Value |
| --- | --- |
| Upstream | `m417z/my-windhawk-mods`, mod id `windows-11-taskbar-styler` |
| Upstream version ported | 1.10 |
| Upstream author | m417z |
| Upstream licence | GNU General Public License v3.0 |
| Vendored copy | [mod/reference/windows-11-taskbar-styler.wh.cpp](mod/reference/windows-11-taskbar-styler.wh.cpp) |
| This project's licence | GPL-3.0 — [LICENSE](LICENSE) |

Obligations this creates, all satisfied by the repo layout in §3:

1. The whole of this project is GPL-3.0 (the DLL is a linked derivative work).
2. The original source and its copyright notice are retained verbatim in
   `mod/reference/`, and the original header is never stripped.
3. Complete corresponding source for the binaries we ship is this repository.
4. Every source file carries an SPDX header naming the upstream origin.

## 3. Deliverables and repo layout

```
TaskbarStyler.dll        engine; injected into explorer.exe; is also its own
                         injector and its own control surface
inject.bat               rundll32 TaskbarStyler.dll,Inject
eject.bat                rundll32 TaskbarStyler.dll,Eject
theme.bat                numbered theme menu -> writes config.json, signals reload
status.bat               rundll32 TaskbarStyler.dll,Status
data/themes.json         generated theme pack (language-neutral)
mod/reference/*.cpp      vendored upstream GPL-3.0 source
docs/SPEC.md             this document
docs/PLAN.md             implementation plan
tools/extract_themes.py  source -> themes.json
tools/validate_themes.py proves themes.json is faithful to the source
```

**One binary and four batch files. No `.exe`, no installer, no tray process and
no runtime — nothing to install in order to use it.** Copy the folder anywhere
and run `inject.bat`.

Windows already ships the loader this needs: `rundll32.exe` loads an x64 DLL and
calls a named export. In that process the DLL is an ordinary control program, and
its `Inject` export remote-thread-loads its own file into `explorer.exe`, where
`DllMain` sees it is running inside explorer and starts the engine. Mode is
chosen by host process name — `explorer.exe` means engine, `rundll32.exe` means
control.

## 4. Component: `TaskbarStyler.dll` (styling engine)

A native x64 DLL loaded inside `explorer.exe`. It is the upstream mod's logic
with the Windhawk host API replaced by the shim in §6.

### 4.1 Hooks — exactly seven, all on plain exported functions

Every target is resolved with `GetProcAddress`, so **no PDBs or symbol
resolution are required**, and the port survives Windows updates that recompile
explorer as long as these exports remain.

| # | Target | Module | Resolution | Purpose |
| --- | --- | --- | --- | --- |
| 1 | `CreateWindowExW` | `user32.dll` | direct | Detect the taskbar/tray window as it is created |
| 2 | `CreateWindowInBand` | `user32.dll` | `GetProcAddress`, optional | Early taskbar window creation hook |
| 3 | `CreateWindowInBandEx` | `user32.dll` | `GetProcAddress`, optional | As above, extended band parameter |
| 4 | `LoadLibraryExW` | `kernelbase.dll` | `GetProcAddress` | Catch `Windows.UI.Xaml.dll` load to install hook 7 |
| 5 | `RegOpenKeyExW` | `kernelbase.dll` | `GetProcAddress` | React to taskbar configuration changes |
| 6 | `RegQueryValueExW` | `kernelbase.dll` | `GetProcAddress` | Read taskbar registry state that drives styling |
| 7 | `InitializeXamlDiagnosticsEx` | `Windows.UI.Xaml.dll` | in-process, lazy | Register the XAML visual-tree consumer |

Hooks 2, 3 and 7 are *optional at runtime*: absence is logged and tolerated, not
fatal. Hole count differs across Windows builds.

### 4.2 Styling mechanism

The engine registers an `IVisualTreeWatcher` XAML-diagnostics consumer (the same
approach TranslucentTB uses) and receives the live taskbar visual tree. Each
theme is a list of `(target, styles)` pairs:

- **target** — a selector over the visual tree, e.g.
  `Taskbar.TaskbarFrame > Grid#RootGrid > Taskbar.TaskbarBackground`.
  Supports descendant combinators, `#Name`, `Type#Name`, attribute predicates
  (`[Text=...]`), and multiple comma-separated alternatives.
- **styles** — `Property=Value` (`Tag@DockedLeft=vertical` for state variants,
  `:=` for a XAML value), plus:
  - **constants** — `$name` references defined per theme
    (`CommonBgBrush=<WindhawkBlur BlurAmount="18" TintColor="#25323232"/>`),
  - **resource variables** — `{ThemeResource Key}` overrides, including
    theme-aware `Key@Dark` / `Key@Light`,
  - **expressions** — `{{ ... }}` evaluated against live values, e.g.
    `Width={{taskbarDock==`vertical`?skip():`Auto`}}`.

`WindhawkBlur`, the mod's custom brush, is retained as a real XAML type so
existing theme data keeps working unchanged.

### 4.3 Theme pack

54 selectable themes plus 1 runtime-selected variant (Squircle picks a different
object when an OS feature flag is set), totalling **2376 targets / 7149 styles**.

The pack is authored as `data/themes.json` (generated from the upstream source,
not transcribed) and compiled into the DLL, so the shipped product has no data
files to lose track of. A codegen step emits a C++ table from the JSON; the JSON
remains the single source of truth.

### 4.4 Deliberate deviations from upstream

- **Telemetry removed.** Upstream's `StartStatsTimer` posts usage stats through
  `Wh_GetUrlContent` / `Wh_GetBinaryValue` / `Wh_SetBinaryValue` /
  `Wh_GetModStoragePath`. All of it is deleted, not stubbed. Those shim symbols
  do not exist in this port.
- **XAML-diagnostics conflict handling is notify-only.** XAML diagnostics allows
  a single consumer, so this cannot coexist with TranslucentTB or
  ExplorerBlurMica. Upstream offers `alert` / `block` / `allow`; this port always
  behaves as *notify*: log it and record it for `status.bat` to report.  `block` actively breaks
  other apps and `alert` needs a popup raised from inside explorer, so neither is
  ported. The setting is still parsed for config compatibility, but
  `block`/`allow` are reported as unsupported and downgraded to notify.
- **No settings UI.** §7 replaces it.

## 5. Component: the `.bat` control surface

There is no host process. `TaskbarStyler.dll` exports its own control verbs and
`rundll32.exe` calls them, so the "app" is a handful of batch files.

| Verb | Invocation | Does |
| --- | --- | --- |
| `Inject` | `rundll32 TaskbarStyler.dll,Inject` | Remote-thread-loads the DLL into the current `explorer.exe` |
| `Eject` | `rundll32 TaskbarStyler.dll,Eject` | Signals the injected instance to revert styles, unhook and go inert |
| `SetTheme` | `rundll32 TaskbarStyler.dll,SetTheme LiquidGlass2` | Writes `config.json`, signals live reload |
| `Status` | `rundll32 TaskbarStyler.dll,Status` | Reports injected / theme / conflict / kill-switch state |

`theme.bat` renders the 54 themes plus `None` as a numbered `choice` menu and
calls `SetTheme` with the result, so choosing a theme never means editing JSON by
hand. Selecting one writes `config.json` and signals `Local\TaskbarStylerReload`;
styles are reverted and re-applied live, with **no explorer restart**.

The click-through and start-with-Windows toggles from the earlier tray design are
folded into `config.json` and the `Run` key respectively, both settable from
`theme.bat`'s menu.

Honest limits of having no host process:

1. **No automatic re-injection.** With nothing long-lived running there is no
   process to notice explorer restarting, so a restart needs `inject.bat` run
   again. If that grates, a Task Scheduler trigger on explorer start can run it —
   still no extra binary. This is a deliberate trade for having no background app.
2. **`Eject` deactivates, it does not unmap.** Unloading a DLL from a live
   explorer is far more fragile than injecting one, so `Eject` reverts styles,
   removes the hooks and leaves the module mapped but inert until explorer next
   restarts. In that state nothing is styled and nothing is hooked.
3. **No live indicator.** `status.bat` replaces the tray icon.

### 5.1 Open risk: loading the engine DLL under `rundll32`

Putting the control verbs and the engine in one DLL means `rundll32.exe` has to
load a module that also references C++/WinRT and the XAML types. Upstream already
resolves `InitializeXamlDiagnosticsEx` dynamically (§4.1, hook 7), so nothing
*statically* imports `Windows.UI.Xaml.dll` and the module should load fine in a
non-XAML host. **That is unverified, and it is the first thing Task 11 checks.**

If it does fail, the fallback costs a second DLL and still ships no `.exe`: move
the four control verbs into a small dependency-free `TaskbarStylerCtl.dll` for
`rundll32.exe` to load, and leave `TaskbarStyler.dll` as the pure engine.

## 6. Windhawk shim

The upstream mod needs remarkably little from Windhawk. This is the complete
surface, with real usage counts from the source:

| Symbol | Uses | Reimplementation |
| --- | --- | --- |
| `Wh_Log` | 211 | Rolling UTF-8 log file in `%LOCALAPPDATA%\TaskbarStyler\log.txt` |
| `Wh_GetStringSetting` | 7 | Read from parsed `config.json` |
| `Wh_GetIntSetting` | 1 | Read from parsed `config.json` |
| `Wh_FreeStringSetting` | 3 | Free the copy handed out by the getters |
| `Wh_GetModStoragePath` | 2 | Removed with telemetry (§4.4) |
| `Wh_GetUrlContent` / `Wh_FreeUrlContent` | 4 / 2 | Removed with telemetry |
| `Wh_GetBinaryValue` / `Wh_SetBinaryValue` | 2 / 1 | Removed with telemetry |
| `Wh_ModInit` / `Wh_ModAfterInit` | 1 / 1 | `DllMain` after attachment |
| `Wh_ModUninit` | 1 | `DllMain` detach; unhook and revert styles |
| `Wh_ModSettingsChanged` | 1 | Named-event listener `Local\TaskbarStylerReload` |
| `Wh_ApplyHookOperations` | 1 | No-op (MinHook applies hooks immediately) |
| `WindhawkUtils::SetFunctionHook` | 7 | MinHook `MH_CreateHook` + `MH_EnableHook` |
| `WindhawkUtils::SetWindowSubclassFromAnyThread` | 2 | Ported cross-thread subclass helper |
| `WindhawkUtils::RemoveWindowSubclassFromAnyThread` | 2 | Ported counterpart |

Logging stays file-based rather than a pipe back to the host, so a crash inside
explorer leaves evidence behind.

## 7. Configuration

`%APPDATA%\TaskbarStyler\config.json`, written by the host, read by the engine.
It mirrors the upstream settings schema exactly, so upstream theme
documentation keeps applying:

```jsonc
{
  "theme": "TranslucentTaskbar",
  "styleConstants": ["CommonBgBrush=<WindhawkBlur .../>"],
  "controlStyles": [{ "target": "...", "styles": ["..."] }],
  "themeResourceVariables": ["Key=Value", "Key@Dark=Value"],
  "clickThroughTaskbar": false,
  "xamlDiagnosticsHandling": "notify"
}
```

Unknown keys are preserved on rewrite; malformed JSON falls back to the last good
copy and logs.

## 8. Failure and safety model

Injection into `explorer.exe` and `.dll`-in-process hooking are inherently
risky, so:

1. **Exception containment** — every visual-tree callback is wrapped; a throw
   logs and unwinds instead of taking down explorer.
2. **Kill switch** — 3 explorer crashes within 60 s disables injection, records
   why, and reports it in the log and through `status.bat`. It does not silently
   keep trying.
3. **Always recoverable** — `Eject` needs nothing but the DLL and a running
   explorer, so a bad theme or a corrupt config is always one command away from
   being undone, whatever state the engine is in. `theme.bat` can then select
   *None*.
4. **Revert on unload** — exit reverts styles and removes all hooks.
5. **Honest AV posture** — `CreateRemoteThread` + `LoadLibrary` injection into
   explorer is normal for this class of tool but can trip Defender once. The
   README documents the legitimate unblock steps. **No evasion techniques.**
6. **GPL source availability** — a GPL licence does not permit hiding how this
   works, and none of the above depends on doing so.

## 9. Verification

### 9.1 Already done

The theme pack extraction is machine-verified: `tools/validate_themes.py`
re-derives the theme set from the upstream source and asserts every target, style,
constant and resource string in `themes.json` appears **verbatim** in the original
C++ (escapes included). This caught three real bugs during development — dropped
`\uXXXX` codepoint escapes, a mismapped dispatch key, and a wrongly-rejected
legitimate `L""` style. It currently passes:

```
54 themes, 2376 targets, 7149 styles, 1 runtime variants
OK: themes.json is faithful to the upstream source
```

### 9.2 Ladder for the port

1. **Pure logic, no explorer** — unit tests for the target matcher, the style
   parser (`$const`, `@state`, `:=`, `{{expr}}`) and the expression evaluator.
   These run in CI and on any machine.
2. **Shim conformance** — the shim is exercised against the real mod sources so a
   missing or wrong-signature symbol fails at build time, not at runtime inside
   explorer.
3. **On-machine manual pass** — `inject.bat`, then apply *TranslucentTaskbar* and
   screenshot-diff against the upstream mod's output; switch themes live with
   `theme.bat`; kill explorer, run `inject.bat` again and confirm the styling
   returns; select *None* and confirm a clean restore; `eject.bat` and confirm
   the hooks are gone.
4. **Soak** — 15 minutes with a theme switch every 60 s, watching memory, handle
   counts, and the log for contained exceptions.

A green build proves none of §9.2 steps 1–4.

## 10. Build and delivery routes

### 10.1 The part that cannot be avoided

Restyling the taskbar means changing XAML visual-tree properties *inside*
`explorer.exe`. The only mechanism that exposes that tree is the XAML
diagnostics channel — `InitializeXamlDiagnosticsEx` handing back an
`IVisualTreeService` through a callback object (§4). The mod reaches it by
*being* inside explorer and hooking seven exported functions (§4.1).

There is no out-of-process API for it. So one artifact is mandatory: **a native
x64 PE DLL that runs in `explorer.exe`.** No script, no managed runtime, and no
shell extension can stand in for it, because the code must live in explorer's
address space, speak the Windows ABI, and hook `user32`/`kernelbase` entry
points.

Prior art confirms this is the shape of the problem, not an artefact of this
port: Windhawk, ExplorerPatcher, StartAllBack and Start11 all ship a native
injected module.

The question therefore splits into three separate ones:

| Question | Answer |
|---|---|
| Must there be natively compiled code? | **Yes** — the engine DLL. |
| Must there be an `.exe`? | **No.** Something has to load the DLL, but it need not be an exe. |
| Must *you* build it on this machine? | **No.** |

### 10.2 Routes

**A — Build in CI (GitHub Actions, `windows-latest`).**
MSVC 2022 and the Windows SDK are preinstalled on the runner. Push, collect
`TaskbarStyler.dll` and `.exe` as downloadable artifacts. Nothing installed
locally, no elevation, no cost on a public repo (2,000 min/month when private).
Cost: no local compile feedback — an edit is verified by pushing.
Note that personal use is not distribution, so GPLv3 §6 only bites if the
binaries are handed to someone else.

**B — Install MSVC Build Tools locally (`winget`).**
`Microsoft.VisualStudio.2022.BuildTools` with only the *MSVC v143 x64 build
tools* component and one Windows 11 SDK: roughly **2–3 GB**, and it needs
elevation. That is the local floor. The 8–10 GB figure is the full IDE, which is
*not* required. Dropping under 1 GB would mean giving up C++/WinRT for
hand-written raw COM vtables so MinGW could compile it, which is a rewrite of
every XAML interaction in the mod — more risk than the port itself, not
recommended. Benefit: the normal edit-build-test loop, and §9.2's on-machine
steps become runnable at all.

**C — Rust + `windows-rs` on `x86_64-pc-windows-gnu` (no MSVC).**
`rustup` is present but has no toolchain; installing one is user-local and needs
no elevation. The GNU target avoids the MSVC linker entirely.
Cost, and it is steep: this is a **rewrite, not a port**. The mod is C++/WinRT,
so the COM interfaces, the vtable callbacks and the hook layer would all be new
Rust (`retour`/`detour` in place of MinHook). On top of that, recent
`windows`/`windows-sys` crates moved onto `raw-dylib`, whose GNU-target support
I have **not** verified. Treat C as a hypothesis to test, not a plan.

**D — Don't port anything: drive Windhawk.**
Windhawk already injects into explorer and already implements this engine. An
installer script that installs Windhawk, adds the mod, and writes the chosen
theme into Windhawk's config delivers all 54 themes with **zero compiled code**.
Cost: Windhawk stays installed — precisely what you asked to remove — and there
is no settings UI of our own. It is, however, the only route that puts styled
themes on the taskbar today, so it is worth holding as a fallback.

**E — `.NET 8` C# control app + CI-built DLL. Dropped.**
This was live while the plan still had a tray host. With the `.bat` control
surface (§5) there is no host process left to write in C#, so the route buys
nothing and costs a second toolchain.

**F — PowerShell + `Add-Type` as host and injector. Rejected.**
`Add-Type` can compile C# in memory and P/Invoke `CreateRemoteThread` +
`LoadLibraryW`, so this is technically possible with no compiler installed at
all. But PowerShell-driven DLL injection is a catalogued attack signature
(MITRE T1055.001) with named detections in Defender and Elastic. Shipping that
as a desktop app is volunteering for an AV incident. Recorded here only so the
option is visibly considered and refused.

### 10.3 Current state and recommendation

No compiler exists on this machine. Verified exhaustively rather than sampled: no
`cl.exe`, `link.exe`, `clang-cl`, `g++`, `cmake` or `ninja` anywhere under
`C:\Program Files`, `C:\Program Files (x86)` or `C:\ProgramData`, nor anywhere on
`D:` to a depth of 8. No Windows SDK under `Program Files (x86)\Windows Kits\10`.
No `gh`. rustup is installed with no toolchain. **Windhawk is not installed
either** — so its bundled mod compiler, the one thing on a Windhawk machine that
could have built this for free, is not available. `rundll32.exe` is present and
is x64, which is what §5's no-exe design rests on. The only toolchain present is
.NET 8 SDK 8.0.424.

Recommendation, in order:

1. **A — CI.** Zero bytes installed, MSVC and the Windows SDK are already on the
   runner, and the downloaded artifact is ready to use with `inject.bat`. This is
   the only route that fully satisfies "nothing heavy".
2. **B — a temporary local install.** ~2–3 GB, install, build, uninstall. Worth it
   only if A's push-and-wait loop proves too slow, or once §9.2 step 3's
   on-machine pass needs iterating.
3. **D — driving Windhawk.** No longer a build route, since Windhawk is not
   installed here; it survives only as an option if the goal shifts back to
   "styled taskbar now, without a port".

Independent of the route: the theme pack (§4.3) and its validation tooling are
complete and verified *now*, because they depend only on Python.

### 10.4 Additional dependencies

The upstream mod was built by Windhawk's own build system, so its includes were
implicit. This port vendors them, and every addition is recorded here rather
than discovered in a linker error.

| Dependency | Purpose | Licence |
|---|---|---|
| MinHook | The 7 `SetFunctionHook` detours (§4.1) | BSD-2-Clause |
| C++/WinRT headers | `IVisualTreeService` and the XAML types | MIT |
| doctest | Core unit tests (§9.2) | MIT |
| `nlohmann/json` | Parsing `data/themes.json` (§4.3) | MIT |

All four are permissive and GPL-compatible. Anything not in this table must be
added here before it is used.

### 10.5 Rejected alternative: MinGW-w64 (measured)

MinGW-w64 is the obvious way to dodge the MSVC download. It is roughly 300 MB,
needs no elevation, and the sibling project `taskbar-volume-control` already
builds a native Win32 exe with COM, DWM and GDI+ that way
(`g++ ... -lole32 -loleaut32 -luuid -ldwmapi -lshcore`). That is a working
precedent for the shape of this engine, so the option deserves a number rather
than a shrug.

The blocker is C++/WinRT, and as of this measurement it is counted, not assumed:

| Metric | Value |
| --- | --- |
| Distinct `winrt/` headers | 20 |
| `#include <winrt/...>` lines | 22 |
| `winrt::` call sites | **397** |
| `winrt::impl::abi_t` (deep internals) | 22 |

That distribution is more favourable than the raw count suggests:
`IInspectable` (32 uses) and `IPropertyValue` (25) are plain COM interfaces,
`hstring` (40) and `hresult_error` (39) have trivial raw replacements, and
`xamlom.h` — the XAML-diagnostics header the engine actually talks to — is pure
C COM rather than WinRT. The genuinely WinRT-only runtime classes are few:
`Uri` (6), `UISettings` (4), `DispatcherQueue` (4), `DispatcherQueueTimer` (4).

It is still 397 call sites, a rewrite larger and riskier than the port itself,
and `winrt::implements` / `auto_revoke` event revocation is fiddly to hand-roll
correctly. **Conclusion: not worth it.** CI costs nothing and removes the need
entirely.

One trap if this is ever revisited: the non-MSVC branch of the root
`CMakeLists.txt` sets `-Werror`, and the common Win32 idiom
`WNDCLASSEXW wc{ sizeof(wc) }` trips `-Wmissing-field-initializers` under GCC.
That warning is noise (the braces do zero the rest of the struct), but it would
fail the build. The branch is currently unexercised because CI compiles with
MSVC and `src/core` is the only thing that can build without a SDK.
