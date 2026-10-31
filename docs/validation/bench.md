# 样机与早期台架记录

查某项功能最早在哪种条件下工作，可按下表找到对应试验。独立 ESP32-S3 台架和整机面包板的引脚、供电与软件版本不同。现行接线见[整机接线表](../wiring.md)，当前能力与部署版本见[状态页](../current-status.md)。

| 对象和试验条件 | 已观察的结果 | 留待整机验证 |
|---|---|---|
| 独立灵矽设备，0.1／0.2 | 绑定、WSS、端侧 MCP 状态和停止可用。受限喷水做过断开功率的调用及两次带载调用 | 面包板语音和网页有独立会话规则。[台架工程](../../firmware/esp32-linx/README.md) |
| 独立 MOS 水枪台架，GPIO4 | 5 秒喷水到期停止，另一次按 BOOT 提前停止，用户确认松开后未恢复 | 精确关断延迟、残液、温升、持续负载和失电行为。[台架配置](../../firmware/esp32-mos-bench/README.md) |
| 独立 L298N 台架，电机空载 | 8 组方向与通道隔离得到现场反馈。双路约 60% 输出运行 10 秒时观察母线约 12 V，另测过 BOOT 提前停止 | 辰克电池下的整机电流、定量温升、机械停止距离。[运行记录](../../firmware/esp32-motor-bench/dual-10s-run-verification.json) · [停止记录](../../firmware/esp32-motor-bench/dual-boot-stop-verification.json) |
| 面包板 ct2、ct4、ct5 | ct2 修复工具回执崩溃后，语音状态与停止完成联调。GPIO18 控制端接反纠正后，ct4 实喷及 BOOT 停止有反馈。ct5 的可变时长调用在功率断开时核对 | 30 秒持续喷水、装壳声学和当前角色的真人语音回归 |
| 同板集成 ct6、并发 ct7 | ct6 完成四方向空载、水枪及 BOOT 分项。ct7 观察到行走与喷水同时运行、分别到期，BOOT 与语音可提前停止 | 当时的供电和通道映射只适用于该轮。参见 [ct6 部署](../../firmware/esp32-audio/startup-ct6.json)和 [ct7 部署](../../firmware/esp32-audio/startup-ct7.json) |
| 网页 ct9、装车 ct21、组合动作 ct24 | ct9 完成无负载网页检查，ct21 有四方向实物反馈，ct24 有后续步骤并发、独立截止与取消的记录，喷水启动略晚 | 真实手机异常断线、持续组合负载、喷水延迟及机械停止量测。[ct9](../../firmware/esp32-audio/startup-ct9.json) · [ct21](../../firmware/esp32-audio/startup-ct21.json) · [ct24 现场记录](../../firmware/esp32-audio/field-ct24.json) |

现行编排和语音评测见[验证材料](README.md)。记录每次现场试验时，应区分软件回执、GPIO 采样、用户观察和仪器量测。

逐次现场观察保存在对应版本的原记录中。[绑定与受限喷水](https://github.com/miclle/cybertrack/blob/c25b0af729bd216b69779db2bba75f32f9475cdd/docs/linx-validation.md) · [音频与停止](https://github.com/miclle/cybertrack/blob/c25b0af729bd216b69779db2bba75f32f9475cdd/docs/audio-board-validation.md) · [面包板喷水](https://github.com/miclle/cybertrack/blob/c25b0af729bd216b69779db2bba75f32f9475cdd/docs/audio-water-validation.md) · [MOS 台架](https://github.com/miclle/cybertrack/blob/c25b0af729bd216b69779db2bba75f32f9475cdd/docs/mos-bench.md) · [电机台架](https://github.com/miclle/cybertrack/blob/c25b0af729bd216b69779db2bba75f32f9475cdd/docs/motor-bench.md) · [同板集成](https://github.com/miclle/cybertrack/blob/c25b0af729bd216b69779db2bba75f32f9475cdd/docs/breadboard-integration.md) · [并发试验](https://github.com/miclle/cybertrack/blob/c25b0af729bd216b69779db2bba75f32f9475cdd/docs/concurrent-actions.md) · [早期网页试验](https://github.com/miclle/cybertrack/blob/c25b0af729bd216b69779db2bba75f32f9475cdd/docs/lan-control-ct9.md)
