# CyberTrack

双履带语音交互玩具机器人，将语音对话、履带行走、喷水和泡泡效果组合成有角色感的机械玩具。

CyberTrack 采用 ESP32-S3 面包板与灵矽语音交互，支持手机局域网网页控制；机械设计采用切面头盔、固定颈架、前部双枪和双液体背包。

[模型与图纸](hardware/model/README.md) · [打印项目](hardware/model/lean-print/README.md) · [面包板固件](firmware/esp32-audio/README.md) · [局域网控制](docs/lan-control.md) · [待办](TODO.md)

## 样机演示

**6 分钟实拍**：样机在地面上的移动、转向与泡泡效果展示。点击下方播放器即可播放。

https://github.com/user-attachments/assets/127dc3f1-0a8f-4abf-b4e5-f43b6fe16fb7

[下载原始视频](artifact/cybertrack-prototype-demo-6min.mp4) · [制作过程与全部素材](artifact/README.md)

影像记录了制作与演示时的样机状态；具体固件、供电配置与工程验收以对应验证记录为准。

## 制作过程与样机照片

从双电机台架、底盘装配到头部电子件安装，再看样机的正面、侧面和背面。点击照片可查看原图。

<table>
  <tr>
    <td width="50%" valign="top"><a href="artifact/03-dual-motor-bench.jpg"><img src="artifact/previews/03-dual-motor-bench.jpg" alt="双电机台架接线" width="100%"></a><br>双电机台架接线</td>
    <td width="50%" valign="top"><a href="artifact/19-chassis-assembly-14.jpg"><img src="artifact/previews/19-chassis-assembly-14.jpg" alt="底盘装配与接线" width="100%"></a><br>底盘装配与接线</td>
  </tr>
  <tr>
    <td width="50%" valign="top"><a href="artifact/26-head-breadboard-installation.jpg"><img src="artifact/previews/26-head-breadboard-installation.jpg" alt="头部面包板与扬声器安装" width="100%"></a><br>头部面包板与扬声器安装</td>
    <td width="50%" valign="top"><a href="artifact/27-prototype-front-workbench.jpg"><img src="artifact/previews/27-prototype-front-workbench.jpg" alt="样机正面：超声波模块与双枪布局" width="100%"></a><br>样机正面：超声波模块与双枪布局</td>
  </tr>
  <tr>
    <td width="50%" valign="top"><a href="artifact/28-prototype-water-gun-side.jpg"><img src="artifact/previews/28-prototype-water-gun-side.jpg" alt="样机侧面：履带、颈架与水枪" width="100%"></a><br>样机侧面：履带、颈架与水枪</td>
    <td width="50%" valign="top"><a href="artifact/29-prototype-rear-reservoirs.jpg"><img src="artifact/previews/29-prototype-rear-reservoirs.jpg" alt="样机背面：双液体瓶与管路" width="100%"></a><br>样机背面：双液体瓶与管路</td>
  </tr>
</table>

[查看全部 33 张照片与 2 段视频](artifact/README.md)

## CAD 模型

以下视图于 **2026-10-27** 从当前 [CyberTrack.FCStd](hardware/model/CyberTrack.FCStd) 导出，展示整机外形、双枪与履带布局，以及背部双瓶结构。点击图片可查看大图。

<table>
  <tr>
    <td width="50%" valign="top"><a href="hardware/model/readme-views/front-iso.png"><img src="hardware/model/readme-views/front-iso.png" alt="CyberTrack CAD 前侧整体视图：头壳、双枪与双履带" width="100%"></a><br>前侧整体视图</td>
    <td width="50%" valign="top"><a href="hardware/model/readme-views/front.png"><img src="hardware/model/readme-views/front.png" alt="CyberTrack CAD 正面视图：超声波探头与双枪布局" width="100%"></a><br>正面布局</td>
  </tr>
  <tr>
    <td width="50%" valign="top"><a href="hardware/model/readme-views/side.png"><img src="hardware/model/readme-views/side.png" alt="CyberTrack CAD 侧面视图：履带、颈架与背包" width="100%"></a><br>侧面结构</td>
    <td width="50%" valign="top"><a href="hardware/model/readme-views/rear-iso.png"><img src="hardware/model/readme-views/rear-iso.png" alt="CyberTrack CAD 后侧视图：双瓶背包与管路" width="100%"></a><br>后侧与双瓶背包</td>
  </tr>
</table>

*以上为 CAD 模型视图，颜色用于区分零件，不代表实物材料或打印配色；样机状态见上方实拍。模型修订见[模型入口](hardware/model/README.md)，装配、打印工艺与持续带载的完整验收仍待完成。*

