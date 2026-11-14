# -*- coding: utf-8 -*-
"""功能检索索引（第 0 层）：一份结构化清单，回答「有什么 / 在哪 / 现在能用吗」。

存在的理由（用户原话）：「你能找到的不一定会用，想用的不一定找得到，但确实有」。
玩家真正的痛点是**「这个功能在我当前这盘棋上到底有没有」**——而形态（矩形/数字/
三角/米字）与模式（练习/创造/竞速）的支持差异散落在代码和各文档里，无从判断。

因此本模块是**单一真源**：任何检索入口（帮助对话框搜索、将来的命令面板、HTTP
接口、官网文档导出）都读这一份数据，不要各自再抄一份。

每条字段：
    id        唯一标识（稳定，别随便改，外部可能引用）
    name      功能名（界面显示用）
    aliases   玩家可能会怎么叫它（检索的关键，尽量穷举口语）
    kind      action 动作 / setting 开关 / panel 面板 / puzzle 建局 / concept 概念 / link 链接
    place     结构化位置，见下方 _place_text 的口径
    forms     支持的形态子集（元组），取自 4 种形态键
    modes     支持的模式子集（元组），取自 3 种模式键
    howto     一句话怎么用
    confusion 常见困惑（没有就空串）

**维护纪律**：本表与代码行为必须一致。改动任何功能的形态/模式支持范围时，
同步改这里的 forms / modes；`test/_test_feature_index.py` 会对抽样条目做一致性断言。
"""

# 形态键与显示名（与 solver.game_form() / puzzle_types kind 口径一致）
FORM_NAMES = {
    'square': '矩形',
    'numbered': '数字',
    'triangle': '三角形',
    'mi': '米字格',
}

# 模式键与显示名（与 GUI.game_mode 口径一致）
MODE_NAMES = {
    'practice': '练习',
    'create': '创造',
    'timed': '竞速',
}

ALL_FORMS = ('square', 'numbered', 'triangle', 'mi')
ALL_MODES = ('practice', 'create', 'timed')
_PUSH_MODES = ('practice', 'create', 'timed')

# 常见组合，减少重复
_RECT_AND_NUM = ('square', 'numbered')
_EXOTIC = ('triangle', 'mi')


def place_text(place):
    """把结构化位置渲染成人话，如 ('settings','animation') → 「设置 → 动画速度页」。"""
    if not place:
        return ''
    head = place[0]
    if head == 'menu':
        return f'顶栏「{place[1]}」'
    if head == 'menu_item':
        return f'顶栏「{place[1]}」→ {place[2]}'
    if head == 'menu_sub':
        return f'顶栏「{place[1]}」→ {place[2]} → {place[3]}'
    if head == 'settings':
        _TAB = {
            'keybindings': '快捷键',
            'animation': '视觉',
            'audio': '音频',
            'solver': '求解器',
            'gather': '聚拢参数',
            'file': '文件',
            'control': '控制',
        }
        return f'设置 → {_TAB.get(place[1], place[1])}页'
    if head == 'right_panel':
        return '主窗口右下角快捷区'
    if head == 'key':
        return '快捷键'
    if head == 'tutorial':
        return '顶栏「教程」'
    if head == 'web':
        return '顶栏「官网」'
    return '—'


