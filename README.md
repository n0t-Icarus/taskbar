# TaskbarStyler

A **standalone** version of the *Windows 11 Taskbar Styler* Windhawk mod. Run one
app, pick a theme, get the styling — no Windhawk installation required.

This is an independent port. It is not affiliated with, endorsed by, or
supported by Windhawk or the upstream mod author.

## What it does

Windows 11's taskbar is XAML, so it can be restyled from inside `explorer.exe`.
This project does that directly: a small engine DLL is injected into
`explorer.exe` and applies theme rules to the live taskbar visual tree.

- **54 built-in themes** — the complete upstream theme pack, plus `None`.
- **Live switching** — change theme from the tray; no explorer restart.
- **Click-through taskbar** — optional, useful with dock-style themes.
- **Runs standalone** — no Windhawk, no additional runtime.

## Status

| Part | State |
| --- | --- |
| Theme pack extraction (`data/themes.json`) | **Done, machine-verified** — 54 themes, 2376 targets, 7149 styles |
| Engine DLL (`TaskbarStyler.dll`) | Not started — blocked on a C++ toolchain, see below |
| Tray host (`TaskbarStyler.exe`) | Not started |
| Design / spec | [docs/SPEC.md](docs/SPEC.md) |
| Implementation plan | [docs/PLAN.md](docs/PLAN.md) |

**Build blocker:** the engine must be a native x64 DLL running inside
`explorer.exe` — there is no scripting or managed runtime alternative. No
native toolchain is installed on this machine. Six delivery routes (CI build,
local MSVC, Rust/GNU, driving Windhawk, .NET host, and one rejected) are
compared in [docs/SPEC.md §10](docs/SPEC.md#10-build-and-delivery-routes).

## Theme data

`data/themes.json` is generated from the upstream GPL-3.0 source, never
hand-transcribed, and validated against it:

```sh
python tools/extract_themes.py    # source -> data/themes.json
python tools/validate_themes.py   # prove every style string is verbatim upstream
```

The validator fails the build on drift, so the theme pack cannot silently
diverge from the code it was extracted from.

## Safety

This tool injects a DLL into `explorer.exe` and hooks a handful of Win32 exports
inside it. That is the only way to do what it does, and it is worth being blunt
about the risks:

- A bug can crash or hang the taskbar. The engine contains exceptions, reverts
  styles on unload, and stops injecting after 3 explorer crashes in 60 s.
- Launching with **Shift held** starts the tray only, with no injection — use
  this if a bad theme or config ever needs undoing.
- Windows Defender may flag the injection once. **No evasion techniques** are
  used; see the README section on unblocking if you trust the source and want it
  to run.
- It cannot coexist with other XAML-diagnostics consumers such as TranslucentTB
  or ExplorerBlurMica. The app will tell you when it detects a conflict; it will
  not quietly break the other program.
- No telemetry. The upstream mod's usage reporting is removed, not disabled.

## Licence

**GPL-3.0.** See [LICENSE](LICENSE).

This project is a derivative work of
[`m417z/my-windhawk-mods`](https://github.com/m417z/my-windhawk-mods)
(`windows-11-taskbar-styler` v1.10, © m417z, GPL-3.0). The upstream source is
retained in [mod/reference/](mod/reference/) with its original notices, and this
repository is the complete corresponding source for the binaries it ships.