## 当前状态

截至 **2026-10-27**，项目已进入**样机联调与整机验证阶段**。已有基本组装样机，制作过程及多角度实拍已归档，[6 分钟运行视频](#样机演示)展示了地面移动、转向和泡泡效果。最近一次有记录的面包板部署版本为 **`2.0.3-ct21`**，用户已现场确认前进、后退、左转、右转均正常；机械设计与打印包继续迭代，见[模型入口](hardware/model/README.md)。

已有语音、水枪及停止功能的分项台架记录，四路控制与组合模式已有软件实现。样机照片、运行视频和四方向现场反馈分别记录了对应进展；整机供电、持续带载、停止性能和完整故障验收仍未完成，视频中的固件与供电配置也尚未逐项核对。

| 模块 | 已有进展 | 尚待验证／证据入口 |
|---|---|---|
| 语音交互 | 保留“小D”语音、OLED 和设备绑定；已有状态、停止及行走／喷水联调记录 | 新增泡泡、点火、狂暴模式的真人语音回归待完成；[角色维护](docs/agent-role.md) · [语音记录](docs/audio-board-validation.md) |
| 行走与喷水 | 样机视频已有地面移动与转向；ct21 修正左右履带映射后，用户确认四方向正常。水枪启停、BOOT 提前停止及 ct7 并发与独立截止已有台架记录 | 持续带载、不同工况方向回归、定量电流／温升、停止时延与距离仍待验证；[ct21 部署及现场反馈](firmware/esp32-audio/startup-ct21.json) · [集成台架](docs/breadboard-integration.md) · [并发记录](docs/concurrent-actions.md) |
| 局域网控制 | 行走／喷水／泡泡长按、独立定时、四路全停与语音并用；动作结束后的页面提示已修复；ct21 部署已核对启动联网、页面与源码一致及输出全关 | ct21 部署检查未启动执行器；装车后的语音／网页并用、失联及故障回归仍需完整验证；[使用说明](docs/lan-control.md) · [部署记录](firmware/esp32-audio/startup-ct21.json) |
| 泡泡与点火 | 样机视频已有实际出泡画面；泡泡独立 MOS、双点火共用一块 MOS 的低压控制固件已实现，四路可并行、分别限时 | 泡泡持续运行、定时与提前停止、新通道接线仍待系统核验；底盘前方双火花的高压接线、安全、绝缘、液体共存及 EMC 未验收；[运行视频](#样机演示) · [效果控制](docs/effects-control.md) |
| 狂暴模式 | 网页和语音均可请求限时组合：左转、喷水、泡泡及间歇点火，最长 30 秒 | 动作时序证据来自主机测试，真人口述与带载待验；[模式说明](docs/lan-control.md#ct17-狂暴模式) · [语音接入](docs/lan-control.md#ct18-语音启动) |
| 机械与打印 | 已有履带底盘、双枪、头部面包板及双瓶背包的基本组装样机和制作过程照片；CAD 与打印包持续迭代 | 实物装配记录不等于全部打印件验收；材料、朝向、支撑、公差、紧固、拆装和承载仍待系统验证；[制作与样机照片](artifact/README.md#照片) · [现行模型与打印包](hardware/model/README.md) · [历史合并检查](hardware/model/print-consolidation-audit.json) |
| 电源 | 已换为辰克 5 V 电池包，保留 12 V 升压电机支路；水枪和泡泡工作电压为 3.7 V | 新电池输出、分线保护、组合负载与续航待核；旧电源台架结果不迁移；[电源方案](docs/power-and-interfaces.md) · [电池资料](hardware/components/ck-5v-battery/README.md) |

实拍记录制作与运行表现，用户反馈确认相应现场现象；主机测试覆盖软件逻辑，CAD 检查核对所建几何关系，台架记录只覆盖对应版本与工况。这些证据不能互相替代，也不构成完整的整机制造、电气或儿童使用验收。

接下来围绕现有样机收敛三方面：补齐打印件实物适配、紧固与拆装验证；测量新电源及各支路的电流、温升、停止性能和组合负载；完成装车后的方向、液路、语音与网页故障回归。具体任务与验收条件统一维护在 [TODO](TODO.md) 和[实施及验收计划](docs/verification-plan.md)。

## 从这里开始

### 查看模型、补打与装配

使用 FreeCAD 打开 [CyberTrack.FCStd](hardware/model/CyberTrack.FCStd)，当前几何、局部修订及检查入口见[模型说明](hardware/model/README.md)。原生 FCStd 是几何依据，STEP 用于交换；部分历史 STEP 体积比较仍超过阈值，不能把交换文件一概视为原生几何等价。

- **现行打印项目**：[Lean 29 件／6 盘](hardware/model/lean-print/README.md)及[3MF 文件](hardware/model/lean-print/CyberTrack-Lean-6plates.3mf)。已按 P2S、0.4 mm 喷嘴与 PLA Basic 配置各零件的朝向、层高、墙数和支撑，并完成切片与相应几何／路径检查。用于补打或复现样机时，按所需零件选盘，已打印件不重复打印；切片估算与检查不代表实物强度、配合或整机验收。
- **头部与单件文件**：[0.58 头部整体打印与螺丝适配](docs/head-shell-print.md)说明 PP07 头壳、配套 PP05 冠盖及独立面包板托盘；[单件目录](hardware/model/print-parts/README.md)提供 STL／STEP 与专项记录。导孔试拧、螺丝保持力与重复拆装仍待实物核验，单件 STL 不包含支撑配置。
- **装配与维护参考**：[装配说明](docs/assembly.md)与[装配维护图册](hardware/model/CyberTrack-assembly-and-service.pdf)保留各修订的特征定位和拆装参考，其中旧分件、孔形及配合状态须结合现行模型与专项记录阅读。实际打印分件以 Lean 清单为准，已合并的源特征不独立打印；[0.51 六件图册](hardware/model/print-parts/print-parts.pdf)仅作历史合并参考。

[Ready 用户排盘快照](hardware/model/print-ready/README.md)与 Lean 分别保留，盘序和零件范围不同，不混用盘号或切片估算。样机基本装配已有实拍记录；剩余适配、紧固、拆装与承载验证继续按 [TODO](TODO.md) 跟进。

### 开发固件

控制核心可在电脑上构建和测试，无需连接设备。需要 C11 编译器、CMake ≥ 3.16 和 Python ≥ 3.9，在仓库根目录执行：

```sh
cmake -S firmware -B build/firmware-host -DCMAKE_BUILD_TYPE=Debug
cmake --build build/firmware-host
ctest --test-dir build/firmware-host --output-on-failure
```

这组命令验证通用控制核心及协议／运行层，不包含当前面包板的全部功能。现用语音与网页控制从 `firmware/esp32-audio/` 开始，源码版本与最近部署记录均为 `2.0.3-ct21`；通过 overlay 接入固定的上游源码，构建仍使用 ESP-IDF v5.5.1、原始源码及组件缓存。源码导出还需满足面包板适配说明中的 Python 与依赖要求。各工程的 GPIO 与工具语义须分别查阅：

- [面包板适配](firmware/esp32-audio/README.md)：现用语音、网页和四路控制的构建、部署及逐版本记录。
- [固件总览](firmware/README.md)与[能力及接口手册](firmware/CAPABILITIES.md)：通用核心、工程差异和接口；现用面包板的四路控制、约 80% 电机 PWM 与左右履带映射以[面包板当前记录](firmware/esp32-audio/README.md)为准，旧台架记录保留各自版本边界。
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
| 机械布局、打印与装配 | [模型与当前修订](hardware/model/README.md) · [Lean 六盘打印项目](hardware/model/lean-print/README.md) · [头部打印与螺丝](docs/head-shell-print.md) · [装配参考](docs/assembly.md) |
| 电源、接线与采购 | [电源与接口](docs/power-and-interfaces.md) · [接线总表](docs/wiring.md) · [BOM](hardware/BOM.md) · [采购清单](hardware/procurement.md) |
| 原理图设计与 PCB 打板 | [KiCad 原理图工程](hardware/schematic/README.md) · [五页原理图 PDF](hardware/schematic/CyberTrack-schematic.pdf) · [设计与制板要求](docs/schematic-and-pcb.md)；A1 为模块级审图稿，尚未达到 PCB 制造放行状态；[待确认参数](hardware/schematic/parameter-confirmation.md) |
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
  lean-print/          现行 29 件六盘项目、切片与交付检查
  print-parts/         单件 STL／STEP、头部打印及历史合并记录
  print-ready/         用户 Ready 排盘快照与精简前历史记录
firmware/              控制核心、板级工程、协议与测试
  esp32-audio/         现用面包板的语音、网页及执行器适配
scripts/               CAD 生成、布局检查与图纸生成脚本
```

## 许可证

项目采用 [Apache License 2.0](LICENSE)。供应商图片、原理图及数据手册的权利归原权利人，归档不改变其授权条件。
