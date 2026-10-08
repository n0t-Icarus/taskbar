#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Derived from windows-11-taskbar-styler (c) m417z, GPL-3.0.
"""Extract the built-in theme pack from the upstream Windhawk mod source.

Reads the vendored ``windows-11-taskbar-styler.wh.cpp`` and emits
``data/themes.json``: a language-neutral representation of every built-in
theme plus the mod's setting declarations.

This exists so the standalone port never has to hand-copy ~20k lines of
embedded C++ data, and so the port can be verified against a machine-checked
extraction rather than against a transcription.

Source is GPL-3.0; see mod/reference/ for the original and ../LICENSE.

Usage:
    python tools/extract_themes.py [--source PATH] [--out PATH]
"""

from __future__ import annotations

import argparse
import json
import pathlib
import re
import string
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
DEFAULT_SOURCE = ROOT / "mod" / "reference" / "windows-11-taskbar-styler.wh.cpp"
DEFAULT_OUT = ROOT / "data" / "themes.json"

ESCAPES = {
    "n": "\n",
    "t": "\t",
    "r": "\r",
    "\\": "\\",
    '"': '"',
    "'": "'",
    "0": "\0",
    "a": "\a",
    "b": "\b",
    "f": "\f",
    "v": "\v",
}


class ParseError(RuntimeError):
    pass


def read_string(src: str, i: int) -> tuple[str, int]:
    r"""Read a C++ string literal starting at the opening quote.

    Handles the escape forms the themes actually use, including ``\uXXXX``
    codepoint escapes (Segoe Fluent Icons glyphs such as ``Text=\uE971``).
    Dropping the backslash on those would silently corrupt the theme data.
    """
    assert src[i] == '"'
    i += 1
    out: list[str] = []
    while i < len(src):
        c = src[i]
        if c == "\\":
            nxt = src[i + 1] if i + 1 < len(src) else ""
            if nxt in ("u", "U"):
                width = 4 if nxt == "u" else 8
                digits = src[i + 2 : i + 2 + width]
                if len(digits) == width and all(d in string.hexdigits for d in digits):
                    code = int(digits, 16)
                    if code <= 0x10FFFF:
                        out.append(chr(code))
                        i += 2 + width
                        continue
                    raise ParseError(f"codepoint escape out of range: \\{nxt}{digits}")
            elif nxt == "x":
                j = i + 2
                while j < len(src) and src[j] in string.hexdigits:
                    j += 1
                if j > i + 2:
                    out.append(chr(int(src[i + 2 : j], 16)))
                    i = j
                    continue
            out.append(ESCAPES.get(nxt, nxt))
            i += 2
            continue
        if c == '"':
            return "".join(out), i + 1
        out.append(c)
        i += 1
    raise ParseError("unterminated string literal")


def tokenize(src: str, i: int) -> list[tuple[str, str | None]]:
    """Tokenize C++ into ('str'|'{'|'}'|','|'other') tokens.

    Comments and whitespace are dropped. Identifiers are kept as 'other' so the
    parser can tolerate aggregate type names such as ``ThemeTargetStyles``.
    """
    toks: list[tuple[str, str | None]] = []
    n = len(src)
    while i < n:
        c = src[i]
        if c in " \t\r\n":
            i += 1
            continue
        if c == "/" and src.startswith("//", i):
            j = src.find("\n", i)
            i = n if j < 0 else j + 1
            continue
        if c == "/" and src.startswith("/*", i):
            j = src.find("*/", i + 2)
            i = n if j < 0 else j + 2
            continue
        if c == '"':
            val, i = read_string(src, i)
            toks.append(("str", val))
            continue
        if c == "L" and i + 1 < n and src[i + 1] == '"':
            val, i = read_string(src, i + 1)
            toks.append(("str", val))
            continue
        if c in "{},":
            toks.append((c, None))
            i += 1
            continue
        if c == ";":
            toks.append((";", None))
            i += 1
            continue
        j = i
        while j < n and src[j] not in " \t\r\n{},;":
            j += 1
        toks.append(("other", src[i:j]))
        i = j
    return toks