# ---------------------------------------------------------------- 清单本体
# 形态缩写：矩形 / 数字 / 三角 / 米字
FEATURES = (
    # ---------------- 文件 ----------------
    dict(id='load', name='打开存档', aliases=('打开', '载入', '读取存档', '导入', 'load'),
         kind='action', place=('menu_item', '文件', '打开'),
         forms=ALL_FORMS, modes=ALL_MODES,
         howto='顶栏「文件」→「打开」，选一个 .json 存档。',
         confusion='竞速模式计时中禁止打开存档。'),
    dict(id='save', name='保存存档', aliases=('保存', '存档', '保存进度', 'save'),
         kind='action', place=('menu_item', '文件', '保存'),
         forms=ALL_FORMS, modes=ALL_MODES,
         howto='顶栏「文件」→「保存」；已存过的会直接覆盖。',
         confusion='开了「防止覆盖」后，Ctrl+S 一律走另存为。'),
    dict(id='save_as', name='另存为', aliases=('另存', '存为新档', '导出'),
         kind='action', place=('menu_item', '文件', '另存为...'),
         forms=ALL_FORMS, modes=ALL_MODES,
         howto='顶栏「文件」→「另存为...」，换文件名存一份新档。',
         confusion=''),
    dict(id='save_compress', name='压缩存档',
         aliases=('压缩', '压缩存档', '存档压缩', '压缩保存', '重放压缩', '存档变小'),
         kind='setting', place=('settings', 'file'),
         forms=ALL_FORMS, modes=ALL_MODES,
         howto='设置 → 文件页「压缩存档」。打开后，矩形/数字谜题存档只记初始局面加一串操作，读档时按操作重放还原，文件小很多。',
         confusion='三角、米字和模型盘不受影响，仍存普通格式；压缩存档要有一路走过的完整操作，没有历史的一局存不了。'),
    dict(id='readonly_save', name='存档只读',
         aliases=('只读', '存档只读', '只读标记', '锁住存档', '只读档'),
         kind='setting', place=('settings', 'file'),
         forms=ALL_FORMS, modes=ALL_MODES,
         howto='设置 → 文件页「存档只读」。打开后保存的存档都会带只读标记；打开只读存档只能撤销/重做。',
         confusion='只读是存档文件自带的标记，不是这个窗口的临时状态：想真正改盘面，先另存为一份普通档。'),
    dict(id='prevent_overwrite', name='防止覆盖',
         aliases=('防止覆盖', '防覆盖', '覆盖', '不覆盖旧档', '强制另存'),
         kind='setting', place=('settings', 'file'),
         forms=ALL_FORMS, modes=ALL_MODES,
         howto='设置 → 文件页「防止覆盖」。打开后按 Ctrl+S 一律进「另存为」，不会盖掉旧存档。',
         confusion='它只改 Ctrl+S 的去向，不改存档格式；频繁另存会留下一堆副本，整理时按日期删。'),
    dict(id='restart', name='重启游戏', aliases=('重启', '重新启动', '重开', '自动重开', 'restart'),
         kind='action', place=('menu_item', '文件', '重启（自动重开）'),
         forms=ALL_FORMS, modes=ALL_MODES,
         howto='顶栏「文件」→「重启（自动重开）」；或命令面板搜「重启」。游戏退出后由看门进程自动重拉起，无需手动关掉再双击。',
         confusion='重启会退出当前进程再重开：未保存的编辑器内容会丢失；已自动暂存的进度重启后会恢复。它与「退出」不同——退出后不会自动重开。'),

    # ---------------- 找功能（元功能：找不到别的入口时先来这里） ----------------
    # 排在清单最前：它是「不知道有没有 / 不知道在哪」时的兜底入口，检索时
    # 「命令面板」四个字若能命中自己，玩家就能从帮助框里也把它翻出来。
    dict(id='command_palette', name='命令面板（搜索功能）',
         aliases=('命令面板', '搜索功能', '查找功能', '功能检索', '找不到',
                  '有没有', '在哪', 'palette', 'ctrl k', '搜索'),
         kind='action', place=('menu_item', '搜索', '命令面板'),
         forms=ALL_FORMS, modes=ALL_MODES,
         howto='按 Ctrl+K；或顶栏「搜索」→「命令面板」。输关键词后 ↑↓ 选择、回车直接到位。',
         confusion='**不确定某个功能有没有、在哪、当前能不能用，先来这里搜。** '
                   '结果会写明位置、怎么用，以及当前形态/模式下是否可用（不可用会标 ✕ 并说明原因）。'),

    # ---------------- 编辑 ----------------
    dict(id='undo', name='撤销', aliases=('撤销', '退回', '上一步', '反悔', 'undo'),
         kind='action', place=('menu_item', '编辑', '撤销'),
         forms=ALL_FORMS, modes=_PUSH_MODES,
         howto='按 Ctrl+Z，或顶栏「编辑」→「撤销」。',
         confusion=''),
    dict(id='redo', name='重做', aliases=('重做', '恢复', '下一步', 'redo'),
         kind='action', place=('menu_item', '编辑', '重做'),
         forms=ALL_FORMS, modes=_PUSH_MODES,
         howto='按 Ctrl+X，或顶栏「编辑」→「重做」。',
         confusion=''),
    dict(id='shuffle', name='打乱', aliases=('打乱', '洗牌', '乱序', '重新开始', 'shuffle'),
         kind='action', place=('menu_item', '编辑', '打乱'),
         forms=ALL_FORMS, modes=_PUSH_MODES,
         howto='按 Alt+S，或顶栏「编辑」→「打乱」。',
         confusion='竞速计时中、只读存档下禁止打乱。'),
    dict(id='reset', name='重置', aliases=('重置', '还原', '复原', '回到初始', 'reset'),
         kind='action', place=('menu_item', '编辑', '重置'),
         forms=ALL_FORMS, modes=_PUSH_MODES,
         howto='按 Ctrl+R，或顶栏「编辑」→「重置」，回到建局时的实心形状。',
         confusion='重置不等于解开——它只是把盘面退回起始状态。'),
    dict(id='center_view', name='居中', aliases=('居中', '回到屏幕', '拉回来', '看不到滑块', '重新居中', 'center'),
         kind='action', place=('menu_item', '编辑', '居中'),
         forms=ALL_FORMS, modes=ALL_MODES,
         howto='顶栏「编辑」→「居中」，把滑块组拉回屏幕中央（一次）。',
         confusion='找不到滑块组时用；它只挪视图，不动棋盘上的滑块。'),
    dict(id='auto_solve', name='自动求解', aliases=('自动求解', '求解', '自动', '让电脑解', 'solve'),
         kind='action', place=('menu_item', '编辑', '自动求解'),
         forms=ALL_FORMS, modes=_PUSH_MODES,
         howto='选好算法后按 Ctrl+A；求解中再按一次可叫停。',
         confusion='竞速计时中、只读存档、标注录制中都禁止求解。'),

    # ---------------- 求解算法 ----------------
    dict(id='algo_gather', name='单次聚拢（求解算法）',
         aliases=('聚拢', '单次聚拢', '聚拢求解', 'gather', '梯度'),
         kind='setting', place=('settings', 'solver'),
         forms=ALL_FORMS, modes=ALL_MODES,
         howto='设置 → 求解器页，选「单次聚拢」，按确定后 Ctrl+A 开跑。',
         confusion='**唯一支持三角形 / 米字格的算法**；其余算法在异形下会明确拒绝。它只跑一轮聚拢，多轮自动放宽参数请用「梯度聚拢」。'),
    dict(id='algo_others', name='求解算法（查表 / 梯度聚拢 / 填洞补缺 / 混合）',
         aliases=('查表', '梯度聚拢', '填洞补缺', '混合', '混合求解', '自动规划',
                  'table', 'hybrid', 'gap macro', 'IDA*', '快速', '贪心'),
         kind='setting', place=('settings', 'solver'),
         forms=_RECT_AND_NUM, modes=ALL_MODES,
         howto='设置 → 求解器页的算法列表里选：查表（题库有答案就直接给）、梯度聚拢（一轮不够再来一轮）、填洞补缺（对着缺口逐个补）、混合（有答案先查表，没有就聚拢→补缺→搜索）。界面会把当前形态不支持的项置灰。',
         confusion='数字形态本质是矩形+编号，按矩形判定，所以这些算法在数字下可用；三角、米字只认单次聚拢与梯度聚拢。'),
    dict(id='pick_fill', name='选块填空', aliases=('选块填空', '填空', '单段求解', '指定空位'),
         kind='setting', place=('settings', 'solver'),
         forms=('square',), modes=('practice',),
         howto='选该算法 → 点一个凸起方块和一个空位（顺序不限）→ Ctrl+A。',
         confusion='只支持矩形；数字、三角、米字会在入口就拒绝。只保证你点的那个空位被填上，不要求整盘还原。'),
    dict(id='solver_log_enabled', name='求解器日志',
         aliases=('求解日志', '求解器日志', 'solver log', '过程日志', '复盘日志'),
         kind='setting', place=('settings', 'solver'),
         forms=ALL_FORMS, modes=ALL_MODES,
         howto='设置 → 求解器页「求解器日志」。打开后每次求解会记一份过程明细（用了哪个算法、各段花多久、为什么停下），排查「求解为什么停下」时用；文件在游戏的 config 目录里，按大小只留最近若干条。',
         confusion='它只是记录，不影响求解结果与步数；成绩记录只记「多少步/多久」，这里记的是「为什么」。文件会按大小自动只留最近若干条。'),
    dict(id='gather_params', name='聚拢参数（进阶）',
         aliases=('聚拢参数', '参数', '聚拢调参', '调参', '停滞容忍', '激进程度', '最大步数'),
         kind='setting', place=('settings', 'gather'),
         forms=_EXOTIC, modes=ALL_MODES,
         howto='设置 → 聚拢参数页：停滞容忍步数、无进展停机秒数、激进程度、目标聚拢度、最大步数五项，只在三角/米字聚拢时起作用。',
         confusion='这一页只影响「聚拢」这一步，不影响填洞、查表。默认值是实测调过的，改激进程度最容易看出差别（也最容易让步数暴涨）。'),

    # ---------------- 面板 ----------------
    dict(id='virtual_keyboard', name='虚拟键盘', aliases=('虚拟键盘', '键盘', '屏幕键盘', '方向键'),
         kind='panel', place=('key', 'virtual_keyboard'),
         forms=ALL_FORMS, modes=ALL_MODES,
         howto='按 F1，或右下角「虚拟键盘」开关。',
         confusion='三角是 6 向布局、米字是 8 向布局；米字不做物理键盘绑定，定向主要靠它。'),
    dict(id='metrics_panel', name='调试面板', aliases=('调试面板', '指标面板', '聚拢度面板', '调试'),
         kind='panel', place=('key', 'metrics_panel'),
         forms=ALL_FORMS, modes=ALL_MODES,
         howto='按 F2；或设置 → 视觉页的「调试面板」开关。',
         confusion='三种形态都支持。面板显示数据，棋盘上的记号和框由「复原提示标记」单独控制。'),
    dict(id='records_panel', name='成绩面板', aliases=('成绩', '记录', '计时记录', '最好成绩', 'ao5'),
         kind='panel', place=('right_panel', 'show_records_panel'),
         forms=ALL_FORMS, modes=ALL_MODES,
         howto='按 F3，或点右下角「成绩」开关。',
         confusion='这个开关**不在**设置对话框里，只有 F3 和右下角两个入口。'),

    # ---------------- 开关（设置对话框） ----------------
    dict(id='coloring_enabled', name='分组着色',
         aliases=('着色', '染色', '分色', '上色', '颜色分组', '分组'),
         kind='setting', place=('settings', 'animation'),
         forms=ALL_FORMS, modes=ALL_MODES,
         howto='设置 → 视觉页「分组着色」；或右下角「着色」开关。',
         confusion='**等级 1 时看不到任何效果**——等级 1 时分组退化成一组，所有滑块同色。这是设计使然，不是开关坏了。'),
    dict(id='chain_hint_enabled', name='悬停连锁提示',
         aliases=('连锁', '连锁提示', '悬停提示', '联动提示'),
         kind='setting', place=('settings', 'animation'),
         forms=ALL_FORMS, modes=ALL_MODES,
         howto='设置 → 视觉页「悬停连锁提示」；或右下角「连锁」开关。',
         confusion='鼠标悬停在滑块上时，高亮与它同组、可能互换位置的其他滑块。'),
    dict(id='gap_hover_flash_enabled', name='悬停缝隙闪烁',
         aliases=('缝隙闪烁', '缝隙高亮', '悬停缝隙', '缝提示', '缝隙呼吸'),
         kind='setting', place=('settings', 'animation'),
         forms=ALL_FORMS, modes=ALL_MODES,
         howto='设置 → 视觉页「悬停缝隙闪烁」。鼠标停在点得动的那条缝上时，用慢速灰闪先亮出来，点击前就知道这条缝能动。',
         confusion='这是纯视觉开关：关掉只是不再闪，缝隙的点击判定、选中红线和求解逻辑都不变；灰闪不等于「已选中」，选中是红线。'),
    dict(id='board_marks_enabled', name='复原提示标记',
         aliases=('标记', '复原标记', '记号', '目标框', '洞标记', '凸起标记', '洞位'),
         kind='setting', place=('settings', 'animation'),
         forms=ALL_FORMS, modes=ALL_MODES,
         howto='设置 → 视觉页「复原提示标记」；或右下角「复原标记」开关；F2 会连带切换它。',
         confusion='这是**独立于调试面板**的开关：只想要棋盘上的记号和框、不想要数据面板时，单独开它即可。'),
    dict(id='draw_grid', name='绘制网格',
         aliases=('网格', '背景网格', '显示网格', '方格'),
         kind='setting', place=('settings', 'animation'),
         forms=ALL_FORMS, modes=ALL_MODES,
         howto='设置 → 视觉页「绘制网格」。关掉后只画滑块之间的缝，不再铺满整盘的网格线，空位和洞口留白；四种盘（矩形/数字/三角/米字）都生效，选中缝的高亮不受影响。',
         confusion='关闭后不是「网格全消失」：滑块与滑块相接的地方仍然有缝线（否则拼图看不出分块），消失的只是横穿空位/洞口的那部分。四种原版盘（矩形/数字/三角/米字）都会变，选中缝高亮不受影响；模型盘本就没有这层网格，不受开关影响。'),
    dict(id='anti_drift', name='防偏移演示',
         aliases=('防偏移', '防止偏移', '质心锁定', '不漂走', '居中演示', '漂移', '漂走', '别漂'),
         kind='setting', place=('settings', 'animation'),
         forms=ALL_FORMS, modes=ALL_MODES,
         howto='设置 → 视觉页「防偏移演示」。自动求解演示与存档回放期间，让整盘别慢慢往一边滑走（纯视觉，不动解法与盘面）。目前只对矩形盘生效。',
         confusion='纯视觉：步数、盘面、存档内容都不变，只是演示时画面不再漂；关掉即恢复原样。三角、米字还没接上这块，所以那两种盘仍会跟着解法平移。'),
    dict(id='thinking', name='思考演示',
         aliases=('思考演示', '假装在尝试', '假装尝试', '随机游走演示', '像人在想'),
         kind='setting', place=('settings', 'animation'),
         forms=ALL_FORMS, modes=ALL_MODES,
         howto='设置 → 视觉页「思考演示」。流式求解播完一段、下一段还没算出来时，让滑块随机试着推几步；算出下一段的瞬间按游走步逆序连续撤回到段末状态，再播放下一段动画。纯视觉，不改盘面/历史/解法/步数。',
         confusion='只在「等下一段」的空档里出现，不是求解器真的在重新搜索；撤回会多花一点点时间，嫌慢可以关掉。渲染层的游走不会改盘面、不会写撤销历史、也不会改变聚拢度，关掉后演示恢复成原来的干等。'),
    dict(id='animation_enabled', name='滑动动画',
         aliases=('滑动动画', '动画', '移动动画', '过渡'),
         kind='setting', place=('settings', 'animation'),
         forms=ALL_FORMS, modes=ALL_MODES,
         howto='设置 → 视觉页「滑动动画」；或右下角「滑动动画」开关。',
         confusion='关掉后移动是瞬时的，不是卡住了。'),
    dict(id='selection_animation_enabled', name='选中动画',
         aliases=('选中动画', '选中提示', '选组动画', '求解播放高亮'),
         kind='setting', place=('settings', 'animation'),
         forms=ALL_FORMS, modes=ALL_MODES,
         howto='设置 → 视觉页「选中动画」；或右下角「选中动画」开关。',
         confusion='关掉后，求解器/宏播放不再显示选中的红缝、整片选中色与当前步白光边（2026-11-07 修：宏播放每步用完 be_opted 后清视觉态，_play_head_border 也读这个开关）。手玩时自己点选的缝和滑块组照常高亮——那是操作状态，不是动画；滑动动画由「滑动动画」开关单独管，不受影响。'),
    dict(id='arrows_enabled', name='箭头按键',
         aliases=('箭头', '箭头按钮', '方向按钮', '两端按键'),
         kind='setting', place=('settings', 'control'),
         forms=ALL_FORMS, modes=ALL_MODES,
         howto='设置 → 控制页「箭头按键」。',
         confusion='开启后，选中的滑块组两端会出现可点的箭头按键用于定向。'),
    dict(id='ui_mode', name='界面模式（增强 / 朴素）',
         aliases=('界面模式', '增强模式', '朴素模式', '特效', 'ui'),
         kind='setting', place=('settings', 'animation'),
         forms=ALL_FORMS, modes=ALL_MODES,
         howto='设置 → 视觉页「界面模式」。',
         confusion='朴素模式下不播放增强动效，其余功能完全一致。'),
    dict(id='animation_duration', name='动画时长',
         aliases=('动画时长', '速度', '动画速度', '毫秒'),
         kind='setting', place=('settings', 'animation'),
         forms=ALL_FORMS, modes=ALL_MODES,
         howto='设置 → 视觉页拖「动画时长」滑条（100~1000ms）；右下角速度滑条可到 50ms。',
         confusion='对话框滑条最低 100ms，接口与右下角滑条可到 50ms——两者下限不一致，属已知差异。'),
    dict(id='zoom', name='缩放',
         aliases=('缩放', '放大', '缩小', 'zoom', '视图大小'),
         kind='setting', place=('settings', 'animation'),
         forms=ALL_FORMS, modes=ALL_MODES,
         howto='设置 → 视觉页拖「缩放」滑条（10%~400%）；右下角缩放滑条、Ctrl+滚轮同样可调，三者实时联动。',
         confusion='缩放只改视图、不动棋盘；换异形谜题时会按棋盘大小自动适配一次。'),

    # ---------------- 音频（2026-11-07 单独成页） ----------------
    dict(id='sfx_enabled', name='音效（总开关）',
         aliases=('音效', '声音', '音效开关', 'sfx', '声音开关'),
         kind='setting', place=('settings', 'audio'),
         forms=ALL_FORMS, modes=ALL_MODES,
         howto='设置 → 音频页「音效总开关」；关掉后下面每一项都不出声（背景音乐不受影响）。',
         confusion='这是上级闸门：逐项开关开着、总开关关着，一样没声。素材在 assets/audio/sound/，缺文件不报错、只是那项不响。'),
    dict(id='sfx_slots', name='音效一览（逐项开关 / 试听）',
         aliases=('音效一览', '音效列表', '逐项音效', '滑动音效', '点击音效',
                  '键盘音效', '失败音效', '复原音效', '试听', '音量', '声音大小'),
         kind='setting', place=('settings', 'audio'),
         forms=ALL_FORMS, modes=ALL_MODES,
         howto='设置 → 音频页「音效一览」：滑动声 / 滑动被拒 / 复原 / 鼠标点击 / 键盘按键 各一行，独立开关，右侧「试听」可直接听。',
         confusion='「试听」无视开关与总静音（就是要让你听完再决定开不开）。滑动声是单次魔方转动声，一次滑动只播一次原始采样、不会被拉长；音量跟着滑动速度走——动画时越长（滑得越慢）声音越轻，就像真的转动魔方。按方向键推动成功或被拒时只出动作音，不会再叠一声按键音；键盘音只在没有动作音时、松开按键那一刻响。'),
    dict(id='music_enabled', name='背景音乐',
         aliases=('背景音乐', 'bgm', '音乐', '背景乐', '循环音乐'),
         kind='setting', place=('settings', 'audio'),
         forms=ALL_FORMS, modes=ALL_MODES,
         howto='设置 → 音频页「背景音乐」开关，音量用下面的「音乐音量」滑条。素材放 assets/audio/music/（目录里第一个音讯档即当作 bgm）。',
         confusion='与音效共用同一个开关区但互不影响：关音效不会停背景音乐，反之亦然。'),
    dict(id='sound_muted', name='全部静音',
         aliases=('全部静音', '总静音', '一键静音', '静音', 'mute', '声音总开关'),
         kind='setting', place=('settings', 'audio'),
         forms=ALL_FORMS, modes=ALL_MODES,
         howto='设置 → 音频页「全部静音」开关，再点一次恢复。',
         confusion='它压在音效和背景音乐两个总开关之上：开着时两路都不出声、正在响的那一声也会立刻停，但不改它们各自的开关状态，关掉静音后原样恢复。只想关音效就用「音效」总开关，别用它。「试听」按钮不受静音影响。'),

    # ---------------- 控制方式 ----------------
    dict(id='control_single_touch', name='单次触控',
         aliases=('单次触控', '单击拖动', '一次触控', '拖动跟随'),
         kind='setting', place=('settings', 'control'),
         forms=('square', 'numbered', 'triangle'), modes=ALL_MODES,
         howto='设置 → 控制页「单次触控」。',
         confusion='**米字格永久关闭**——切到米字会自动关掉，手动也打不开（八向靠一次触控猜方向误触太大），请用两次触控或虚拟键盘。'),
    dict(id='control_two_touch', name='两次触控',
         aliases=('两次触控', '两次触摸', '点缝再拖'),
         kind='setting', place=('settings', 'control'),
         forms=ALL_FORMS, modes=ALL_MODES,
         howto='设置 → 控制页「两次触控」；第一下点缝隙，第二下按住滑块拖动定向。',
         confusion='米字格的主要操作方式。'),
    dict(id='control_mouse_kb', name='鼠标键盘（含方向键）',
         aliases=('鼠标键盘', '键盘操作', '方向键', 'wasd'),
         kind='setting', place=('settings', 'control'),
         forms=('square', 'numbered', 'triangle'), modes=ALL_MODES,
         howto='设置 → 控制页「鼠标键盘」；方形/数字用 WASD，三角用 W/E/A/D/Z/X 六向。',
         confusion='**米字格不绑物理键盘**，定向请用虚拟键盘或拖动。'),
    dict(id='external_control', name='外部控制（HTTP / 命令行）',
         aliases=('外部控制', '远程控制', '接口', 'api', 'http', '脚本控制', '令牌', 'token'),
         kind='setting', place=('settings', 'control'),
         forms=ALL_FORMS, modes=ALL_MODES,
         howto='设置 → 控制页最下面的「外部控制」区：看连接话术、复制令牌、下载控制教程。开着游戏时也能从外部下指令（滑动、打乱、求解、读盘面）。',
         confusion='令牌只在本机有效，发给别人等于把控制权交出去；不玩自动化就整块不用管，它不影响正常操作。'),

    # ---------------- 建局 ----------------
    dict(id='preset_quick', name='快速开始', aliases=('快速开始', '快速', '推荐档'),
         kind='puzzle', place=('menu_item', '谜题', '快速开始：矩形 6×6 等级2'),
         forms=ALL_FORMS, modes=ALL_MODES,
         howto='顶栏「谜题」→「快速开始：矩形 6×6 等级2」。',
         confusion=''),
    dict(id='preset_rect', name='矩形谜题预设档', aliases=('矩形', '矩形谜题', '方形谜题', '尺寸'),
         kind='puzzle', place=('menu_sub', '谜题', '矩形谜题 ▸', '各尺寸'),
         forms=ALL_FORMS, modes=ALL_MODES,
         howto='顶栏「谜题」→「矩形谜题 ▸」，按等级分组（1 入门 / 2 经典 / 3 复杂）。',
         confusion=''),
    dict(id='preset_exotic', name='异形谜题预设档', aliases=('异形', '异形谜题', '三角', '米字', '数字'),
         kind='puzzle', place=('menu_sub', '谜题', '异形谜题 ▸', '各形态'),
         forms=ALL_FORMS, modes=ALL_MODES,
         howto='顶栏「谜题」→「异形谜题 ▸」，含三角形、米字格、数字三组。',
         confusion=''),
    dict(id='custom_puzzle', name='自定义谜题', aliases=('自定义', '自定义尺寸', '改尺寸', '改等级'),
         kind='puzzle', place=('menu_item', '谜题', '自定义...'),
         forms=ALL_FORMS, modes=ALL_MODES,
         howto='顶栏「谜题」→「自定义...」，先选形态再填尺寸与等级。',
         confusion='三角形要求「边长 − 等级 ≥ 2」，否则一步都动不了，会自动拒绝。'),
    dict(id='delete_preset', name='删除预设',
         aliases=('删除预设', '删预设', '删除谜题', '删档位', '删掉这一档', '移除预设'),
         kind='action', place=('menu_item', '谜题', '删除预设...'),
         forms=ALL_FORMS, modes=ALL_MODES,
         howto='顶栏「谜题」→「删除预设...」，选中哪一档就删哪一档；删完菜单里立刻消失。',
         confusion='只删你自己造的自定义档与导入的模型档；游戏自带的矩形/三角/米字档删不掉，也不会被误删。'),
    dict(id='model_editor', name='搭积木编辑器（造模型盘）',
         aliases=('模型', '模型文件', '模型编辑器', '搭积木', '造题', '自制谜题', '设计谜题'),
         kind='puzzle', place=('tutorial',),
         forms=ALL_FORMS, modes=('create',),
         howto='右下角模式切到「创造」→ 顶栏下方工具条的「还原态设计」→「搭积木（自由板型）」，从空盘摆块造新板型，存成模型文件后在「谜题」菜单里出现。',
         confusion='搭积木出的是「模型盘」，与自带四种盘型不是一套几何；编辑器只认模型盘，自带盘型进不去搭积木。创造模式下才出现这条工具条。'),

    # ---------------- 模式 ----------------
    dict(id='mode_practice', name='练习模式', aliases=('练习', '练习模式', '随便玩'),
         kind='setting', place=('right_panel', 'game_mode'),
         forms=ALL_FORMS, modes=ALL_MODES,
         howto='点右下角「模式」开关循环切换：练习 → 竞速 → 创造 → 迷宫。',
         confusion='练习模式不限时、不计成绩，随便试。'),
    dict(id='mode_timed', name='竞速模式', aliases=('竞速', '计时', '限时', '比赛'),
         kind='setting', place=('right_panel', 'game_mode'),
         forms=ALL_FORMS, modes=ALL_MODES,
         howto='右下角「模式」切到竞速；按空格或点状态栏计时区开始/放弃。',
         confusion='计时中禁止：求解、宏、打乱、重置、打开存档。'),
    dict(id='mode_create', name='创造模式', aliases=('创造', '创造模式', '造题', '自定义谜题'),
         kind='setting', place=('right_panel', 'game_mode'),
         forms=ALL_FORMS, modes=ALL_MODES,
         howto='右下角「模式」切到创造，可[随机生成]或[手动构造]造题。',
         confusion='**[随机生成]只支持矩形与数字**；三角/米字没有这个按钮，请用[手动构造]（三种形态都能用）。'),

    # ---------------- 宏 ----------------
    dict(id='macro_record', name='录制宏', aliases=('宏', '录制宏', '录宏', 'macro'),
         kind='action', place=('menu_item', '宏定义', '录制宏'),
         forms=_RECT_AND_NUM + ('triangle',), modes=('practice', 'create'),
         howto='按 Ctrl+M 或顶栏「宏定义」→「录制宏」，走完步骤再按一次结束。',
         confusion='竞速计时中、只读存档下禁止录制；米字格不支持录制。'),
    dict(id='macro_execute', name='执行宏', aliases=('执行宏', '播放宏', '回放'),
         kind='action', place=('menu_item', '宏定义', '（宏名）'),
         forms=_RECT_AND_NUM, modes=('practice', 'create'),
         howto='顶栏「宏定义」里点宏名即可回放；「逆序播放」可倒着放。',
         confusion='竞速计时中、只读存档下禁止执行。'),
    dict(id='macro_reverse', name='逆序播放宏', aliases=('逆序', '逆序播放', '倒放'),
         kind='setting', place=('settings', 'control'),
         forms=_RECT_AND_NUM, modes=ALL_MODES,
         howto='设置 → 控制页「逆序播放宏」。',
         confusion='这是全局开关，影响所有宏的回放方向。'),
    dict(id='infinite_shuffle', name='无限打乱', aliases=('无限打乱', '随机游走', '连续打乱'),
         kind='setting', place=('settings', 'control'),
         forms=ALL_FORMS, modes=ALL_MODES,
         howto='设置 → 控制页「无限打乱」。开启后调用「打乱」会一直随机游走，再次调用「打乱」即停止。',
         confusion='它只是「打乱」的持续模式，不是另一个打乱按钮；开了以后要再点一次「打乱」才停。'),

    dict(id='macro_manage', name='管理宏', aliases=('管理宏', '宏管理', '删除宏'),
         kind='action', place=('menu_item', '宏定义', '管理宏...'),
         forms=_RECT_AND_NUM, modes=ALL_MODES,
         howto='顶栏「宏定义」→「管理宏...」。',
         confusion=''),

    # ---------------- 引导 ----------------
    dict(id='help', name='帮助（操作说明）', aliases=('帮助', '说明', '操作说明', '怎么用', '教程'),
         kind='action', place=('menu', '帮助'),
         forms=ALL_FORMS, modes=ALL_MODES,
         howto='顶栏「帮助」，或直接按 F1 旁的搜索入口（本对话框顶部搜索框）。',
         confusion=''),
    dict(id='tutorial', name='新手教程', aliases=('教程', '新手', '教学', '闯关'),
         kind='action', place=('menu', '教程'),
         forms=ALL_FORMS, modes=ALL_MODES,
         howto='顶栏「教程」，按关卡一步步走。',
         confusion='首次进入游戏（无存档且没看过）会自动开始；教程不覆盖你原来的局面。'),
    dict(id='website', name='官网', aliases=('官网', '网站', '网页版', '下载'),
         kind='link', place=('menu', '官网'),
         forms=ALL_FORMS, modes=ALL_MODES,
         howto='顶栏「官网」，用默认浏览器打开网页版。',
         confusion='网页版只有矩形一种形态，且不做求解器 / 宏 / 调试面板。'),

    # ---------------- 更新（增量更新器） ----------------
    dict(id='check_update', name='检查更新',
         aliases=('检查更新', '查更新', '有没有新版本', '版本', 'update', '新版'),
         kind='action', place=('menu', '帮助'),
         forms=ALL_FORMS, modes=ALL_MODES,
         howto='在命令面板（Ctrl+K）搜「检查更新」，或顶栏「帮助」。仅安装版（exe）生效，开发版不检查。',
         confusion='自动更新**只覆盖程序文件**，你的存档 / 配置 / 宏目录都原样保留，不会动。'),
    dict(id='update_now', name='立即更新',
         aliases=('更新', '立即更新', '升级', '升到最新', 'update now'),
         kind='action', place=('menu', '帮助'),
         forms=ALL_FORMS, modes=ALL_MODES,
         howto='先「检查更新」发现新版本后，在命令面板搜「立即更新」，或点游戏内左上角的「更新」按钮。',
         confusion='点击后会**关闭游戏 → 下载新版本 → 自动重启**；更新过程中不要手动关进程。'),

    # ---------------- 概念 ----------------
    dict(id='concept_step', name='等级（= 步长）',
         aliases=('等级', '步长', '难度', 'step'),
         kind='concept', place=('menu_item', '谜题', '自定义...'),
         forms=ALL_FORMS, modes=ALL_MODES,
         howto='在「自定义」里改数字；等级就是一次推动几格。',
         confusion='**等级、步长、step 是同一件事**，不是三个独立概念。宽裕型 = 长宽 > 等级×2；紧凑型 = 长宽 ≤ 等级×2。等级 2 的 6×6 ≈ 三阶魔方。'),
    dict(id='concept_gap', name='缝（缝隙）',
         aliases=('缝', '缝隙', '切线', '切缝', '缝模型'),
         kind='concept', place=('menu', '帮助'),
         forms=ALL_FORMS, modes=ALL_MODES,
         howto='点一条缝 → 再点它一侧的滑块，就选中了那一整片；片上箭头或虚拟键盘决定往哪推。',
         confusion='**缝是刀，不是被推的东西**：它负责把盘面切开，被推的是切出来的那一片。'),
    dict(id='concept_hole', name='缺口 / 孔洞（统称空位）',
         aliases=('空位', '缺口', '孔洞', '洞', '空格'),
         kind='concept', place=('menu', '帮助'),
         forms=ALL_FORMS, modes=ALL_MODES,
         howto='调试面板会标出当前所有的洞和凸起在哪。',
         confusion='「缺口」是边缘凹进去的，「孔洞」是内部空出来的，统称**空位**。'),
    dict(id='concept_gather', name='聚拢度',
         aliases=('聚拢度', '聚拢', '完成度', '进度'),
         kind='concept', place=('key', 'metrics_panel'),
         forms=ALL_FORMS, modes=ALL_MODES,
         howto='按 F2 看调试面板，里面显示当前聚拢度与目标窗口。',
         confusion='聚拢度是「离还原还差多远」的内部指标，不是官方难度评分。'),
)


