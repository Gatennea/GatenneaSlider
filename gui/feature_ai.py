# -*- coding: utf-8 -*-
"""大模型 AI 兜底（功能检索的最后一道安全网）。

设计要点（与 docs/ui/搜索改进设计.md Phase 4 一致）：
  · 结构化检索（精确/别名/包含/模糊）+ suggest 都拿不准时，由 LLM 把自然语言
    意图映射到功能清单，或给出真人级解释。
  · **provider 无关**：走 OpenAI 兼容的 Chat Completions 协议；换模型/厂商只改
    环境变量，不动代码。
  · **离线安全**：未配置（无 endpoint / 无 key）时 `resolve` 一律返回 []，由上层
    退回 suggest；绝不抛异常、绝不阻断现有检索。
  · **不编造**：Prompt 强制模型只返回清单内功能 id 的 JSON 数组，清单外一律丢弃。

启用方式（桌面安装版，开发版亦可）：
  set GATENNEA_AI_ENDPOINT=https://<你的兼容端点>/v1/chat/completions
  set GATENNEA_AI_KEY=<你的 key>
  set GATENNEA_AI_MODEL=gpt-4o-mini   # 可选，默认 gpt-4o-mini

TODO（后续）：在设置对话框加 AI 兜底开关 + endpoint/key 输入框，避免让用户改环境变量。
作者：貓九
"""

import json
import os
import urllib.request

# 超时（秒）：兜底必须在交互时限内返回，超时即放弃走回 suggest。
_TIMEOUT = 8


def is_configured():
    """是否已配置可用的 AI 后端（endpoint + key 都在）。"""
    return bool(os.environ.get('GATENNEA_AI_ENDPOINT')
                and os.environ.get('GATENNEA_AI_KEY'))


def _catalog(features, form, mode):
    """把功能清单压成给模型的紧凑 JSON：id / 名称 / 别名 / 当前是否可用。"""
    items = []
    for f in features:
        items.append({
            'id': f['id'],
            'name': f.get('name', ''),
            'aliases': list(f.get('aliases', ())),
            'available': ((form is None or form in f.get('forms', ()))
                          and (mode is None or mode in f.get('modes', ()))),
        })
    return items


_SYSTEM = (
    "你是滑块解谜游戏「貓九滑块（Gatennea Slider）」的功能导航助手。"
    "下面是游戏全部功能的清单（id / 名称 / 玩家别名 / 当前是否可用）。"
    "玩家会用口语描述他想做的事或卡住的情境。请从中挑选最相关的至多 {k} 个功能的 id，"
    "只返回一个 JSON 数组（如 [\"undo\",\"coloring_enabled\"]），不要任何解释文字，"
    "也不要编造清单之外的功能；若一个都不相关就返回 []。"
)


def resolve(query, form=None, mode=None, features=None, k=5):
    """用 LLM 把自然语言查询映射到功能。

    返回 [(entry, available), ...]（最多 k 条）；未配置 / 出错 / 超时 / 无匹配都返回 []，
    由上层退回 suggest。绝不抛异常。
    """
    if not is_configured() or not query or not features:
        return []
    catalog = _catalog(features, form, mode)
    user_prompt = (
        f"当前形态={form or '任意'}，当前模式={mode or '任意'}。\n"
        f"玩家说：{query}\n"
        f"功能清单：{json.dumps(catalog, ensure_ascii=False)}"
    )
    body = json.dumps({
        'model': os.environ.get('GATENNEA_AI_MODEL', 'gpt-4o-mini'),
        'messages': [
            {'role': 'system', 'content': _SYSTEM.format(k=k)},
            {'role': 'user', 'content': user_prompt},
        ],
        'temperature': 0,
    }).encode('utf-8')
    try:
        req = urllib.request.Request(
            os.environ['GATENNEA_AI_ENDPOINT'], data=body,
            headers={
                'Content-Type': 'application/json',
                'Authorization': f"Bearer {os.environ['GATENNEA_AI_KEY']}",
            }, method='POST')
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
            data = json.loads(resp.read().decode('utf-8'))
        content = data['choices'][0]['message']['content']
        ids = json.loads(content)
        if not isinstance(ids, list):
            ids = []
    except Exception:
        return []

    by_id = {f['id']: f for f in features}
    out = []
    for i in ids:
        f = by_id.get(i)
        if f is None or len(out) >= k:
            continue
        avail = ((form is None or form in f.get('forms', ()))
                 and (mode is None or mode in f.get('modes', ())))
        out.append((f, avail))
    return out
