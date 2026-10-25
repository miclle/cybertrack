# CyberTrack

双履带语音交互玩具机器人，将语音对话、履带行走、喷水和泡泡效果组合成有角色感的机械玩具。

CyberTrack 采用 ESP32-S3 与灵矽语音交互，搭配切面头盔、分层固定颈架和双液体背包。充电宝位于前下方，电机支路通过 DC-DC 升压至 12 V，使用 L298N 驱动两台 37R-520 电机。

[模型与图纸](hardware/model/README.md) · [固件开发](firmware/README.md) · [局域网控制](docs/lan-control.md) · [接线总表](docs/wiring.md) · [待办](TODO.md)

![CyberTrack 整机 CAD 装配候选](hardware/model/assembly.png)

*当前机械布局：0.43。图中为 CAD 装配候选，实物装配、制造与整机带载验收仍在推进。*

## 功能与进度

当前处于**机械设计与分项台架联调阶段**。已有语音、双电机和水枪的实测记录；泡泡效果与顶部效果仍待后续实现或评估。

| 模块 | 当前进展 | 验证边界与记录 |
|---|---|---|
| 语音交互 | 面包板保留“小D”的语音、OLED 和设备绑定，已联调状态查询、停止及动作指令 | [角色与提示词](docs/agent-role.md) · [语音联调](docs/audio-board-validation.md) |
| 行走与喷水 | 已完成双电机四方向空载、水枪启停、BOOT 提前停止；ct7 已完成并发动作、独立截止及全停的核心台架回归 | [基本台架](docs/breadboard-integration.md) · [并发记录](docs/concurrent-actions.md)；落地带载与完整供电验收待完成 |
| 局域网控制 | 当前面包板源码为 `2.0.3-ct12`：网页自动连接、长按行走与计时、独立喷水、语音并用，同通道冲突时网页优先 | [使用与验证](docs/lan-control.md)；ct12 已部署并完成实机无负载检查，200 ms 操作间隔尚未通过带载验收 |
| 机械结构 | 0.43 包含面包板浅托盘、超声波共存候选、前部双枪、双瓶背包，以及效果模块夹持和四板固定结构 | [模型与检查报告](hardware/model/README.md) · [装配图纸](hardware/model/CyberTrack-assembly-and-service.pdf)；实物适配、线管与固定强度待验证 |
| 泡泡效果 | 前部泡泡枪、储液瓶与管路已纳入布局，使用泡泡枪自带风扇 | [机械设计](docs/mechanical.md)；驱动联调、带液工作和实际出泡待验证 |
| 顶部效果 | 保留双火花视觉效果需求及被动机械占位 | [结构边界](docs/effects-mount.md)；未实现高压接线或驱动，安全、绝缘、液体共存与 EMC 未验收 |

主机测试、CAD 检查和短时台架结果各有适用范围，不能替代整机供电、温升、停止时延、制造或儿童使用验收。后续工作统一维护在 [TODO](TODO.md) 和[实施及验收计划](docs/verification-plan.md)。

## 从这里开始

### 查看机械设计

在[模型入口](hardware/model/README.md)查看整机视图、布局和拆装检查，使用 FreeCAD 打开 [CyberTrack.FCStd](hardware/model/CyberTrack.FCStd)。原生 FCStd 是几何依据；STEP 仅供布局交换，[装配 PDF](hardware/model/CyberTrack-assembly-and-service.pdf)用于结构评审，不是加工图。

### 开发固件

控制核心可在电脑上构建和测试，无需连接设备。需要 C11 编译器、CMake ≥ 3.16 和 Python ≥ 3.9，在仓库根目录执行：

```sh
cmake -S firmware -B build/firmware-host -DCMAKE_BUILD_TYPE=Debug
cmake --build build/firmware-host
ctest --test-dir build/firmware-host --output-on-failure
```

这组命令验证通用控制核心及协议／运行层。面包板适配、ESP32 无负载检查和独立台架是不同工程，构建、GPIO 与工具语义须按对应版本查阅：

- [固件总览](firmware/README.md)与[能力及接口手册](firmware/CAPABILITIES.md)：选择工程、了解接口和验证范围。
- [面包板适配](firmware/esp32-audio/README.md)：语音、网页、双电机与水枪控制的构建和部署说明。
- [ESP32 无负载检查](firmware/esp32/README.md)、[电机台架](firmware/esp32-motor-bench/README.md)与[MOS 台架](firmware/esp32-mos-bench/README.md)：各自的接线、版本和测试记录。

### 使用局域网控制

已部署对应面包板固件的设备与手机接入同一可互通局域网后，打开 `http://<设备 IP>:8080/`；设备 IP 可从 OLED 或串口读取。

- 按住方向键行走，松开停止行走；喷水单独选择时长并启动，可与行走同时进行。
- “全部停止”、BOOT 或语音停止会结束两路动作；停止后旧动作不自动恢复。
- 网页与语音可同时使用，同通道冲突时网页优先；两路停止后的操作间隔均为 200 ms。

完整操作、抢占规则和验证记录见[局域网控制说明](docs/lan-control.md)。当前网页没有用户身份认证，同局域网可访问设备的客户端可申请控制会话；页面状态为固件逻辑回执，没有轮速或水流反馈。

## 文档导航

| 想了解什么 | 入口 |
|---|---|
| 产品目标与已确认决定 | [产品需求](docs/requirements.md) · [决策和待补资料](docs/decisions.md) |
| 机械布局与装配维护 | [机械设计](docs/mechanical.md) · [模型与视图](hardware/model/README.md) · [装配说明](docs/assembly.md) |
| 电源、接线与采购 | [电源与接口](docs/power-and-interfaces.md) · [接线总表](docs/wiring.md) · [BOM](hardware/BOM.md) · [采购清单](hardware/procurement.md) |
| 控制架构与语音配置 | [系统架构](docs/architecture.md) · [智能体角色](docs/agent-role.md) · [灵矽接入](docs/linx-integration.md) |
| 固件接口与后续开发 | [固件入口](firmware/README.md) · [能力与接口](firmware/CAPABILITIES.md) · [固件计划](firmware/PLAN.md) |
| 当前待办与验收范围 | [TODO](TODO.md) · [实施及验收计划](docs/verification-plan.md) |
| 部件资料与来源 | [资料索引](docs/references.md) · [部件资产](hardware/components/) |

## 仓库结构

```text
docs/                  需求、决策、设计、接线与验证记录
hardware/components/   独立部件模型、厂商资料与实测记录
hardware/model/        整机 CAD、视图、装配图纸与检查报告
firmware/              控制核心、板级工程、协议与测试
scripts/               CAD 生成、布局检查与图纸生成脚本
```

## 许可证

项目采用 [Apache License 2.0](LICENSE)。供应商图片、原理图及数据手册的权利归原权利人，归档不改变其授权条件。
