# CyberTrack 当前状态

核对日期：2026-10-31。机器可读版本入口为 [firmware/current.json](../firmware/current.json)，检查命令 `python3 scripts/check_firmware_current.py`。它核对版本与角色记录，不连接设备，也不证明修改后的源码等于已部署二进制。

| 项目 | 当前依据与状态 |
|---|---|
| 源码基线 | `2.0.3-ct45`（网页编排、版本确认与三个泡泡表演模板），已仅应用部署；ESP-IDF 5.5.1、小智固定版本及 overlay |
| 最近记录的部署 | [ct45](../firmware/esp32-audio/startup-ct45.json)；2026-10-31 已重启联网并回读 |
| 软件验证 | [ct45 主机／编译记录](../firmware/esp32-audio/verification-ct45.json)，与部署及实物验收分开 |
| 角色 | [唯一角色源](../firmware/esp32-audio/role-prompt.txt)，5994 字符已保存、重新打开逐字回读；平台哈希记录于上述部署文件 |
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


真实灵矽隔离文本联调已完成首轮：80 条工具匹配 76 条（95%），8 条编排匹配 5 条；成功静默及只读解释尚未通过。无前缀诊断单独保留，未替代首轮成绩。真实设备网页、草稿 300538 ms 到期和六类非法输入拒绝均保持零启动。完整边界见[联调记录](validation/lingxi-ct45-20261031.md)。

运行 `python3 scripts/verify_improvements.py` 检查版本元数据、差异格式、现有控制主机测试及网页原脚本回归（需要 Node.js）。已有准备树时运行 `python3 scripts/verify_improvements.py --source build/xiaozhi-ct45-src`，增加实际 MCP／HTTP 与音频适配检查。每次输出独立的 `output/improvements/checks/<UTC时间>/report.json` 和日志，记录源码哈希及未覆盖范围；不刷写、联网调用模型或操纵设备。完整固件编译仍按面包板说明执行。

模型设计工具随仓库交付后，可在依赖已准备的环境运行 `python3 scripts/verify_improvements.py --source build/xiaozhi-ct45-src --model-design`。新增模型／几何／整机同步测试、插件 bundle 和合成宿主界面回归；统一报告记录工具源码哈希并排除依赖、研究数据及生成文件。命令不安装插件、不调用正在运行的模型服务，也不代表桌面宿主消息或 FreeCAD GUI MCP 已验收。首次依赖准备见[模型设计工具](../tools/solidcue/README.md)。

模型辅助设计的[真实 GUI 验收](../tools/solidcue/verification-gui-20261031.json)已完成：198 件整机中冠盖上移 8 mm 后恢复，修改与恢复均经 FreeCAD GUI MCP 保存重开核对；同一本地页面更新到 r7，正式模型未改。无界面快照材质顺序修复通过 GUI 回读。后续[真实宿主卡片验收](../tools/solidcue/verification-host-20261031.json)已完成评论保存／宿主接受、MCP 读回与回执，以及同一卡片 r7 → r8 → r9 更新／恢复。随后[真实消息驱动验收](../tools/solidcue/verification-message-20261031.json)完成：尚未处理的 r9 评论通过 `mcp_app` 独立触发本轮，冠盖上移 4 mm 后恢复，GUI 保存重开与同一卡片 r9 → r10 → r11、最终回执均通过。I11 接入已验收；单次真实链路不代表制造或实物通过。