def split_groups(toks: list[tuple[str, str | None]]) -> list[list[tuple[str, str | None]]]:
    """Split the body of a Theme initializer into its top-level brace groups.

    A Theme is ``{ {targetStyles}, {styleConstants}, {themeResourceVariables} }``
    with the two trailing groups optional.
    """
    if not toks or toks[0][0] != "{":
        raise ParseError("expected '{' opening Theme initializer")
    depth = 0
    groups: list[list[tuple[str, str | None]]] = []
    current: list[tuple[str, str | None]] | None = None
    for kind, _value in toks[1:]:
        if kind == "{":
            depth += 1
            if depth == 1:
                current = []
                continue
        elif kind == "}":
            depth -= 1
            if depth == 0:
                if current is not None:
                    groups.append(current)
                current = None
                continue
            if depth < 0:
                break
        if current is not None:
            current.append((kind, _value))
    return groups


def strings_by_depth(group: list[tuple[str, str | None]]) -> dict[int, list[str]]:
    """Map brace depth -> string literals found at that depth inside a group."""
    depth = 0
    found: dict[int, list[str]] = {}
    for kind, value in group:
        if kind == "{":
            depth += 1
        elif kind == "}":
            depth -= 1
        elif kind == "str":
            found.setdefault(depth + 1, []).append(value or "")
    return found


def parse_target_styles(group: list[tuple[str, str | None]]) -> list[dict]:
    """Pair each target with the styles vector that follows it.

    Inside the targetStyles group the token depth is:

        other(ThemeTargetStyles)          depth 0
        {                                 depth 1 now
        str(target)                       depth 1
        {                                 depth 2 now
        str(style)                        depth 2
        }                                 closing at depth 2 ends the entry
        }
    """
    entries: list[dict] = []
    depth = 0
    pending_target: str | None = None
    current_styles: list[str] | None = None
    for kind, value in group:
        if kind == "{":
            depth += 1
            if depth == 2:
                if pending_target is None:
                    raise ParseError("style vector opened before a target was seen")
                current_styles = []
            continue
        if kind == "}":
            if depth == 2:
                if pending_target is None:
                    raise ParseError("style vector closed with no pending target")
                entries.append({"target": pending_target, "styles": current_styles or []})
                pending_target = None
                current_styles = None
            depth -= 1
            if depth < 0:
                raise ParseError("unbalanced braces in targetStyles group")
            continue
        if kind == "str":
            if depth == 1:
                if pending_target is not None:
                    raise ParseError(f"target {value!r} seen while {pending_target!r} is still open")
                pending_target = value
            elif depth == 2 and current_styles is not None:
                current_styles.append(value or "")
    if depth != 0:
        raise ParseError("unbalanced braces in targetStyles group")
    if not entries:
        raise ParseError("no target styles parsed")
    return entries


def parse_theme_blocks(src: str) -> dict[str, dict]:
    """Return {'g_themeX': {targetStyles, styleConstants, themeResourceVariables}}."""
    themes: dict[str, dict] = {}
    for m in re.finditer(r"\bconst\s+Theme\s+(g_[A-Za-z0-9_]+)\s*=\s*\{", src):
        var = m.group(1)
        brace = src.index("{", m.end() - 1)
        toks = tokenize(src, brace)
        groups = split_groups(toks)
        if not groups:
            raise ParseError(f"{var}: no initializer groups found")
        target_styles = parse_target_styles(groups[0])
        constants = strings_by_depth(groups[1]).get(1, []) if len(groups) > 1 else []
        resources = strings_by_depth(groups[2]).get(1, []) if len(groups) > 2 else []
        themes[var] = {
            "targetStyles": target_styles,
            "styleConstants": constants,
            "themeResourceVariables": resources,
        }
    return themes