# ---------------------------------------------------------------- 一键到位目标
# 检索结果被回车 / 点击时执行。类型语义见 `gui/events.py::_activate_feature`。
_ACTIONS = {
    # 找功能：打开命令面板（自指条目——面板里搜到它也能打开面板）
    'command_palette': {'type': 'palette'},
    # 文件
    'load': {'type': 'menu', 'name': '文件'},
    'save': {'type': 'menu', 'name': '文件'},
    'save_as': {'type': 'menu', 'name': '文件'},
    'save_compress': {'type': 'settings', 'tab': 'file'},
    'readonly_save': {'type': 'settings', 'tab': 'file'},
    'prevent_overwrite': {'type': 'settings', 'tab': 'file'},
    'restart': {'type': 'menu', 'name': '文件'},
    # 编辑
    'undo': {'type': 'menu', 'name': '编辑'},
    'redo': {'type': 'menu', 'name': '编辑'},
    'shuffle': {'type': 'menu', 'name': '编辑'},
    'reset': {'type': 'menu', 'name': '编辑'},
    'auto_solve': {'type': 'menu', 'name': '编辑'},
    'center_view': {'type': 'menu', 'name': '编辑'},
    # 求解器
    'algo_gather': {'type': 'settings', 'tab': 'solver'},
    'algo_others': {'type': 'settings', 'tab': 'solver'},
    'pick_fill': {'type': 'settings', 'tab': 'solver'},
    'solver_log_enabled': {'type': 'settings', 'tab': 'solver'},
    'gather_params': {'type': 'settings', 'tab': 'gather'},
    # 面板 / 开关（直接切换，等价右下角快捷开关）
    'virtual_keyboard': {'type': 'toggle', 'key': 'show_virtual_keyboard'},
    'metrics_panel': {'type': 'toggle', 'key': 'show_metrics_panel'},
    'records_panel': {'type': 'toggle', 'key': 'show_records_panel'},
    'coloring_enabled': {'type': 'toggle', 'key': 'coloring_enabled'},
    'chain_hint_enabled': {'type': 'toggle', 'key': 'chain_hint_enabled'},
    'gap_hover_flash_enabled': {'type': 'settings', 'tab': 'animation'},
    'board_marks_enabled': {'type': 'toggle', 'key': 'board_marks_enabled'},
    'draw_grid': {'type': 'toggle', 'key': 'draw_grid'},
    'anti_drift': {'type': 'toggle', 'key': 'anti_drift_enabled'},
    'thinking': {'type': 'toggle', 'key': 'thinking_enabled'},
    'animation_enabled': {'type': 'toggle', 'key': 'animation_enabled'},
    'selection_animation_enabled': {'type': 'toggle', 'key': 'selection_animation_enabled'},
    # 设置页（跳页签）
    'arrows_enabled': {'type': 'settings', 'tab': 'control'},
    'ui_mode': {'type': 'settings', 'tab': 'animation'},
    'animation_duration': {'type': 'settings', 'tab': 'animation'},
    'zoom': {'type': 'settings', 'tab': 'animation'},
    # 音频（设置页单独一页，见 gui/audio.py）
    'sfx_enabled': {'type': 'settings', 'tab': 'audio'},
    'sfx_slots': {'type': 'settings', 'tab': 'audio'},
    'music_enabled': {'type': 'settings', 'tab': 'audio'},
    'sound_muted': {'type': 'settings', 'tab': 'audio'},
    'control_single_touch': {'type': 'settings', 'tab': 'control'},
    'control_two_touch': {'type': 'settings', 'tab': 'control'},
    'control_mouse_kb': {'type': 'settings', 'tab': 'control'},
    'external_control': {'type': 'settings', 'tab': 'control'},
    # 宏
    'macro_record': {'type': 'menu', 'name': '宏定义'},
    'macro_execute': {'type': 'menu', 'name': '宏定义'},
    'macro_manage': {'type': 'menu', 'name': '宏定义'},
    'macro_reverse': {'type': 'settings', 'tab': 'control'},
    'infinite_shuffle': {'type': 'settings', 'tab': 'control'},
    # 建局
    'preset_quick': {'type': 'puzzle', 'params': (6, 6, 2), 'kind': 'square'},
    'preset_rect': {'type': 'menu', 'name': '谜题'},
    'preset_exotic': {'type': 'menu', 'name': '谜题'},
    'custom_puzzle': {'type': 'custom_dialog'},
    'delete_preset': {'type': 'menu', 'name': '谜题'},
    'model_editor': {'type': 'none'},
    # 模式
    'mode_practice': {'type': 'mode', 'mode': 'practice'},
    'mode_create': {'type': 'mode', 'mode': 'create'},
    'mode_timed': {'type': 'mode', 'mode': 'timed'},
    # 引导 / 链接
    'help': {'type': 'none'},
    'tutorial': {'type': 'tutorial'},
    'website': {'type': 'website'},
    # 增量更新器
    'check_update': {'type': 'updater_check'},
    'update_now': {'type': 'updater_now'},
    'concept_step': {'type': 'none'},
    'concept_gap': {'type': 'none'},
    'concept_hole': {'type': 'none'},
    'concept_gather': {'type': 'none'},
}

