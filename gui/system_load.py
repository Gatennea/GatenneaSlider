# -*- coding: utf-8 -*-
"""系统整体负载探测（用于「空闲生成重启动画」的次级门禁）。

只依赖 ctypes 调 Windows kernel32.GetSystemTimes，不引入 psutil 等额外
依赖；非 Windows 平台返回 0.0（视为空闲，放行）。纯函数，便于单测打桩。
"""
import time


def system_cpu_busy(sample_ms=400):
    """采样系统 CPU 占用率（0.0~1.0）。两次 GetSystemTimes 间隔采样。

    返回 0.0~1.0；采样失败 / 非 Windows / 间隔过短返回 0.0（保守放行）。
    """
    if not hasattr(__import__('sys'), 'getwindowsversion'):
        # 非 Windows：无简单跨平台等价，保守放行
        return 0.0
    try:
        import ctypes
        kernel32 = ctypes.windll.kernel32

        class _FT(ctypes.Structure):
            _fields_ = [("dwLowDateTime", ctypes.c_uint32),
                        ("dwHighDateTime", ctypes.c_uint32)]

        idle, kernel, user = _FT(), _FT(), _FT()
        if not kernel32.GetSystemTimes(ctypes.byref(idle),
                                      ctypes.byref(kernel),
                                      ctypes.byref(user)):
            return 0.0

        def _to_int(ft):
            return (ft.dwHighDateTime << 32) | ft.dwLowDateTime

        i0, k0, u0 = _to_int(idle), _to_int(kernel), _to_int(user)
        time.sleep(max(50, sample_ms) / 1000.0)
        idle2, kernel2, user2 = _FT(), _FT(), _FT()
        kernel32.GetSystemTimes(ctypes.byref(idle2),
                               ctypes.byref(kernel2),
                               ctypes.byref(user2))
        i1, k1, u1 = _to_int(idle2), _to_int(kernel2), _to_int(user2)

        sys0, sys1 = (k0 + u0), (k1 + u1)
        total = sys1 - sys0
        busy = (sys1 - sys0) - (i1 - i0)
        if total <= 0:
            return 0.0
        return max(0.0, min(1.0, busy / total))
    except Exception:
        return 0.0
