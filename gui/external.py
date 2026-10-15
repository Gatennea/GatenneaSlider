# -*- coding: utf-8 -*-
"""外部控制混入：开关 / 反馈 / 剪贴板桥接 / 玩家指南生成。

2026-10-14 从 GUI.py 拆出（纯搬方法，零逻辑改动；refactor-structure 第四步）。
「外部控制」= 让外部程序（另一个 AI/脚本）经 http_server 操作棋盘的那套；
本 mixin 管它的开关、给玩家的反馈文案、剪贴板 roundtrip 自检和指南落盘。
只依赖 pygame 与 self.*。
"""
import secrets

import pygame


class ExternalMixin:
    """外部控制（原 GUI.py 内联代码，整体搬迁）。"""

    def external_enabled(self) -> bool:
        """外部控制开关是否开启（有有效令牌才算真开）。"""
        ext = getattr(self, 'ext_state', None) or {}
        return bool(ext.get('enabled')) and bool(ext.get('token'))

    def set_external_control(self, enabled: bool):
        """开/关外部控制。

        关：清空令牌——重开必换新 token，关闭期间复制出去的话术随之作废。
        开：没有令牌就现场生成一个，并往 stdout 打印一行（subprocess
            启动方与人类控制台都能再读到新令牌）。
        """
        ext = self.ext_state
        ext['enabled'] = bool(enabled)
        if enabled:
            if not ext.get('token'):
                ext['token'] = secrets.token_urlsafe(24)
            print(f"GATSLI_TOKEN={ext['token']}")
        else:
            ext['token'] = None

    def external_control_message(self) -> str:
        """生成复制给外部程序的连接话术（含当前令牌与端口；关闭时令牌为空）。"""
        from http_server import TOKEN_MESSAGE_TEMPLATE
        ext = self.ext_state
        return TOKEN_MESSAGE_TEMPLATE.format(
            token=ext.get('token') or '', port=ext.get('port') or 5050)

    def _set_ext_feedback(self, ok: bool, text: str, timer: int = 300):
        """控制页内联反馈（替代宏通知）。

        为什么不用 macro_notify：通知浮层画在模态对话框**之下**，设置框
        开着时玩家根本看不到 toast——按钮就像死的一样。对话框内的操作反
        馈必须在对话框内自报。
        """
        self._settings_ext_msg = text
        self._settings_ext_msg_ok = bool(ok)
        self._settings_ext_msg_timer = int(timer)
        # 反馈行是内容区新长出来的：请求下次绘制时把设置框滚到底，
        # 否则新行落在裁剪区外，玩家看不到任何反应（按钮像死的）
        self._settings_ext_pin_bottom = True

    @staticmethod
    def _clipboard_roundtrip_ok(got, msg: str) -> bool:
        """读回校验：容忍换行风格差异（Windows 剪贴板常把 \\n 变 \\r\\n），
        并接受「关键信息在」这一较松判据——宁可少报错，不可诬告失败。
        """
        if got is None:
            return False
        if isinstance(got, bytes):
            try:
                got = got.decode('utf-8')
            except UnicodeDecodeError:
                return False
        norm = got.replace('\r\n', '\n').replace('\r', '\n')
        return norm == msg or ('Authorization: Bearer' in norm and '令牌：' in norm)

    def _copy_external_message(self):
        """「复制连接话术」按钮：把含令牌的话术写进系统剪贴板。

        剪贴板稳健化：pygame-ce 的 scrap 在部分显示驱动下未自动初始化
        （dummy 驱动直接报 "scrap system not initialized"），故依次尝试
        put_text → init+put，并在写入后读回校验；全失败时给出内联反馈，
        把令牌/端口直接显示出来，玩家可手动抄送（其余步骤见教程文件）。
        """
        if not self.external_enabled():
            self._set_ext_feedback(False, "外部控制已关闭：先打开上方开关，再复制话术")
            return
        msg = self.external_control_message()
        err = None
        ok_msg = "已复制到剪贴板：把这段话发给能在本机发送 HTTP 请求的外部程序即可"
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter('ignore')
            # 路线 1：非弃用的 put_text
            try:
                pygame.scrap.put_text(msg)
                if self._clipboard_roundtrip_ok(pygame.scrap.get_text(), msg):
                    self._set_ext_feedback(True, ok_msg)
                    return
                err = '读回校验不一致'
            except Exception as e:
                err = str(e)
            # 路线 2：旧 API + 显式 init（部分平台 scrap 未随 display 初始化）
            try:
                pygame.scrap.init()
                pygame.scrap.put(pygame.SCRAP_TEXT, msg.encode('utf-8'))
                if self._clipboard_roundtrip_ok(pygame.scrap.get(pygame.SCRAP_TEXT), msg):
                    self._set_ext_feedback(True, ok_msg)
                    return
            except Exception as e:
                err = f"{err} / {e}"
        # 两条路都失败：不装作成功——把关键信息显示出来让人工抄送
        ext = self.ext_state
        self._set_ext_feedback(
            False,
            f"复制失败（剪贴板不可用：{err}）。请手动抄送：令牌 {ext.get('token')}，"
            f"端口 {ext.get('port')}；用法见「下载控制教程」",
            timer=600)

    def write_external_control_guide(self, path: str):
        """生成外部控制教程文件（自包含 Markdown，供外部程序使用者阅读）。

        内容与 GET /help 索引同源；**不含令牌**——令牌只走「复制连接话术」
        那条路，本文件可能被分享/上传官网，职责分离。
        返回 (ok, message)。
        """
        from http_server import API_INDEX
        try:
            ext = self.ext_state
            port = ext.get('port') or 5050
            lines = [
                '# 《貓九的滑塊遊戲》外部控制教程',
                '',
                '> 本文件面向外部程序（AI 助手是其中一种）：读完本文件 + 一个有效',
                '> 令牌，即可通过本机 HTTP 接口控制游戏进程。令牌不在本文件内——',
                '> 在游戏「设置-控制」页点「复制连接话术」获取（那段话含令牌与',
                '> 三步引导）。',
                '',
                '## 1. 连接方式',
                '',
                f'- 基址：`http://127.0.0.1:{port}`',
                '- 鉴权：每个请求带请求头 `Authorization: Bearer <令牌>`，',
                '  或在 URL 上加 `?token=<令牌>`',
                '- 示例：',
                '',
                '  ```',
                '  curl -H "Authorization: Bearer <令牌>" '
                f'http://127.0.0.1:{port}/status',
                '  ```',
                '',
                '## 2. 第一条命令',
                '',
                '- `GET /help` —— 获取最新 API 索引（以索引为准，本文件可能过期）',
                '- `GET /help/<端点>` —— 单个端点的参数/返回/curl 示例，',
                '  如 `GET /help/move`（下表每个端点都适用）',
                '- `GET /status` —— 当前局面与游戏状态',
                '',
                '## 3. API 索引',
                '',
                '| 方法 | 端点 | 说明 |',
                '| --- | --- | --- |',
            ]
            for p, m, s in API_INDEX:
                lines.append(f'| {m} | `{p}` | {s} |')
            lines += [
                '',
                '## 4. 通用约定',
                '',
                '- 所有响应为 JSON，含 `ok`（是否成功）与 `message`（说明）',
                '- 行列坐标从 1 数起（第几行第几列）',
                '- 移动方向：w=上 s=下 a=左 d=右（须平行于选中缝隙）；',
                '  三角另加 e/z/x，米字格另加 q',
                '- 通用命令通道：`POST /command`，body `{"cmd": "<CLI 指令>"}`，',
                '  CLI 指令与 stdin 通道同语法（如 `move w` / `status` / `help`）',
                '- stdin 子进程管道通道不设防（只有启动游戏的父进程能写）',
                '',
                '## 5. 边界',
                '',
                '- 只能控制本机上的这个游戏进程；游戏重启后令牌失效，需重新复制',
                '- 三角形/米字格形态的部分分析接口不支持（返回 reason=unsupported）',
                '',
            ]
            with open(path, 'w', encoding='utf-8') as f:
                f.write('\n'.join(lines))
            return True, f'已保存到 {path}'
        except Exception as e:
            return False, f'保存失败：{e}'

