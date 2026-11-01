# ct78：移除泡泡剧场

2026-11-01，用户决定完整移除独立表演编辑能力。组合效果继续由直接语音指令表达，保留步骤内并发、步骤间串行、独立截止和停止保护。I06／I07 的草稿编辑、模板与重玩指标取消，不记作验收通过。

## 当前范围

- 删除网页剧场、三个模板、编辑／预览／确认入口，以及离线排演页面和打包入口。
- 删除 `self.tank.compose`、HTTP `show_edit`／`show_confirm`、草稿版本与过期状态、语音读版本许可、专用相对改稿分类器及状态说明。公开工具从十二个减为十一个。
- 删除仅用于网页表演的序列来源分支；保留语音 `sequence` 最多 16 步、`move_and_water`、运行中调速、统一停止、BOOT、断线／故障取消、不重试及不恢复。
- 删除当前使用说明，将专用研究记录移入 history 归档，更新需求、架构、接口、角色和待办。版本化原始 JSON、压缩轨迹和历史评分语料保留以复算旧证据；参考包中的历史 compose 成绩不代表现行能力。

旧 MCP 工具按未知工具拒绝，旧 HTTP 编辑／确认请求在解析时拒绝，不映射成动作。旧缓存网页不能通过已移除的确认接口启动；其他合法遥控接口仍按原契约处理。

## 仅讨论或预览时不执行

角色明确：仅在用户要求执行时调用动作工具；“只预览”“先别执行”、编辑表演等请求不转换为直接动作，不虚构保存或确认入口。

设备增加有限的拒绝性检查：当前识别文字含预览、编排、草稿、排演、只讨论、只说说、修改／编辑表演或若干明确暂不执行表达时，动作与调速返回 `execution_not_requested`，同轮不补做；查询和停止仍可用，新识别输入重新判断。此检查不会授权动作，也不证明完整自然语言理解。含相反意图的混合表达保守拒绝，需重新明确指令；未覆盖说法仍依赖模型语义回归。

活动或步骤间等待时，全停始终优先；本机和可信网页停止不受语音输入限制。原有限否定句、新输入代际、过期票据和错误隔离检查继续保留。

## 本地验证

构建与检查摘要见 [verification-ct78.json](../../firmware/esp32-audio/verification-ct78.json)，版本与角色哈希见 [current.json](../../firmware/current.json)。

可复现入口：

```sh
sh firmware/esp32-audio/test.sh
node firmware/esp32-audio/tests/web_ui_test.mjs
python3 firmware/esp32-audio/tests/run_mcp_tests.py --source build/xiaozhi-ct78-src
python3 scripts/build_firmware_host.py --source build/xiaozhi-ct78-src --output build/ct78-full-host --sanitize
python3 scripts/check_no_theatre.py --executable build/ct78-full-host/firmware_host --output build/ct78-no-theatre.json
python3 scripts/check_firmware_host.py --executable build/ct78-full-host/firmware_host
python3 scripts/replay_stop_matrix.py --source build/xiaozhi-ct78-src
python3 -m unittest discover -s tests/improvements
```

主机回归使用真实解析、工具回调与控制守卫，时钟、识别文字、距离和 IO 为模拟；不等于实际模型、扬声器或实物动作验收。停止矩阵保留当前适用的语音序列和网页遥控项目；旧网页表演序列项目随功能退役，未将其标成通过。

## 部署边界

ct78 为本地候选，尚未刷写，也未同步线上角色。最近记录设备应用仍为 ct77，平台最近回读仍为旧 5991 字符角色。上线需将 ct78 固件和仓库新角色配套更新、保存重开回读，再验证工具发现、组合／序列、停止、否定、只预览／暂不执行和拒绝后的新输入恢复。不得用旧固定集成绩作为新角色通过证据。
