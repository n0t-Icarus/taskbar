// SPDX-License-Identifier: GPL-3.0-or-later
// Derived from windows-11-taskbar-styler (c) m417z, GPL-3.0.

#include <windows.h>

// Task 0 skeleton. The engine itself arrives in Tasks 7-11: seven detours, the
// XAML-diagnostics consumer, and the style applier. For now this exists so that
// CI proves the whole pipeline end to end - configure, compile, link a x64 DLL,
// produce a usable export table - before any real behaviour depends on it.
//
// DllMain deliberately does nothing but decline thread notifications, so an
// accidental load into any process stays harmless.

extern "C" __declspec(dllexport) unsigned int TS_AbiVersion() {
    // Bumped only when the injected engine and the control surface disagree.
    return 1;
}

BOOL APIENTRY DllMain(HMODULE module, DWORD reason, LPVOID) {
    if (reason == DLL_PROCESS_ATTACH) {
        DisableThreadLibraryCalls(module);
    }
    return TRUE;
}
