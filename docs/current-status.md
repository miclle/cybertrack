# CyberTrack 当前状态

核对日期：2026-10-31。机器可读版本入口为 [firmware/current.json](../firmware/current.json)，检查命令 `python3 scripts/check_firmware_current.py`。它核对版本与角色记录，不连接设备，也不证明修改后的源码等于已部署二进制。

| 项目 | 当前依据与状态 |
|---|---|
| 源码基线 | `2.0.3-ct45` 候选（网页编排、版本确认与三个泡泡表演模板），未部署；ESP-IDF 5.5.1、小智固定版本及 overlay |
| 最近记录的部署 | [ct42](../firmware/esp32-audio/startup-ct42.json)；不是本次实时设备探测 |
| 软件验证 | [ct45 主机／编译记录](../firmware/esp32-audio/verification-ct45.json)，与 ct42 部署分开 |
| 角色 | [唯一角色源](../firmware/esp32-audio/role-prompt.txt)，源码新增编排规则，尚未同步；ct42 平台回读哈希记录于上述部署文件 |
| 运动 | 四方向，60–100% PWM、默认 100%；全速转向省略时长为 880 ms，其他普通动作默认 1000 ms；无编码器里程计 |
| 并发与序列 | 四路独立截止，序列最多 16 步；步骤内并发，步骤间串行；取消不恢复 |
| 测距 | IO1/TRIG、IO2/ECHO，约 100 ms 采样、500 ms 过期；无效不报旧距离 |
| 距离提示音 | 小于 50 cm 提示；40–50 cm 每 800 ms，小于 40 cm 每 400 ms；与动作及停车开关独立 |
| 前进保护 | 网页开关默认关闭；开启时小于 15 cm 停前进／至少 20 cm 解锁，解锁不续走；无自动绕行 |
| 网页 | `http://<设备 IP>:8080/`；单网页会话，长按租期 600 ms；同通道网页优先 |
| 电源 | 辰克 5 V 电池包、12 V 升压电机支路；旧电源测试不迁移 |
| 机械 | [当前模型](../hardware/model/README.md)，Lean／Ready 各 27 件、6 盘；须按各自说明切片 |
| 实物 | 已有样机及分项现场反馈；当前整机持续负载、停止性能、可靠性及完整语音回归未验收 |
| 只读帮助 | ct43 候选新增[上手与回执解释](status-explanation.md)，不自动执行或重试；线上语音待验 |
| 编排候选 | ct45 新增[泡泡剧场编辑器](show-composer.md)与登场／庆祝／谢幕模板；设备版本预览、显式确认及取消，未部署 |
| 新改进 | [执行计划](improvement-plan.md)，候选能力不等于部署 |

ct42 部署检查记录 18 次有效距离样本、执行器启动次数为 0。提示音调度日志不是听感验收；电平、机械停止及效果反馈继续以专项实测为准。2026-10-31 用户暂时无法配合实机测试。

旧版本参数及证据保留在各专题的历史章节；当前能力以本页、[接口手册](../firmware/CAPABILITIES.md)与源码交叉核对。

## 统一软件检查

运行 `python3 scripts/verify_improvements.py` 检查版本元数据、差异格式、现有控制主机测试及网页原脚本回归（需要 Node.js）。已有准备树时运行 `python3 scripts/verify_improvements.py --source build/xiaozhi-ct45-src`，增加实际 MCP／HTTP 与音频适配检查。每次输出独立的 `output/improvements/checks/<UTC时间>/report.json` 和日志，记录源码哈希及未覆盖范围；不刷写、联网调用模型或操纵设备。完整固件编译仍按面包板说明执行。

模型设计工具随仓库交付后，可在依赖已准备的环境运行 `python3 scripts/verify_improvements.py --source build/xiaozhi-ct45-src --model-design`。新增模型／几何／整机同步测试、插件 bundle 和合成宿主界面回归；统一报告记录工具源码哈希并排除依赖、研究数据及生成文件。命令不安装插件、不调用正在运行的模型服务，也不代表桌面宿主消息或 FreeCAD GUI MCP 已验收。首次依赖准备见[模型设计工具](../tools/solidcue/README.md)。

模型辅助设计的[真实 GUI 验收](../tools/solidcue/verification-gui-20261031.json)已完成：198 件整机中冠盖上移 8 mm 后恢复，修改与恢复均经 FreeCAD GUI MCP 保存重开核对；同一本地页面更新到 r7，正式模型未改。无界面快照材质顺序修复通过 GUI 回读。后续[真实宿主卡片验收](../tools/solidcue/verification-host-20261031.json)已完成评论保存／宿主接受、MCP 读回与回执，以及同一卡片 r7 → r8 → r9 更新／恢复。旧连接超时已解除；宿主消息自动触发独立处理轮次仍未验证，不能用目标续跑处理或统一软件检查替代。
