# CyberTrack

CyberTrack 是一个双履带语音交互玩具机器人项目，将履带行走、语音、喷水和泡泡效果组合成有角色感的机械玩具。当前造型采用切面头盔、分层固定颈架、颈架左侧朝前水枪和共用双液体机甲背包，重充电宝在前下方平放，不要求传统坦克轮廓。

项目采用 ESP32-S3 主控及充电宝供电。已完成灵矽设备绑定、状态／停止和本机单次授权喷水的[真实联调](docs/linx-validation.md)，包括 5 秒自动停止及 BOOT 提前停止；另已在保留“彩菊”绑定的独立音频板上完成[状态／停止语音联调](docs/audio-board-validation.md)，音频及 OLED 回复正常；该板未接执行器，整机语音、自主动作和其他执行器仍待接入。

## 规划功能

- **双履带行走**：前进、后退、差速转弯和停止。
- **语音互动**：语音对话，以及行走、喷水和吹泡泡等动作控制。
- **前部喷水**：自动水枪产生连续脉冲喷水效果。
- **前部泡泡**：正面看左侧为泡泡枪、右侧为水枪，两者朝前微微上仰；泡泡枪使用自带风扇。
- **顶部效果**：拟加入双火花视觉效果，方案尚待评估。

## 项目进度

目前已整理硬件采购清单、部件资料和系统方案，并生成[初步整机模型及视图](hardware/model/README.md)。[固件](firmware/README.md)已完成控制核心、F1 离线 MCP 协议适配及 F2a 通用启动／运行层，通过主机与假板卡测试；另有[ESP32-S3 无负载检查工程](firmware/esp32/README.md)与[实物启动／PSRAM 记录](hardware/components/ESP32-S3-N16R8/physical-verification.md)；执行器驱动、实体停止和平台接入仍待完成。

下一步继续推进[不依赖实物的固件工作](firmware/PLAN.md#不依赖实物的后续工作)；F2b 继续按[清单](firmware/BOARD-INFO.md)补停止器件、板级焊装与外设信息。硬件侧继续核对尺寸和供电参数，用实测部件修订布局并开展单模块测试。具体任务见 [TODO](TODO.md)，阶段安排见[实施及验收计划](docs/verification-plan.md)与[固件计划](firmware/PLAN.md)。

## 了解项目

| 主题 | 文档 |
|---|---|
| 产品与需求 | [产品需求](docs/requirements.md) · [决策和待补资料](docs/decisions.md) |
| 机械与硬件 | [机械设计](docs/mechanical.md) · [电源与接口](docs/power-and-interfaces.md) |
| 控制与语音 | [系统架构](docs/architecture.md) · [灵矽接入](docs/linx-integration.md) · [固件规划](firmware/README.md) |
| 物料与采购 | [BOM](hardware/BOM.md) · [采购清单](hardware/procurement.md) |
| 技术资料 | [资料索引](docs/references.md) |

## 许可证

项目许可证见 [LICENSE](LICENSE)。供应商图片、原理图及数据手册的权利归原权利人，归档不改变其授权条件。