# 每条都必须登记动作；漏登记直接 KeyError，不静默兜底。
for _f in FEATURES:
    _f['action'] = _ACTIONS[_f['id']]


# ---------------------------------------------------------------- 检索
# ---------------------------------------------------------------- 检索
# 疑问前缀 / 句尾语气词：匹配前剥离，让「怎么撤销」「能不能着色」直接落到核心词。
_QUESTION_PREFIXES = (
    '怎么', '如何', '怎样', '咋', '在哪', '哪里', '为什么', '为啥',
    '能不能', '能否', '是否', '可以吗', '我想', '我要', '我想找', '我要找', '请问',
)
_TRAILING_PARTICLES = ('吗', '呢', '呀', '啊', '吧', '哦')


def _strip_question(query):
    """剥掉口语疑问外壳，返回核心检索串。

    例：『怎么撤销』→『撤销』、『能不能着色吗』→『着色』、『我想找三角求解』→『三角求解』。
    只动已提交的整串，不影响 IME 组字途中状态（TEXTINPUT 已在事件层处理）。
    """
    q = (query or '').strip()
    for p in _QUESTION_PREFIXES:
        if q.startswith(p):
            q = q[len(p):].strip()
            break
    while q and q[-1] in _TRAILING_PARTICLES:
        q = q[:-1].strip()
    return q


