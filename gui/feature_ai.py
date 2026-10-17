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

启用方式（桌面安装版，开发版亦可）—— 两种模式：
  · 作者中转（默认，零门槛）：DEFAULT_TO_RELAY=True 时，未设环境变量就走 RELAY_ENDPOINT
    中转（占位，部署后替换为真实地址）。玩家无需任何 key / 无需选模型，中转服务端自带
    key 并补默认模型。未部署前占位地址解析失败 → 静默退回 suggest（不崩）。
  · 玩家自填：设 GATENNEA_AI_ENDPOINT + GATENNEA_AI_KEY 即改用玩家自己的兼容端点，
    此时必须自带 key；可选 GATENNEA_AI_MODEL（默认 gpt-4o-mini）。
  · 可选 GATENNEA_APP_KEY：若中转服务端启用了发布校验（APP_KEY），在此提供以免 401。

TODO（后续）：在设置对话框加 AI 兜底开关 + 中转/自填切换，避免让用户改环境变量。
作者：貓九
"""

import json
import os
import urllib.request

# 超时（秒）：兜底必须在交互时限内返回，超时即放弃走回 suggest。
_TIMEOUT = 8

# ===== 部署自定义域名后需改的配置（共 3 处，清单见后端 README「绑定自定义域名」节）=====
#   ① 本文件 RELAY_ENDPOINT（游戏 exe 侧的后端地址）
#   ② GatenneaSliderWeb/src/io/ApiClient.ts 的 API_BASE（网页版侧的后端地址）
#   ③ GatenneaSliderBackend/wrangler.toml 的 ALLOWED_ORIGIN（仅当官网本身也换自定义域才改；
#      后端绑自定义域是在 Cloudflare 控制台操作，不在这 3 处文本里）
# 提示：改 RELAY_ENDPOINT 后必须重新打包 exe；也可设环境变量 GATENNEA_RELAY_ENDPOINT 覆盖，免重打包。

# ---- AI 中转（作者托管）配置 ----
# 默认走作者中转：玩家零门槛即用 AI 兜底，无需任何 key。
# 部署自定义域后把 RELAY_ENDPOINT 改成 https://你的域/api/ai/relay（DEFAULT_TO_RELAY 保持 True）。
DEFAULT_TO_RELAY = True
# 后端地址（自定义域后改这里）：游戏 exe 实际连的后端 Worker 地址。
RELAY_ENDPOINT = "https://gatennea-backend.gatennea.workers.dev/api/ai/relay"


def _effective_endpoint():
    """最终使用的端点：自填端点优先，其次环境变量中继覆盖，否则回落作者中转（若启用）。

    GATENNEA_AI_ENDPOINT  = 玩家自填端点（须自带 key）
    GATENNEA_RELAY_ENDPOINT = 覆盖作者中转地址（部署自定义域后免重打包 exe 用）
    """
    return (os.environ.get('GATENNEA_AI_ENDPOINT')
            or os.environ.get('GATENNEA_RELAY_ENDPOINT')
            or (RELAY_ENDPOINT if DEFAULT_TO_RELAY else ''))


def _using_relay():
    """是否走作者中转（无需玩家 key / 服务端补默认模型）。"""
    return DEFAULT_TO_RELAY and not os.environ.get('GATENNEA_AI_ENDPOINT')


def is_configured():
    """是否已配置可用的 AI 后端。

    自填端点必须同时有 key；走作者中转则无需玩家 key。
    """
    if os.environ.get('GATENNEA_AI_ENDPOINT'):
        return bool(os.environ.get('GATENNEA_AI_KEY'))
    return DEFAULT_TO_RELAY


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
    endpoint = _effective_endpoint()
    if not endpoint:
        return []
    catalog = _catalog(features, form, mode)
    user_prompt = (
        f"当前形态={form or '任意'}，当前模式={mode or '任意'}。\n"
        f"玩家说：{query}\n"
        f"功能清单：{json.dumps(catalog, ensure_ascii=False)}"
    )
    # 走中转时不带 model：服务端用其 AI_MODEL 默认；仅自填端点才带 model。
    body_obj: dict = {
        'messages': [
            {'role': 'system', 'content': _SYSTEM.format(k=k)},
            {'role': 'user', 'content': user_prompt},
        ],
        'temperature': 0,
    }
    if not _using_relay():
        body_obj['model'] = os.environ.get('GATENNEA_AI_MODEL', 'gpt-4o-mini')
    body = json.dumps(body_obj).encode('utf-8')

    headers = {'Content-Type': 'application/json'}
    key = os.environ.get('GATENNEA_AI_KEY')
    if key:  # 自填端点才带 key；中转由服务端补 key
        headers['Authorization'] = f"Bearer {key}"
    app_key = os.environ.get('GATENNEA_APP_KEY')
    if app_key:  # 仅当中转服务端启用发布校验（APP_KEY）时才需要
        headers['X-App-Key'] = app_key
    try:
        req = urllib.request.Request(endpoint, data=body, headers=headers, method='POST')
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
