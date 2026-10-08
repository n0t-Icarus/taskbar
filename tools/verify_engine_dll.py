#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Derived from windows-11-taskbar-styler (c) m417z, GPL-3.0.
"""Verify a downloaded TaskbarStyler.dll is the real, x64 engine.

Run this on the file you unzipped out of the CI artifact. It answers the three
questions that matter before you try to inject anything:

  1. Is this a 64-bit PE? Same-architecture is mandatory: a 32-bit DLL can never
     be loaded into 64-bit explorer.exe, and the failure mode (ERROR_BAD_EXE_FORMAT
     from a remote thread) is opaque.
  2. Is it a DLL, not an EXE?
  3. Does it export the control verbs the .bat files call?

Exit code 0 means pass; anything else means do not use this file.
"""

from __future__ import annotations

import argparse
import struct
import sys
from pathlib import Path

IMAGE_FILE_DLL = 0x2000

MACHINE_NAMES = {
    0x014C: "x86 (32-bit)",
    0x8664: "x64 (64-bit)",
    0xAA64: "ARM64",
    0x01C4: "ARM",
}

IMAGE_DIRECTORY_ENTRY_EXPORT = 0


class PeError(Exception):
    """The file is not a PE this checker can read."""


def _rva_to_offset(sections, rva: int) -> int | None:
    for va, vsize, raw_size, raw_ptr in sections:
        span = max(vsize, raw_size)
        if va <= rva < va + span:
            return raw_ptr + (rva - va)
    return None


def parse_pe(data: bytes) -> dict:
    if len(data) < 0x40 or data[:2] != b"MZ":
        raise PeError("not a Windows PE file (missing MZ signature)")

    pe_off = struct.unpack_from("<I", data, 0x3C)[0]
    if pe_off + 24 > len(data) or data[pe_off : pe_off + 4] != b"PE\0\0":
        raise PeError("not a Windows PE file (missing PE signature)")

    coff = pe_off + 4
    machine, n_sections = struct.unpack_from("<HH", data, coff)
    size_optional = struct.unpack_from("<H", data, coff + 16)[0]
    characteristics = struct.unpack_from("<H", data, coff + 18)[0]

    opt = coff + 20
    magic = struct.unpack_from("<H", data, opt)[0]
    if magic == 0x20B:
        pe_kind, dd_off = "PE32+", opt + 112
    elif magic == 0x10B:
        pe_kind, dd_off = "PE32", opt + 96
    else:
        raise PeError(f"unrecognised optional header magic 0x{magic:04X}")

    sections = []
    sec_off = opt + size_optional
    for i in range(n_sections):
        base = sec_off + i * 40
        if base + 40 > len(data):
            break
        vsize, va, raw_size, raw_ptr = struct.unpack_from("<IIII", data, base + 8)
        sections.append((va, vsize, raw_size, raw_ptr))

    export_dir_rva, export_dir_size = struct.unpack_from("<II", data, dd_off)
    exports = []
    if export_dir_rva:
        exports = _read_exports(data, sections, export_dir_rva)

    return {
        "machine": machine,
        "machine_name": MACHINE_NAMES.get(machine, f"unknown (0x{machine:04X})"),
        "pe_kind": pe_kind,
        "is_dll": bool(characteristics & IMAGE_FILE_DLL),
        "sections": n_sections,
        "export_rva": export_dir_rva,
        "export_size": export_dir_size,
        "exports": exports,
    }


def _read_exports(data: bytes, sections, export_rva: int) -> list[str]:
    off = _rva_to_offset(sections, export_rva)
    if off is None or off + 40 > len(data):
        return []

    # IMAGE_EXPORT_DIRECTORY is 40 bytes: 2 DWORDs, one DWORD holding the two
    # WORD versions, then 7 DWORDs. Counting it as 11 fields silently shifts
    # every field after TimeDateStamp by four bytes, which reads garbage as the
    # name-array pointer and yields a table of empty strings.
    (
        _characteristics,
        _timestamp,
        _versions,
        _name_rva,
        _base,
        n_functions,
        n_names,
        _addr_functions,
        addr_names,
        _addr_ordinals,
    ) = struct.unpack_from("<IIIIIIIIII", data, off)

    del n_functions  # only the name table is read here

    names_off = _rva_to_offset(sections, addr_names)
    if names_off is None or names_off + n_names * 4 > len(data):
        return []

    out = []
    for i in range(n_names):
        pos = names_off + i * 4
        if pos + 4 > len(data):
            break
        str_rva = struct.unpack_from("<I", data, pos)[0]
        str_off = _rva_to_offset(sections, str_rva)
        if str_off is None:
            continue
        end = data.find(b"\0", str_off)
        if end == -1:
            continue
        name = data[str_off:end].decode("ascii", "replace")
        if name:
            out.append(name)
    return sorted(out)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("dll", type=Path, help="path to TaskbarStyler.dll")
    ap.add_argument(
        "--expect-export",
        action="append",
        default=[],
        metavar="NAME",
        help="require this export to be present (repeatable)",
    )
    args = ap.parse_args()

    if not args.dll.is_file():
        print(f"FAIL: {args.dll} does not exist", file=sys.stderr)
        return 2

    data = args.dll.read_bytes()
    try:
        info = parse_pe(data)
    except PeError as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 2

    print(f"file       : {args.dll}")
    print(f"size       : {len(data):,} bytes")
    print(f"format     : {info['pe_kind']} / {info['machine_name']}")
    print(f"module type: {'DLL' if info['is_dll'] else 'EXE'}")
    print(f"sections   : {info['sections']}")
    print(f"exports    : {len(info['exports'])}")
    for name in info["exports"]:
        print(f"  - {name}")

    failures = []
    if info["machine"] != 0x8664:
        failures.append(
            f"must be x64 to load into 64-bit explorer.exe, got {info['machine_name']}"
        )
    if not info["is_dll"]:
        failures.append("must be a DLL, not an EXE")
    for want in args.expect_export:
        if want not in info["exports"]:
            failures.append(f"missing required export {want!r}")

    if failures:
        print()
        for line in failures:
            print(f"FAIL: {line}", file=sys.stderr)
        return 1

    print()
    print("OK: x64 DLL, safe to inject")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
