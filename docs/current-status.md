# CyberTrack 当前状态

核对日期：2026-10-31。机器可读版本入口为 [firmware/current.json](../firmware/current.json)，检查命令 `python3 scripts/check_firmware_current.py`。`last_recorded_deployment` 保留应用部署记录，独立的 `last_recorded_role_sync` 记录后续纯角色同步，避免将重启冒充烧录。检查器核对源码版本与构建记录，以及角色同步所对应的已部署版本。可用下列命令分别核对两份本地应用文件的字节数和 SHA-256。省略参数时只检查记录；两种方式均离线运行。

```sh
python3 scripts/check_firmware_current.py --source-bin build/firmware-ct62/xiaozhi.bin --deployed-bin build/firmware-ct45/xiaozhi.bin
```

| 项目 | 当前依据与状态 |
|---|---|
| 源码基线 | `2.0.3-ct62` 候选，增加按识别输入代际的失败隔离，失败后拒绝自动重试／补做，停止与查询保留，新输入恢复；状态查询明确区分已有／没有草稿和本次保存回执。调速拒绝时提供请求时刻的未移动或链路离线说明。工具说明要求单说“全速”直接请求调速，匹配本轮成功回执后抑制确认音频。手机可在载入前对照设备新稿与本页预览，动作状态未确认时保留本地 BOOT 停止指引，明确全停成功后本地抑制确认音频，状态查询列出网页长按通道，区分续租窗口与定时动作剩余量，剧场预览显示同时动作和结束顺序；ESP-IDF 5.5.1、小智固定版本及 overlay |
| 最近记录的部署 | [ct45](../firmware/esp32-audio/startup-ct45.json)；2026-10-31 已重启联网并回读 |
| 最近角色同步 | [ct45 停止与长按角色修正](../firmware/esp32-audio/role-cancel-hold-ct45.json)，5991 字符保存回读、重启与零启动检查；模型语义另验 |
| 软件验证 | [ct62 软件记录](../firmware/esp32-audio/verification-ct62.json)、[输入失败隔离](validation/voice-input-guard.md)、[ct47 定向联调](validation/lingxi-ct47.md)与 [ct46 三轮联调](validation/lingxi-ct46.md)；已部署 ct45 的软件依据仍见 [ct45 记录](../firmware/esp32-audio/verification-ct45.json) |
| 角色 | [唯一角色源](../firmware/esp32-audio/role-prompt.txt)，5991 字符，已重开回读。检查命令分别列出仓库角色与平台回读哈希 |
| 运动 | 四方向，60–100% PWM、默认 100%；全速转向省略时长为 880 ms，其他普通动作默认 1000 ms；无编码器里程计 |
| 并发与序列 | 四路独立截止，序列最多 16 步；步骤内并发，步骤间串行；取消不恢复 |
| 测距 | IO1/TRIG、IO2/ECHO，约 100 ms 采样、500 ms 过期；无效不报旧距离 |
| 距离提示音 | 小于 50 cm 提示；40–50 cm 每 800 ms，小于 40 cm 每 400 ms；与动作及停车开关独立 |
| 前进保护 | 网页开关默认关闭；开启时小于 15 cm 停前进／至少 20 cm 解锁，解锁不续走；无自动绕行 |
| 网页 | `http://<设备 IP>:8080/`；单网页会话，长按租期 600 ms；同通道网页优先 |
| 电源 | 辰克 5 V 电池包、12 V 升压电机支路；旧电源测试不迁移 |
| 机械 | [当前模型](../hardware/model/README.md)，Lean／Ready 各 27 件、6 盘；须按各自说明切片 |
| 实物 | 已有样机及分项现场反馈；当前整机持续负载、停止性能、可靠性及完整语音回归未验收 |
| 只读帮助 | ct43 引入、ct45 已部署[上手与回执解释](status-explanation.md)，不自动执行或重试；线上隔离解释已运行，发现猜测和恢复表述偏差；见[联调结果](validation/lingxi-ct45-20261031.md) |
| 编排 | ct45 新增[泡泡剧场编辑器](show-composer.md)与登场／庆祝／谢幕模板；设备版本预览、显式确认及取消；无动作草稿路径已在设备验证 |
| 新改进 | [执行计划](improvement-plan.md)，部署不等于实物验收 |