def parse_dispatch_branches(src: str) -> list[tuple[str, str]]:
    """Parse the ``wcscmp(themeName, L"...")`` chain into (key, branch body) pairs.

    Each branch body runs from the end of its ``wcscmp`` call to the start of the
    next one. Branches are keyed by the setting value, which is what the theme is
    selected by; the ``&g_themeX`` references inside the body tell us which C++
    theme object(s) that key resolves to.
    """
    pattern = re.compile(r'wcscmp\(\s*themeName\s*,\s*L"([^"]*)"\s*\)')
    matches = list(pattern.finditer(src))
    if not matches:
        raise ParseError("theme dispatch chain (wcscmp on themeName) not found")

    branches: list[tuple[str, str]] = []
    seen: dict[str, int] = {}
    for idx, m in enumerate(matches):
        key = m.group(1)
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(src)
        body = src[m.end() : end]
        if key in seen:
            # A second copy of the chain (e.g. a settings-changed path): merge the
            # variables it references into the branch we already recorded.
            prev_key, prev_body = branches[seen[key]]
            branches[seen[key]] = (prev_key, prev_body + body)
            continue
        seen[key] = len(branches)
        branches.append((key, body))
    return branches


def sanitize_key(key: str) -> str:
    """`Oversimplified&Accentuated` -> `Oversimplified_Accentuated`."""
    return re.sub(r"[^A-Za-z0-9_]", "_", key)


def resolve_name_map(
    themes_by_var: dict[str, dict],
    branches: list[tuple[str, str]],
    log: list[str],
) -> tuple[dict[str, str], dict[str, str]]:
    """Resolve (primary var -> key) and (auto-variant var -> key).

    By convention a key maps to ``g_theme<sanitized key>``. Where the upstream mod
    picks between two objects at runtime on an OS feature flag (see the Squircle
    branch) the other object is recorded as an auto-variant rather than a hole in
    the theme list.
    """
    primary_of: dict[str, str] = {}
    auto_of: dict[str, str] = {}

    for key, body in branches:
        referenced = re.findall(r"&(g_[A-Za-z0-9_]+)", body)
        guess = "g_theme" + sanitize_key(key)
        if guess in themes_by_var:
            primary = guess
        elif referenced:
            primary = referenced[0]
            log.append(
                f"note: key {key!r} has no g_theme{key} object; "
                f"using {primary} referenced in its branch"
            )
        else:
            raise ParseError(f"key {key!r}: branch references no theme object")

        if primary in primary_of and primary_of[primary] != key:
            raise ParseError(f"theme object {primary} claimed by two keys")
        primary_of[primary] = key

        for var in referenced:
            if var == primary or var not in themes_by_var or var in primary_of:
                continue
            auto_of[var] = primary
            log.append(f"note: {var} is a runtime auto-variant of {primary} (key {key!r})")

    accounted = set(primary_of) | set(auto_of)
    unaccounted = sorted(set(themes_by_var) - accounted)
    if unaccounted:
        raise ParseError(f"theme objects with no dispatch entry: {unaccounted}")

    return primary_of, auto_of


def parse_settings_options(src: str) -> dict[str, str]:
    """Parse the `- theme:` `$options:` list into modId -> display name."""
    block = re.search(r"==WindhawkModSettings==\n(.*?)\n// ==/WindhawkModSettings==", src, re.S)
    if not block:
        raise ParseError("WindhawkModSettings block not found")
    text = block.group(1)
    # Isolate the $options list that belongs to the `theme:` setting.
    opt = re.search(r"- theme:.*?\$options:\n(.*?)(?=\n- \w|\Z)", text, re.S)
    if not opt:
        raise ParseError("theme $options list not found")

    options: dict[str, str] = {}
    lines = opt.group(1).splitlines()
    pending_key: str | None = None
    for line in lines:
        item = re.match(r"\s*-\s*(.*)$", line)
        if item:
            body = item.group(1).strip()
            if body.endswith(">-"):
                pending_key = body[:-2].strip().rstrip(":")
                continue
            if ":" in body:
                key, _, name = body.partition(":")
                key, name = key.strip().strip('"'), name.strip()
                if name.startswith(">-"):
                    pending_key = key
                    continue
                options[key] = name or key
            pending_key = None
            continue
        # folded continuation of a `>-` value
        if pending_key is not None and line.strip():
            options[pending_key] = line.strip()
            pending_key = None
    return options