def _entry_tokens(entry):
    """名称 + 全部别名（小写），用于模糊匹配。"""
    toks = [entry.get('name', '').lower()]
    toks.extend(a.lower() for a in entry.get('aliases', ()))
    return toks


def _lcs_len(a, b):
    """最长公共子序列长度（短串专用，O(n·m) 足够）。"""
    if not a or not b:
        return 0
    prev = [0] * (len(b) + 1)
    best = 0
    for ch_a in a:
        cur = [0] * (len(b) + 1)
        for j, ch_b in enumerate(b, 1):
            if ch_a == ch_b:
                cur[j] = prev[j - 1] + 1
                if cur[j] > best:
                    best = cur[j]
        prev = cur
    return best


def _haystack(entry):
    """一条功能参与匹配的全部文本（名称 + 别名 + 说明 + 困惑 + 位置）。"""
    parts = [entry.get('name', '')]
    parts.extend(entry.get('aliases', ()))
    for key in ('howto', 'confusion', 'place'):
        val = entry.get(key)
        if isinstance(val, tuple):
            parts.extend(str(v) for v in val)
        elif val:
            parts.append(str(val))
    return ' '.join(parts).lower()


_INDEX = [(f, _haystack(f), _entry_tokens(f)) for f in FEATURES]


def _score(term, entry, hay):
    """单个关键词的得分：命中位置越靠前（名称 > 别名 > 说明）分越高。"""
    term = term.lower()
    name = entry.get('name', '').lower()
    if term == name:
        return 100
    if term in name:
        return 70
    for alias in entry.get('aliases', ()):
        alias = alias.lower()
        if term == alias:
            return 90
        if term in alias:
            return 60
        # 玩家把别名写长了也算命中：『三角形』里含别名『三角』、『音量』里含
        # 别名『音量』。只单向比的话，写长的词会掉到「说明里提到过」的 30 分，
        # 被判给不相干的条目。
        if alias in term:
            return 60
    if term in hay:
        return 30
    return 0


