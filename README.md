# TaskbarStyler

A **standalone** version of the *Windows 11 Taskbar Styler* Windhawk mod. Run one
`.bat`, pick a theme, get the styling — no Windhawk, and nothing to install.

This is an independent port. It is not affiliated with, endorsed by, or
supported by Windhawk or the upstream mod author.

## What it does

Windows 11's taskbar is XAML, so it can be restyled from inside `explorer.exe`.
This project does that directly: a small engine DLL is injected into
`explorer.exe` and applies theme rules to the live taskbar visual tree.

```
inject.bat     inject the engine and style the taskbar
theme.bat      pick one of the 54 themes (numbered menu)
status.bat     what is injected, which theme, any conflict
eject.bat      revert the styling and remove the hooks
```

- **54 built-in themes** — the complete upstream theme pack, plus `None`.
- **Live switching** — change theme from `theme.bat`; no explorer restart.
- **Click-through taskbar** — optional, useful with dock-style themes.
- **Runs standalone** — one DLL and four batch files. No `.exe`, no installer, no
  background tray process, no runtime.

## Status

| Part | State |
| --- | --- |
| Theme pack extraction (`data/themes.json`) | **Done, machine-verified** — 54 themes, 2376 targets, 7149 styles |
| Engine DLL (`TaskbarStyler.dll`) | Not started — one binary, also its own injector |
| `.bat` control surface (`inject`/`eject`/`theme`/`status`) | Not started — replaces the tray host |
| Design / spec | [docs/SPEC.md](docs/SPEC.md) |
| Implementation plan | [docs/PLAN.md](docs/PLAN.md) |

**Build blocker:** the engine must be a native x64 DLL running inside
`explorer.exe` — there is no scripting or managed runtime alternative, so it has
to be compiled. No compiler exists on this machine (checked exhaustively), and
the local floor for one is ~2–3 GB, so the route is a **CI build that installs
nothing locally**. Delivery routes are compared in
[docs/SPEC.md §10](docs/SPEC.md#10-build-and-delivery-routes).

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
- `eject.bat` reverts the styling and removes the hooks without needing the
  engine to be in a working state, so a bad theme or config is always one command
  away from being undone.
- Windows Defender may flag the injection once. **No evasion techniques** are
  used; [docs/UNBLOCKING.md](docs/UNBLOCKING.md) covers the legitimate exclusion
  steps if you trust the source and want it to run.
- It cannot coexist with other XAML-diagnostics consumers such as TranslucentTB
  or ExplorerBlurMica. `status.bat` reports a conflict when it detects one; it will
  not quietly break the other program.
- No telemetry. The upstream mod's usage reporting is removed, not disabled.

## Licence

**GPL-3.0.** See [LICENSE](LICENSE).

This project is a derivative work of
[`m417z/my-windhawk-mods`](https://github.com/m417z/my-windhawk-mods)
(`windows-11-taskbar-styler` v1.10, © m417z, GPL-3.0). The upstream source is
retained in [mod/reference/](mod/reference/) with its original notices, and this
repository is the complete corresponding source for the binaries it ships.
