#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""_sw_win_probe.py — 不依赖 COM, 纯 win32gui 列出 SW 所有窗口 + 标题.
用于诊断 SW 是否被 modal dialog 卡住.
"""
import ctypes
import time
import os
from ctypes import wintypes

user32 = ctypes.windll.user32
psapi = ctypes.windll.psapi
kernel32 = ctypes.windll.kernel32

EnumWindowsProc = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)


def _get_pid(hwnd):
    pid = wintypes.DWORD(0)
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    return pid.value


def _get_proc_name(pid):
    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    h = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not h:
        return ""
    try:
        buf = ctypes.create_unicode_buffer(260)
        size = wintypes.DWORD(260)
        if kernel32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(size)):
            return os.path.basename(buf.value)
    finally:
        kernel32.CloseHandle(h)
    return ""


def _get_title(hwnd):
    length = user32.GetWindowTextLengthW(hwnd)
    if length == 0:
        return ""
    buf = ctypes.create_unicode_buffer(length + 1)
    user32.GetWindowTextW(hwnd, buf, length + 1)
    return buf.value


def _get_class(hwnd):
    buf = ctypes.create_unicode_buffer(256)
    user32.GetClassNameW(hwnd, buf, 256)
    return buf.value


def main():
    sw_windows = []
    all_windows = []

    def enum_proc(hwnd, _):
        pid = _get_pid(hwnd)
        proc = _get_proc_name(pid)
        title = _get_title(hwnd)
        cls = _get_class(hwnd)
        visible = bool(user32.IsWindowVisible(hwnd))
        enabled = bool(user32.IsWindowEnabled(hwnd))
        entry = (pid, proc, cls, title, visible, enabled, hwnd)
        all_windows.append(entry)
        if "SLDWORKS" in proc.upper() or "sldworks" in cls.lower():
            sw_windows.append(entry)
        return True

    user32.EnumWindows(EnumWindowsProc(enum_proc), 0)

    print("═══ SW 相关窗口 ═══")
    if not sw_windows:
        print("  (无 SW 进程拥有的窗口)")
    for pid, proc, cls, title, vis, en, hwnd in sw_windows:
        vmark = "V" if vis else "-"
        emark = "E" if en else "D"
        print(f"  [{vmark}{emark}] pid={pid} cls={cls!r} title={title!r}")

    print("\n═══ 所有顶层窗口 (top 20) ═══")
    for pid, proc, cls, title, vis, en, hwnd in all_windows[:20]:
        vmark = "V" if vis else "-"
        emark = "E" if en else "D"
        print(f"  [{vmark}{emark}] pid={pid:>5} proc={proc:<20} cls={cls[:32]:<32} title={title[:40]!r}")


if __name__ == "__main__":
    main()
