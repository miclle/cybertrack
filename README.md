# CyberTrack

双履带语音交互玩具机器人，将语音对话、履带行走、喷水和泡泡效果组合成有角色感的机械玩具。

CyberTrack 采用 ESP32-S3 面包板与灵矽语音交互，支持手机局域网网页控制；机械设计采用切面头盔、固定颈架、前部双枪和双液体背包。

[模型与图纸](hardware/model/README.md) · [打印候选](hardware/model/print-parts/README.md) · [面包板固件](firmware/esp32-audio/README.md) · [局域网控制](docs/lan-control.md) · [待办](TODO.md)

## 样机演示

**6 分钟实拍**：样机在地面上的移动、转向与泡泡效果展示。点击下方播放器即可播放。

https://github.com/user-attachments/assets/127dc3f1-0a8f-4abf-b4e5-f43b6fe16fb7

[下载原始视频](artifact/cybertrack-prototype-demo-6min.mp4) · [制作过程与全部素材](artifact/README.md)

影像记录了制作与演示时的样机状态；具体固件、供电配置与工程验收以对应验证记录为准。

![CyberTrack 整机 CAD 装配候选](hardware/model/assembly.png)

*0.53 CAD 装配候选；实物适配、打印工艺与整机带载尚未验收。*

## 当前状态

截至 **2026-10-26**，项目处于**机械试制准备与分项台架联调阶段**。当前工作区机械版本为 **0.53**，面包板固件源码及最近一次部署记录为 **`2.0.3-ct19`**。已有语音、双电机空载和水枪的分项实测；四路控制及组合模式已有软件实现，整机供电、装车运行与完整故障验收仍未完成。