def build(src: str) -> dict:
    log: list[str] = []
    themes_by_var = parse_theme_blocks(src)
    primary_of, auto_of = resolve_name_map(
        themes_by_var, parse_dispatch_branches(src), log
    )
    options = parse_settings_options(src)

    missing = sorted(set(primary_of) - set(themes_by_var))
    if missing:
        raise ParseError(f"dispatch entries with no theme definition: {missing}")

    auto_by_primary: dict[str, list[str]] = {}
    for var, primary in auto_of.items():
        auto_by_primary.setdefault(primary, []).append(var)

    def body_of(var: str) -> dict:
        b = themes_by_var[var]
        return {
            "targetStyles": b["targetStyles"],
            "styleConstants": b["styleConstants"],
            "themeResourceVariables": b["themeResourceVariables"],
        }

    themes = []
    for var, mod_id in sorted(primary_of.items(), key=lambda kv: kv[1].lower()):
        entry = {
            "id": mod_id,
            "name": options.get(mod_id, mod_id),
            "sourceVariable": var,
        }
        entry.update(body_of(var))
        variants = auto_by_primary.get(var)
        if variants:
            entry["autoVariants"] = [
                {
                    "sourceVariable": v,
                    "selection": "runtime",
                    "reason": "chosen upstream by an OS feature check, not by the user",
                    **body_of(v),
                }
                for v in sorted(variants)
            ]
        themes.append(entry)
    themes.sort(key=lambda t: t["name"].lower())

    # Every option the mod offers must resolve to a real theme, except the
    # empty "None" entry which disables styling.
    option_ids = {k for k in options if k}
    missing_options = sorted(option_ids - set(primary_of.values()))
    if missing_options:
        raise ParseError(f"setting options with no theme object: {missing_options}")
    extra_ids = sorted(set(primary_of.values()) - option_ids)
    if extra_ids:
        raise ParseError(f"themes with no setting option: {extra_ids}")

    header_version = re.search(r"@version\s+(\S+)", src)
    header_author = re.search(r"@author\s+(\S+)", src)
    header_id = re.search(r"@id\s+(\S+)", src)

    empty = [t["id"] for t in themes if not t["targetStyles"]]
    if empty:
        raise ParseError(f"themes with no target styles: {empty}")

    total_targets = sum(len(t["targetStyles"]) for t in themes)
    total_styles = sum(len(ts["styles"]) for t in themes for ts in t["targetStyles"])

    return {
        "schemaVersion": 1,
        "generator": "tools/extract_themes.py",
        "source": {
            "modId": header_id.group(1) if header_id else None,
            "version": header_version.group(1) if header_version else None,
            "author": header_author.group(1) if header_author else None,
            "url": "https://github.com/m417z/my-windhawk-mods",
            "license": "GPL-3.0",
        },
        "stats": {
            "themeCount": len(themes),
            "variantCount": len(auto_of),
            "targetCount": total_targets,
            "styleCount": total_styles,
        },
        "notes": log,
        "themes": themes,
    }


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--source", type=pathlib.Path, default=DEFAULT_SOURCE)
    ap.add_argument("--out", type=pathlib.Path, default=DEFAULT_OUT)
    args = ap.parse_args(argv)

    if not args.source.is_file():
        print(f"error: source not found: {args.source}", file=sys.stderr)
        return 2

    data = build(args.source.read_text(encoding="utf-8", errors="replace"))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    stats = data["stats"]
    print(
        f"wrote {args.out}: {stats['themeCount']} themes, "
        f"{stats['variantCount']} auto-variants, "
        f"{stats['targetCount']} targets, {stats['styleCount']} styles"
    )
    for note in data["notes"]:
        print(note)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
