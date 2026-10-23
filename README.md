# CyberTrack

CyberTrack 是一个双履带语音交互玩具机器人项目，将履带行走、语音、喷水和泡泡效果组合成有角色感的机械玩具。当前造型采用切面头盔、分层固定颈架、偏置喷水口和共用双液体机甲背包，重充电宝在前下方平放，不要求传统坦克轮廓。

项目采用 ESP32-S3 主控，计划接入灵矽平台，让使用者通过语音与机器人交流、发出动作指令，并使用充电宝供电。

## 规划功能

- **双履带行走**：前进、后退、差速转弯和停止。
- **语音互动**：语音对话，以及行走、喷水和吹泡泡等动作控制。
- **前部喷水**：自动水枪产生连续脉冲喷水效果。
- **尾部泡泡**：泡泡机通过自带风扇向车后吹出泡泡。
- **顶部效果**：拟加入双火花视觉效果，方案尚待评估。

## 项目进度

目前已整理硬件采购清单、部件资料和系统方案，并生成[初步整机模型及视图](hardware/model/README.md)。详细结构、电路与实物适配仍待验证；固件进展见[固件说明](firmware/README.md)。

下一步将补齐硬件尺寸和供电参数，开展布局设计与单模块测试。具体任务见 [TODO](TODO.md)，阶段安排见[实施及验收计划](docs/verification-plan.md)。

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