def _fuzzy_score(needle, tokens):
    """整串无空格组合词（如『三角求解』）的模糊得分。

    取与任一名称/别名的最长公共子序列，重叠 ≥2 字才给分，上限 50（低于别名
    包含 60，精确/包含仍优先）。只在「名称+别名」token 上算，避免对 howto/
    confusion 长文本产生垃圾误中（保证 search('zzzz不存在的东西') 仍返回 []）。

    **前缀加成**：某个名称/别名正好是查询的开头（『三角求解』以别名『三角』
    开头）时再加 15。没有这一条，『三角求解』里『三角』和『求解』各命中一次、
    分数并列，先登记的条目会把真正想找的预设档挤出前几名（§二十五 那条红）。
    """
    if len(needle) < 2:
        return 0
    best = 0
    prefix_hit = False
    for tok in tokens:
        if tok and needle.startswith(tok):
            prefix_hit = True
        ov = _lcs_len(needle, tok)
        if ov > best:
            best = ov
    if best < 2:
        return 0
    score = min(50, 25 + (best - 2) * 10)
    if prefix_hit:
        score = min(60, score + 15)
    return score


def search(query, form=None, mode=None, limit=30):
    """模糊检索功能清单。

    两路匹配：
      1) 主路：按空白分词、所有词都要命中（AND）+ 子串打分；
      2) 模糊路：整串（无空格的组合词，如『三角求解』）走最长公共子序列，
         主路全失时兜底，让「中文不空格」也能搜到。

    疑问前缀（怎么/如何/能不能…）与句尾语气词（吗/呢…）在匹配前被剥离。

    参数：
        query: 玩家输入。
        form:  当前形态键（'square'/'numbered'/'triangle'/'mi'），用于标注可用性。
        mode:  当前模式键（'practice'/'create'/'timed'），同上。

    返回：
        [(score, entry, available), ...] 按 (强命中数, 可用, 综合分) 降序；
        available 为当前上下文是否可用。返回形状保持稳定，UI 无需改动。
    """
    q = _strip_question(query)
    terms = [t for t in q.split() if t]
    if not terms:
        return []

    out = []
    for entry, hay, toks in _INDEX:
        total = 0
        strong = 0
        for term in terms:
            s = _score(term, entry, hay)
            if s == 0:
                total = 0
                strong = 0
                break
            total += s
            if s >= 60:        # 名称 / 别名命中算强信号，用于同分精排
                strong += 1
        if total <= 0:
            continue
        available = supports(entry, form, mode)
        out.append((total, strong, entry, available))

    # 主路全失 → 模糊兜底（整串作为单一 needle，仅查名称+别名 token）
    if not out:
        needle = ''.join(terms)
        for entry, _hay, toks in _INDEX:
            fs = _fuzzy_score(needle, toks)
            if fs <= 0:
                continue
            available = supports(entry, form, mode)
            out.append((fs, 0, entry, available))

    # 排序：(强命中数, 可用, 综合分) 降序——**名称/别名命中优先于可用性**。
    # 以前可用性排第一，导致「三角」在矩形盘里被排在「单次聚拢」后面
    # （预设档被判成当前形态不支持），玩家会以为搜不到；预设档本身能切形态，
    # 已按 ALL_FORMS 登记，但保留这条规则更稳：确切的词先出来，灰着的也比
    # 不相干的强命中靠前。
    out.sort(key=lambda r: (r[1], r[3], r[0]), reverse=True)
    return [(total, entry, available) for total, _strong, entry, available in out][:limit]


