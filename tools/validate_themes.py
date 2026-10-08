#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Derived from windows-11-taskbar-styler (c) m417z, GPL-3.0.
"""Validate data/themes.json against the vendored upstream source.

This is the check that makes the extraction trustworthy: it re-derives the
theme set from the original GPLv3 mod source and asserts that every style
string in the JSON appears verbatim in that source, so nothing was invented,
truncated, or mis-associated during extraction.

Exit status is 0 only when every check passes.

Usage:
    python tools/validate_themes.py
"""

from __future__ import annotations

import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
THEMES_JSON = ROOT / "data" / "themes.json"
SOURCE = ROOT / "mod" / "reference" / "windows-11-taskbar-styler.wh.cpp"

failures: list[str] = []


def check(condition: bool, message: str) -> None:
    if not condition:
        failures.append(message)


def _escape_body(value: str, *, hex_upper: bool) -> str:
    parts: list[str] = []
    for ch in value:
        if ch == "\\":
            parts.append("\\\\")
        elif ch == '"':
            parts.append('\\"')
        elif ch == "\n":
            parts.append("\\n")
        elif ch == "\t":
            parts.append("\\t")
        elif ch == "\r":
            parts.append("\\r")
        elif 0x20 <= ord(ch) < 0x7F:
            parts.append(ch)
        elif ord(ch) <= 0xFFFF:
            parts.append(("\\u%04X" if hex_upper else "\\u%04x") % ord(ch))
        else:
            code = ord(ch) - 0x10000
            hi, lo = 0xD800 + (code >> 10), 0xDC00 + (code & 0x3FF)
            fmt = "\\u%04X\\u%04X" if hex_upper else "\\u%04x\\u%04x"
            parts.append(fmt % (hi, lo))
    return "".join(parts)


def literal_variants(value: str) -> list[str]:
    r"""Every spelling the upstream source could legitimately use for a value.

    C++ may spell non-ASCII either as ``\uXXXX`` escapes (uppercase or lowercase
    hex) or as the raw character in the source file, so accept any of them.
    """
    return [
        'L"' + _escape_body(value, hex_upper=True) + '"',
        'L"' + _escape_body(value, hex_upper=False) + '"',
        'L"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"',
    ]


def found_in_source(value: str, src: str) -> bool:
    return any(variant in src for variant in literal_variants(value))


def main() -> int:
    if not THEMES_JSON.is_file() or not SOURCE.is_file():
        print("error: run tools/extract_themes.py first", file=sys.stderr)
        return 2

    data = json.loads(THEMES_JSON.read_text(encoding="utf-8"))
    src = SOURCE.read_text(encoding="utf-8", errors="replace")
    themes = data["themes"]

    # --- theme set must cover every `const Theme g_...` in the source --------
    source_vars = set(re.findall(r"\bconst\s+Theme\s+(g_[A-Za-z0-9_]+)", src))
    json_vars: set[str] = set()
    for theme in themes:
        json_vars.add(theme["sourceVariable"])
        for variant in theme.get("autoVariants", []):
            json_vars.add(variant["sourceVariable"])
    check(
        source_vars == json_vars,
        f"theme object mismatch: missing={sorted(source_vars - json_vars)} "
        f"extra={sorted(json_vars - source_vars)}",
    )

    # --- unique ids, non-empty names ----------------------------------------
    ids = [t["id"] for t in themes]
    check(len(ids) == len(set(ids)), "duplicate theme ids in themes.json")
    check(all(t["name"] for t in themes), "a theme has an empty display name")

    # --- every style string must exist verbatim in the source ---------------
    total_styles = 0
    for theme in themes:
        for variant in theme.get("autoVariants", []):
            check(
                variant.get("selection") == "runtime",
                f"{variant['sourceVariable']}: auto-variant without runtime selection",
            )
        for ts in theme["targetStyles"]:
            check(bool(ts["target"]), f"{theme['id']}: empty target")
            check(bool(ts["styles"]), f"{theme['id']}: target {ts['target']!r} has no styles")
            for style in ts["styles"]:
                # An empty style string is legitimate upstream data: some targets
                # are listed with `L""` to clear a previously applied property.
                total_styles += 1
                if not found_in_source(style, src):
                    failures.append(f"{theme['id']}: style not found verbatim: {style!r}")
        for const in theme["styleConstants"]:
            check(
                found_in_source(const, src),
                f"{theme['id']}: style constant not found verbatim: {const!r}",
            )
        for res in theme["themeResourceVariables"]:
            check(
                found_in_source(res, src),
                f"{theme['id']}: resource variable not found verbatim: {res!r}",
            )

    # --- targets must also be verbatim --------------------------------------
    for theme in themes:
        for ts in theme["targetStyles"]:
            check(
                found_in_source(ts["target"], src),
                f"{theme['id']}: target not found verbatim: {ts['target']!r}",
            )

    # --- counted stats must match the payload -------------------------------
    target_count = sum(len(t["targetStyles"]) for t in themes)
    stats = data["stats"]
    check(stats["themeCount"] == len(themes), "stats.themeCount disagrees with themes[]")
    check(stats["targetCount"] == target_count, "stats.targetCount disagrees with themes[]")
    check(stats["styleCount"] == total_styles, "stats.styleCount disagrees with themes[]")

    # --- the mod advertises these themes in its settings block ---------------
    settings = re.search(r"- theme:.*?\$options:\n(.*?)(?=\n- \w|\Z)", src, re.S)
    advertised: set[str] = set()
    check(settings is not None, "could not locate the theme $options list in the source")
    if settings:
        for line in settings.group(1).splitlines():
            m = re.match(r"\s*-\s+(.*)$", line)
            if not m:
                continue
            body = m.group(1).strip()
            if body.endswith(">-"):
                # Folded scalar: the key is the part before the colon.
                key = body[:-2].strip().rstrip(":").strip()
            else:
                key = body.partition(":")[0].strip().strip('"')
            if key:
                advertised.add(key)
    check(
        advertised == set(ids),
        f"settings options disagree with themes.json: "
        f"only-in-settings={sorted(advertised - set(ids))} "
        f"only-in-json={sorted(set(ids) - advertised)}",
    )

    print(
        f"{len(themes)} themes, {target_count} targets, {total_styles} styles, "
        f"{sum(len(t.get('autoVariants', [])) for t in themes)} runtime variants"
    )
    if failures:
        print(f"\nFAILED ({len(failures)} problems):", file=sys.stderr)
        for f in failures[:40]:
            print(f"  - {f}", file=sys.stderr)
        if len(failures) > 40:
            print(f"  ... and {len(failures) - 40} more", file=sys.stderr)
        return 1

    print("OK: themes.json is faithful to the upstream source")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
