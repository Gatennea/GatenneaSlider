# -*- coding: utf-8 -*-
"""
宏定义功能 HTTP 测试脚本

前提：游戏已启动且 HTTP 服务运行在 127.0.0.1:5050
用法：D:/python/python.exe macro/test_macro_http.py
"""

import requests
import time
import sys

BASE = "http://127.0.0.1:5050"


def req(method, path, body=None, timeout=15):
    """发送请求并返回 JSON"""
    url = BASE + path
    try:
        if method == "GET":
            r = requests.get(url, timeout=timeout)
        else:
            r = requests.post(url, json=body or {}, timeout=timeout)
        return r.json()
    except requests.exceptions.ConnectionError:
        print(f"[FAIL] 无法连接 {url}，请确认游戏已启动")
        sys.exit(1)
    except Exception as e:
        print(f"[FAIL] 请求异常: {e}")
        return {"ok": False, "message": str(e)}


def check(expected_ok, resp, desc):
    """检查响应是否符合预期"""
    ok = resp.get("ok", False) == expected_ok
    status = "PASS" if ok else "FAIL"
    msg = resp.get("message", "")
    print(f"  [{status}] {desc}")
    if not ok:
        print(f"         期望 ok={expected_ok}, 实际 ok={resp.get('ok')}, message={msg}")
    return ok


def wait_anim():
    """等待动画完成"""
    time.sleep(0.8)


# ============================================================
# 测试开始
# ============================================================

print("=" * 60)
print("宏定义功能 HTTP 测试")
print("=" * 60)

# --- 0. 检查连接 ---
print("\n[0] 检查连接...")
resp = req("GET", "/status")
if "puzzle" not in resp:
    print(f"  [FAIL] /status 返回异常: {resp}")
    sys.exit(1)
print(f"  [PASS] 已连接, puzzle={resp['puzzle']}")

# --- 1. 创建新谜题并打乱 ---
print("\n[1] 准备环境：创建 4x4 step=2 谜题并打乱...")
check(True, req("POST", "/new", {"m": 4, "n": 4, "step": 2}), "创建新谜题 4x4 step=2")
time.sleep(0.5)
check(True, req("POST", "/shuffle"), "打乱")
wait_anim()

# --- 2. 列出宏（应为空） ---
print("\n[2] 列出宏（应为空）...")
resp = req("GET", "/macro/list")
check(True, resp, "macro_list 返回 ok=True")
macros = resp.get("macros", [])
print(f"         当前宏数: {len(macros)}")
assert len(macros) == 0, "初始宏列表应为空"

# --- 3. 录制宏 ---
print("\n[3] 录制宏流程...")
resp = req("POST", "/macro/record/start")
check(True, resp, "开始录制")

# 选择基准 (0,0)
resp = req("POST", "/macro/record/set_base", {"row": 0, "col": 0})
check(True, resp, "设置基准 (0,0)")

# 执行一步操作：选缝隙 v1, 选方块, 移动 s
check(True, req("POST", "/select_gap", {"type": "v", "line": 1}), "选中缝隙 v1")
check(True, req("POST", "/select_block", {"row": 0, "col": 0}), "选中方块 (0,0)")
check(True, req("POST", "/move", {"direction": "s"}), "移动 s")
wait_anim()

# 停止录制
resp = req("POST", "/macro/record/stop", {"name": "test_macro_1"})
check(True, resp, "停止录制并保存为 'test_macro_1'")

# --- 4. 验证宏已保存 ---
print("\n[4] 验证宏已保存...")
resp = req("GET", "/macro/list")
check(True, resp, "macro_list 返回 ok=True")
macros = resp.get("macros", [])
print(f"         宏数: {len(macros)}")
for m in macros:
    print(f"         - {m['name']} ({m['steps']}步, step={m['recorded_step']})")
assert len(macros) >= 1, "应有至少1个宏"

# --- 5. 重命名宏 ---
print("\n[5] 重命名宏...")
resp = req("POST", "/macro/rename", {"old_name": "test_macro_1", "new_name": "renamed_macro"})
check(True, resp, "重命名 test_macro_1 -> renamed_macro")

# 验证重命名
resp = req("GET", "/macro/list")
names = [m["name"] for m in resp.get("macros", [])]
assert "renamed_macro" in names, f"重命名后应存在 renamed_macro, 实际: {names}"
print(f"         重命名后列表: {names}")

# --- 6. 执行宏 ---
print("\n[6] 执行宏...")
# 先重置
check(True, req("POST", "/reset"), "重置谜题")
wait_anim()

resp = req("POST", "/macro/execute", {"name": "renamed_macro", "base_row": 0, "base_col": 0})
check(True, resp, "执行宏 'renamed_macro' 基准 (0,0)")

# 等待宏执行完成（逐步执行+动画）
time.sleep(3)

# 检查状态
resp = req("GET", "/status")
print(f"         宏执行后步数: {resp.get('step_count', '?')}")

# --- 7. 删除宏 ---
print("\n[7] 删除宏...")
resp = req("POST", "/macro/delete", {"name": "renamed_macro"})
check(True, resp, "删除 renamed_macro")

# 验证删除
resp = req("GET", "/macro/list")
names = [m["name"] for m in resp.get("macros", [])]
assert "renamed_macro" not in names, f"删除后不应存在 renamed_macro"
print(f"         删除后列表: {names}")

# --- 8. 边界测试 ---
print("\n[8] 边界测试...")

# 重复录制
check(True, req("POST", "/macro/record/start"), "开始录制")
check(False, req("POST", "/macro/record/start"), "重复开始录制应失败")
check(True, req("POST", "/macro/record/stop", {"name": "empty"}), "停止录制0步")

# 执行不存在的宏
check(False, req("POST", "/macro/execute", {"name": "nonexist", "base_row": 0, "base_col": 0}), "执行不存在的宏")

# 删除不存在的宏
check(False, req("POST", "/macro/delete", {"name": "nonexist"}), "删除不存在的宏")

# 缺少参数
check(False, req("POST", "/macro/record/stop", {}), "停止录制缺少 name")
check(False, req("POST", "/macro/execute", {"name": "test"}), "执行宏缺少 base_row/col")
check(False, req("POST", "/macro/rename", {}), "重命名缺少参数")

# --- 9. 清理 ---
print("\n[9] 清理测试数据...")
resp = req("GET", "/macro/list")
for m in resp.get("macros", []):
    req("POST", "/macro/delete", {"name": m["name"]})
resp = req("GET", "/macro/list")
print(f"         清理后宏数: {len(resp.get('macros', []))}")

# ============================================================
print("\n" + "=" * 60)
print("测试完成！")
print("=" * 60)