ct45 部署检查的 39 条状态／操作回执全部输出关闭、动作启动计数为 0；草稿创建、单步修改、旧版本拒绝、删除、取消、停止／会话释放失效及重连不恢复通过。未提交有效表演确认，未触发执行器。提示音调度日志不是听感验收；电平、机械停止及效果反馈继续以专项实测为准。2026-10-31 用户暂时无法配合实机测试。

旧版本参数及证据保留在各专题的历史章节；当前能力以本页、[接口手册](../firmware/CAPABILITIES.md)与源码交叉核对。

## 统一软件检查


真实灵矽隔离文本联调：首轮 76/80，角色修正后 77/80（96.25%），8 条编排仍匹配 5 条；只读解释 4/8 满足全部要求，45 条成功静默均未达成。见[最新复测](validation/lingxi-ct45-role-feedback-20261031.md)。无前缀诊断单独保留，未替代首轮成绩。真实设备网页、草稿 300538 ms 到期和六类非法输入拒绝均保持零启动。完整边界见[联调记录](validation/lingxi-ct45-20261031.md)。

运行 `python3 scripts/verify_improvements.py` 检查版本元数据、差异格式、现有控制主机测试及网页原脚本回归（需要 Node.js）。已有准备树时运行 `python3 scripts/verify_improvements.py --source build/xiaozhi-ct62-src`，增加 17 类停止回放、实际 MCP／HTTP、音频适配、完整固件主机及输入失败隔离检查。ct62 十一组通过，含 76 项改进测试；八组输入边界与四条历史请求为离线回放，不构成新模型成绩。每次输出独立的 `output/improvements/checks/<UTC时间>/report.json` 和日志，记录源码哈希及未覆盖范围；不刷写、联网调用模型或操纵设备。完整固件编译仍按面包板说明执行。

要检查模型设计工具，请在依赖已准备的环境运行 `python3 scripts/verify_improvements.py --source build/xiaozhi-ct62-src --model-design`。新增模型／几何／整机同步测试、插件 bundle 和合成宿主界面回归；统一报告记录工具源码哈希并排除依赖、研究数据及生成文件。命令不安装插件、不调用正在运行的模型服务，也不代表桌面宿主消息或 FreeCAD GUI MCP 已验收。首次依赖准备见[模型设计工具](../tools/solidcue/README.md)。

模型辅助设计的[真实 GUI 验收](../tools/solidcue/verification-gui-20261031.json)已完成：198 件整机中冠盖上移 8 mm 后恢复，修改与恢复均经 FreeCAD GUI MCP 保存重开核对；同一本地页面更新到 r7，正式模型未改。无界面快照材质顺序修复通过 GUI 回读。后续[真实宿主卡片验收](../tools/solidcue/verification-host-20261031.json)已完成评论保存／宿主接受、MCP 读回与回执，以及同一卡片 r7 → r8 → r9 更新／恢复。随后[真实消息驱动验收](../tools/solidcue/verification-message-20261031.json)完成：尚未处理的 r9 评论通过 `mcp_app` 独立触发本轮，冠盖上移 4 mm 后恢复，GUI 保存重开与同一卡片 r9 → r10 → r11、最终回执均通过。I11 接入已验收；单次真实链路不代表制造或实物通过。

ct62 [真实 STT 合成上行](validation/ct62-stt-host.md)二十条中十九条正常结束且工具匹配，喷水一条未收到结束事件；转写十九条匹配。全部输入事件、MCP 回执与终态离线重放一致。播放策略抑制 248 个确认包，组合／序列和目标速度仍有 216 个确认包待处理。该记录使用无设备主机，不更新板上 ct45 或真人成绩；完整改进测试现为 81 项通过。