def list_all(form=None, mode=None, limit=None):
    """空查询时列出全部功能，作为「功能地图」供浏览发现。

    排序：(可用优先, 分类优先级, 名称) 升序；返回 [(entry, available), ...]。
    命令面板打开即调它，玩家不输也能逛到所有功能。
    """
    _KIND_ORDER = {'puzzle': 0, 'action': 1, 'setting': 2, 'panel': 3,
                   'concept': 4, 'link': 5}
    rows = []
    for f in FEATURES:
        avail = supports(f, form, mode)
        rows.append((not avail, _KIND_ORDER.get(f.get('kind'), 9),
                     f.get('name', ''), f, avail))
    rows.sort(key=lambda r: (r[0], r[1], r[2]))
    pairs = [(entry, avail) for _na, _ko, _nm, entry, avail in rows]
    return pairs if limit is None else pairs[:limit]


def suggest(query, form=None, mode=None, k=5):
    """零命中时的相近推荐：用模糊重叠（最长公共子序列）挑最相近的 k 条。

    返回 [(entry, available), ...]；query 为空或全无模糊重叠时返回 []。
    帮助框 / 命令面板在 search 拿到 0 命中时改调它，代替「换个说法」。
    """
    q = _strip_question(query)
    needle = ''.join(t for t in q.split() if t)
    if len(needle) < 2:
        return []
    cand = []
    for entry, _hay, toks in _INDEX:
        fs = _fuzzy_score(needle, toks)
        if fs <= 0:
            continue
        cand.append((fs, entry, supports(entry, form, mode)))
    cand.sort(key=lambda r: (r[2], r[0]), reverse=True)
    return [(entry, avail) for _s, entry, avail in cand[:k]]


def supports(entry, form=None, mode=None):
    """该功能在给定形态 / 模式下是否可用；未传上下文时视为可用。"""
    if form is not None and form not in entry.get('forms', ()):
        return False
    if mode is not None and mode not in entry.get('modes', ()):
        return False
    return True


def supported_form_names(entry):
    """该功能支持的形态显示名，如 ['矩形', '三角形']。"""
    return [FORM_NAMES.get(f, f) for f in entry.get('forms', ())]


def unsupported_reason(entry, form, mode):
    """当前上下文为什么用不了（形态 / 模式分别判定），可用时返回 ''。"""
    if form is not None and form not in entry.get('forms', ()):
        return f'{FORM_NAMES.get(form, form)}形态不支持，仅支持{"、".join(supported_form_names(entry))}'
    if mode is not None and mode not in entry.get('modes', ()):
        names = [MODE_NAMES.get(m, m) for m in entry.get('modes', ())]
        return f'{MODE_NAMES.get(mode, mode)}模式下不可用，支持{"、".join(names)}'
    return ''