| 模块 | 已有进展 | 尚待验证／证据入口 |
|---|---|---|
| 语音交互 | 保留“小D”语音、OLED 和设备绑定；已有状态、停止及行走／喷水联调记录 | 新增泡泡、点火、狂暴模式的真人语音回归待完成；[角色维护](docs/agent-role.md) · [语音记录](docs/audio-board-validation.md) |
| 行走与喷水 | 双电机四方向空载、水枪启停、BOOT 提前停止，以及 ct7 并发与独立截止已有台架记录 | 装车方向、履带带载、定量电流／温升及停止时延；[集成台架](docs/breadboard-integration.md) · [并发记录](docs/concurrent-actions.md) |
| 局域网控制 | 行走／喷水／泡泡长按、独立定时、四路全停与语音并用；ct19 修复动作结束后的页面提示 | ct19 已记录刷写、启动联网及页面一致性，部署检查未启动执行器；[使用说明](docs/lan-control.md) · [部署记录](firmware/esp32-audio/startup-ct19.json) |
| 泡泡与点火 | 泡泡独立 MOS、双点火共用一块 MOS 的低压控制固件已实现；四路可并行，分别限时 | 泡泡实际出泡与新通道接线待验；底盘前方双火花的高压接线、安全、绝缘、液体共存及 EMC 未验收；[效果控制](docs/effects-control.md) |
| 狂暴模式 | 网页和语音均可请求限时组合：左转、喷水、泡泡及间歇点火，最长 30 秒 | 动作时序证据来自主机测试，真人口述与带载待验；[模式说明](docs/lan-control.md#ct17-狂暴模式) · [语音接入](docs/lan-control.md#ct18-语音启动) |
| 机械与打印 | 0.53新增[中央外装电源开关](docs/power-switch.md)，两颗自攻螺丝从上方固定；沿用0.51将 58 个设计特征归并为 6 个单实体打印候选，提供 STL、STEP 和图册，已有融合及网格回读检查 | 六件仅是本轮合并范围；材料、朝向、支撑、公差、拆装和承载待验；[合并说明](docs/print-consolidation.md) · [检查报告](hardware/model/print-consolidation-audit.json) |
| 电源 | 已换为辰克 5 V 电池包，保留 12 V 升压电机支路；水枪和泡泡工作电压为 3.7 V | 新电池输出、分线保护、组合负载与续航待核；旧电源台架结果不迁移；[电源方案](docs/power-and-interfaces.md) · [电池资料](hardware/components/ck-5v-battery/README.md) |

主机测试覆盖相应用例的软件逻辑，CAD 检查核对所建几何的关系，台架记录只覆盖对应版本与工况。它们不能互相替代，也不构成整机制造、电气或儿童使用验收。

接下来主要收敛三方面：打印候选的实物试配与拆装；新电源及各支路的电流、温升和停止验证；装车后的方向、液路、语音与网页故障回归。具体任务与验收条件统一维护在 [TODO](TODO.md) 和[实施及验收计划](docs/verification-plan.md)。

## 从这里开始

### 查看模型与准备试打

使用 FreeCAD 打开 [CyberTrack.FCStd](hardware/model/CyberTrack.FCStd)，整机视图、布局和拆装检查见[模型入口](hardware/model/README.md)。原生 FCStd 是几何依据，STEP 仅供布局交换；部分 STEP 体积比较仍超过阈值，不能视为原生几何等价。

- [0.51 打印候选清单](hardware/model/print-parts/README.md)与[六件图册](hardware/model/print-parts/print-parts.pdf)：用于切片和试配准备，尚未确定打印朝向、支撑或材料参数，也不是全机打印包。
- [0.50 装配图册](hardware/model/CyberTrack-assembly-and-service.pdf)：保留为特征级参考；其中源特征的独立图卡不再意味着逐件打印，当前分件以 0.51 清单为准。

### 开发固件

控制核心可在电脑上构建和测试，无需连接设备。需要 C11 编译器、CMake ≥ 3.16 和 Python ≥ 3.9，在仓库根目录执行：

```sh
cmake -S firmware -B build/firmware-host -DCMAKE_BUILD_TYPE=Debug
cmake --build build/firmware-host
ctest --test-dir build/firmware-host --output-on-failure
```

这组命令验证通用控制核心及协议／运行层，不包含当前面包板的全部功能。开发现用语音与网页控制时，从 `firmware/esp32-audio/` 开始；它通过 overlay 接入固定版本的上游源码，构建需要 ESP-IDF v5.5.1、原始源码及组件缓存。各工程的 GPIO 与工具语义须分别查阅：

- [面包板适配](firmware/esp32-audio/README.md)：现用语音、网页和四路控制的构建、部署及逐版本记录。
- [固件总览](firmware/README.md)与[能力及接口手册](firmware/CAPABILITIES.md)：通用核心、工程差异和接口；面包板新增功能结合 ct13–ct19 记录阅读。
- [ESP32 无负载检查](firmware/esp32/README.md)、[电机台架](firmware/esp32-motor-bench/README.md)与[MOS 台架](firmware/esp32-mos-bench/README.md)：各自的接线、版本和测试记录。

### 使用局域网控制

已部署对应面包板固件的设备与手机接入同一可互通局域网后，打开 `http://<设备 IP>:8080/`，页面自动申请控制会话；设备 IP 可从 OLED 或串口读取。以下为当前软件操作规则，各执行器的实物验证状态见上表。

- **行走**：按住方向键持续行走，松开停止本路；语音单次行走最多 3 秒。
- **喷水／泡泡**：各有 1／3／5／10／30 秒按钮和“按住持续”；长按由短租期续约维持，松开只停止本路。
- **点火**：提供 1／3／5 秒按钮，软件单次上限 5 秒；停止后至少等待本次实际软件开启时长。该间隔不代表热保护或硬件时限验收。
- **狂暴模式**：网页提供 5／10／30 秒，语音默认 5 秒、最多 30 秒；四路就绪后整体启动，点火按 1 秒开启与至少等长间隔调度。
- **停止与冲突**：“全部停止”、BOOT 或语音停止关闭四路；旧动作不自动恢复。普通动作同通道冲突时网页优先，行走／喷水／泡泡停止后间隔 200 ms；组合模式的抢占规则见专项说明。

完整操作、失租／断连处理和验证记录见[局域网控制说明](docs/lan-control.md)。当前网页没有用户身份认证，同局域网可访问设备的客户端可申请控制会话；页面显示固件逻辑回执，没有轮速、水流或火花的物理反馈。

## 文档导航

| 想了解什么 | 入口 |
|---|---|
| 产品目标与已确认决定 | [产品需求](docs/requirements.md) · [决策和待补资料](docs/decisions.md) |
| 机械布局、打印与装配 | [机械设计](docs/mechanical.md) · [模型与视图](hardware/model/README.md) · [合并打印](docs/print-consolidation.md) · [装配说明](docs/assembly.md) |
| 电源、接线与采购 | [电源与接口](docs/power-and-interfaces.md) · [接线总表](docs/wiring.md) · [BOM](hardware/BOM.md) · [采购清单](hardware/procurement.md) |
| 原理图设计与 PCB 打板 | [KiCad 原理图工程](hardware/schematic/README.md) · [五页原理图 PDF](hardware/schematic/CyberTrack-schematic.pdf) · [设计与制板要求](docs/schematic-and-pcb.md)；A1 已补引脚位置及电机下拉；[待确认参数](hardware/schematic/parameter-confirmation.md) |
| 控制架构与语音配置 | [系统架构](docs/architecture.md) · [智能体角色](docs/agent-role.md) · [灵矽接入](docs/linx-integration.md) |
| 网页操作与效果控制 | [局域网控制](docs/lan-control.md) · [泡泡与点火](docs/effects-control.md) · [面包板固件](firmware/esp32-audio/README.md) |
| 固件接口与后续开发 | [固件入口](firmware/README.md) · [能力与接口](firmware/CAPABILITIES.md) · [固件计划](firmware/PLAN.md) |
| 当前待办与验收范围 | [TODO](TODO.md) · [实施及验收计划](docs/verification-plan.md) |
| 部件资料与来源 | [资料索引](docs/references.md) · [部件资产](hardware/components/) |

## 仓库结构

```text
artifact/              制作过程照片、样机演示视频与素材索引
docs/                  需求、决策、设计、接线与验证记录
hardware/components/   独立部件模型、厂商资料与实测记录
hardware/model/        整机 CAD、视图、装配图纸与检查报告
  print-parts/         0.51 六组合并打印候选与图册
firmware/              控制核心、板级工程、协议与测试
  esp32-audio/         现用面包板的语音、网页及执行器适配
scripts/               CAD 生成、布局检查与图纸生成脚本
```

## 许可证

项目采用 [Apache License 2.0](LICENSE)。供应商图片、原理图及数据手册的权利归原权利人，归档不改变其授权条件。
