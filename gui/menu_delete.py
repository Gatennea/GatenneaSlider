# -*- coding: utf-8 -*-
"""谜题菜单「删除预设」：判断哪一条能删、删掉之后把盘子收拾干净。

用户 2026-10-26 在谜题菜单重设计里定的规则（**GUI 口径**）：

- **能删**：模型谜题（``models/*.json``，含随包发布的碎三角 / 碎三角·晶格）
  与自定义预设（``config/design_styles/*.json``）——它们各自有一份文件。
- **不能删**：矩形 / 异形（三角、米字、数字）这些内置档位。它们连文件都没有，
  条目是代码里写死的，所以菜单里也不画删除键（用户原话：「正好符合预期」）。
- **直删 + 确认弹窗**：不设回收站，但点下去必须先过一道确认。

设计要点
--------
1. **删除目标从条目结构取，不从显示文本反推**。模型条目叫「碎三角（48 块）」，
   显示文本带块数后缀；真正要删的是第 5 项那个模型名。样式条目则是
   ``('名', '__custom__', '名')``。这条与 ``model_preview.target_of_item``
   同层：**菜单条目是唯一真相**，别再各写一份判据（2026-10-26 预览刚踩过）。
2. **删文件 ≠ 菜单消失**。模型注册表是启动期装进内存的，直接 ``os.remove``
   之后菜单会留下一行点了报「模型未安装」的死条目。所以必须再调
   ``model_registry.unregister()`` 把板型摘掉——这里是唯一删除入口，
   GUI 不许自己 ``os.remove``。
3. **顺带清缩图**：预览缓存按「模型名 + 内容哈希」命名，删了模型不清图就是
   一堆永远不会再被命中的孤儿 png（``_purge_stale`` 只按算法版本清）。
4. 内置档位没有文件，但**碎三角有文件且是随包模型**——按用户口径它可删，
   这里不做白名单（删掉后重装/更新会回来）。
"""
import os

# 删除前要过的门：正在玩的谜题不删（当前局的盘面还指着那份文件，
# 删了之后存档/竞速/预览都会指向一个不存在的名字）。判据在 GUI 侧，见
# EventsMixin._menu_item_deletable —— 它才拿得到「当前是哪一局」。


def item_target(item):
    """菜单条目 → 可删除目标；不能删（无文件）返回 None。

    返回 ``{'kind': 'model'|'style', 'key': str, 'label': str}``：
    - ``kind='model'``：key 是 ``models/<key>.json`` 的模型名
    - ``kind='style'``：key 是 ``config/design_styles/<key>.json`` 的预设名
    """
    if not isinstance(item, (tuple, list)) or len(item) < 2:
        return None
    # 自定义预设：('名', '__custom__', '名')
    if len(item) == 3 and item[1] == '__custom__':
        name = str(item[2])
        return {'kind': 'style', 'key': name, 'label': str(item[0] or name)}
    # 模型谜题：('标题（N 块）', 4, 4, step, 模型名)
    if len(item) >= 5 and isinstance(item[4], str):
        name = item[4]
        from engine import model_registry
        if model_registry.has(name):        # 菜单每帧问一次，别复制整张表
            return {'kind': 'model', 'key': name,
                    'label': model_registry.loaded(name).title}
    return None


def model_path(key: str) -> str:
    """模型文件路径（与注册表扫描同一目录，不另写一份路径规则）。"""
    from engine.model_loader import DEFAULT_MODEL_DIR
    return os.path.join(DEFAULT_MODEL_DIR, f'{key}.json')


def describe(target) -> list:
    """确认弹窗的正文（人话，说明删什么、删完什么会没了）。"""
    if not target:
        return []
    if target['kind'] == 'model':
        return [
            f'模型谜题「{target["label"]}」',
            '删除后菜单里它的等级1 / 等级2 两条会一起消失。',
            '模型文件会被直接删除，游戏不会自动恢复它。',
        ]
    return [
        f'自定义预设「{target["label"]}」',
        '删除后菜单里不再出现这一项。',
        '样式文件会被直接删除，游戏不会自动恢复它。',
    ]


def remove(target, config_dir) -> tuple:
    """执行删除。返回 (ok, 给玩家看的说明)。"""
    if not target:
        return False, '没有可删除的目标'
    key = target['key']

    if target['kind'] == 'style':
        from gui import design_styles
        ok = design_styles.delete_style(config_dir, key)
        return (ok, f'已删除自定义预设「{target["label"]}」' if ok
                else f'自定义预设「{target["label"]}」删除失败（文件不存在或被占用）')

    # 模型：删文件 → 摘板型 → 清缩图。三步都要做，少一步就是「菜单里还有一份
    # 点开报错的死条目」或「永远命不中的孤儿缩图」。
    path = model_path(key)
    if not os.path.exists(path):
        from engine import model_registry
        model_registry.unregister(key)
        return True, f'模型「{target["label"]}」的文件已不存在，已把它从菜单摘掉'
    try:
        os.remove(path)
    except OSError as exc:
        return False, f'模型「{target["label"]}」删除失败：{exc}'

    from engine import model_registry
    try:
        model_registry.unregister(key)
    except Exception:      # noqa: BLE001 —— 文件已删成功，摘板型失败不该谎报删除失败
        pass
    try:
        from gui import model_preview
        model_preview.forget_model(key)
    except Exception:      # noqa: BLE001 —— 同上：缩图清不掉只是留垃圾，不影响删除
        pass
    return True, f'已删除模型谜题「{target["label"]}」'
