# CyberTrack 正式原理图文件

修订：A2，2026-10-30；新增主控侧 3.3 V 超声波接口。采用 KiCad 原生电气符号、引脚、导线、网络和分图组织，保留现有 ESP32-S3 开发板及外置功率模块。

**这是供审图的模块级电气原理图，尚未达到 PCB 制造放行状态。** 总输入保护和主电源控制电路未选型，MOS 下拉、保险和连接器参数待定；图中以 `TBD` 显式表示。没有绘制高压输出电路，也没有进行通电操作。

## 打开与编辑

- 主入口：[CyberTrack.kicad_pro](CyberTrack.kicad_pro)。使用 KiCad 打开项目，再进入原理图编辑器。
- 根图：[CyberTrack.kicad_sch](CyberTrack.kicad_sch)。也可直接打开，根图左下方的分图框可进入其余五页。
- 自定义符号：[CyberTrack.kicad_sym](CyberTrack.kicad_sym)；项目库表：[sym-lib-table](sym-lib-table)。原理图也内嵌所用符号，交付时保留整个目录。
- [六页 PDF](CyberTrack-schematic.pdf)：由同一份 KiCad 原理图直接导出，不是另外手绘的一份图。
- [可编辑工程包](CyberTrack-schematic-A2.zip)：包含六页原理图、项目库、PDF 和检查记录，解压后打开项目文件。本文跨出本目录的仓库链接仅在完整仓库中有效，不影响独立打开工程。

| 页 | 源文件 | 内容 |
|---|---|---|
| 1 | [CyberTrack.kicad_sch](CyberTrack.kicad_sch) | 电池输入、保护／主电源控制待选电路、主控检修断开、独立执行器切断、支路保险 |
| 2 | [control.kicad_sch](control.kicad_sch) | 同一块 ESP32-S3 开发板的 U1A／U1B、GPIO、外接 BOOT、保留音频／显示／按键接口；U1C 位于第 6 页 |
| 3 | [drive.kicad_sch](drive.kicad_sch) | MT3608、L298N、两台电机、六路外部默认低电平候选 |
| 4 | [effects.kicad_sch](effects.kicad_sch) | 独立水枪／泡泡 MOS、降压和 3.7 V 负载；两路受控负极分别命名 |
| 5 | [ignition-lv.kicad_sch](ignition-lv.kicad_sch) | GPIO21 共用 MOS 的低压预留，JP2 默认断开，U10／J9 在本审图装配中 DNP |
| 6 | [ultrasonic.kicad_sch](ultrasonic.kicad_sch) | U1C 的 3V3／GPIO1／GPIO2 至 U11 超声波模块，GND_SYS 共地；新引脚不推定排针位置 |

图中文字采用英文信号名及工程标注，便于与固件、模块丝印和 EDA 网络核对。`TBD` 表示待定，`DNP` 表示本修订装配不安装，`REVIEW ONLY` 表示供设计审阅。

## 图纸表达边界

1. **开发板保留。** U1A、U1B 与 U1C 是同一个开发板的三个符号单元，开发板内部 USB、稳压、复位、射频和 LED 不重复设计。参考原厂 PDF 的表达形式，没有照抄其排针号；当前面包板与独立台架板不能据外观假定为完全相同。
2. **逻辑引脚不是焊盘位置。** `IO8` 表示 GPIO8；`VIN+` 等表示模块端子丝印。自定义符号的 pin ID 不指定物理连接器顺序。A1 在引脚名中加入 `[Lxx/Rxx]` 照片位置：元件面朝前、天线上、USB 下，两排均从上向下计数 1–22；仍需逐线核对和插接试配。A2 中所有符号均排除 PCB 转移与生产 BOM，尚无封装。完成真实针序表和封装映射后，才能创建用于 PCB 的板内电路版本。
3. **外置模块按接口绘图。** JZ-MOS、P12、MT3608 和 L298N 保留成品模块，未虚构其内部电路。P12 的 EN／调压设置及原音频外设的供电／辅助脚未获完整记录，因此保留现有设置，并在图中说明未重建范围。
4. **X1 不是新增连接器。** 它集中表示原麦克风、功放、OLED 和按键的已知信号边界；既有外围供电与实际线束不因这张图改变。扬声器继续接原功放，不能接 GPIO 或擅自将一端接地。
5. **U2／U3 是必须完成的待选电路。** U2 表示输入保护功能，U3 表示主电源控制功能；不能把矩形符号当成已选购模块。SW1 仅表示现有拨动开关作为低电流请求触点的设计候选，实际触点关系未定。SW2 已由用户确认只切执行器供能、主控继续运行，型号、直流额定能力和装配位置另定。
6. **R1–R6 已选 10 kΩ、±1%、至少 0.1 W；R7–R9 与 F1–F7 仍待定。** 六路电机下拉按 L298 芯片参数计算，封装目标 0603，仍需验证实际模块偏置和启动状态。其余位置不能凭 `TBD` 下单。默认低电平电阻不能关断卡在高电平的 MCU；独立切断、启动／失电及信号反灌仍需验证。
7. **负极不能混接。** `WATER_SW_N`、`BUBBLE_SW_N`、`IGNITION_SW_N` 均与 `GND_SYS` 分开。P12 的公共负极属于本路 MOS 输出侧，不得额外接回系统地。主控供电、功率输入负极和控制参考地按图连接；共地不意味着功率经过主控排针。
8. **点火保持禁用。** JP2 打开、预留输出无接线；本审图装配的 U10／J9 标记 DNP。低压接口没有画两只实际点火负载或任何高压端，不能据此开展高压接线或通电试验。
9. **超声波使用主控侧 3.3 V。** U11 VCC 接 U1 3V3，TRIG 接 GPIO1，ECHO 接 GPIO2，GND 接 GND_SYS。按用户指定直连方案绘图，未添加未经选型的电平转换器或外部下拉；3V3 余量、模块版型、ECHO 峰值／失电状态和实际针序仍待核实。不得保留 ECHO 直连而改用 5 V 供电。四根线均在头部内，见[接线依据](../../docs/ultrasonic-ranging.md)。

保险、开关和检修连接件都是两端器件，网表记录其两侧为不同网络；网表不模拟其闭合状态、电阻、故障或器件内部导通。`PWR_FLAG` 仅向 ERC 声明预期供电路径，不能证明该路径实际已接通或符合额定要求。

## 设计输入与待确认参数

[参数清单](parameter-confirmation.md)列出 E01–E10、已知值、测点与可回填模板。[design-inputs.json](design-inputs.json)记录照片位置、R1–R6 的定值条件和用户确认的 SW2 分支，供生成脚本使用。照片辨识、芯片参数计算和实物验收分别记录；本轮没有现场通电测试。

## 验证及复现

2026-10-30 A2 验证见 [verification-current.json](verification-current.json)：从当前六页工程重新导出网表与 PDF，执行 ERC，并对网表及当前源码执行 112 项检查。新增检查覆盖 TRIG／ECHO 方向、3V3 供电、共地、直连端点、未虚构的排针位置，以及全部 A1 既有端子的连接保持；六页 PDF 渲染检查通过，驱动页文字同步为当前固件 A／右、B／左。工具版本、导出文件哈希和逐页检查见 [A2-export-check.json](checks/A2-export-check.json)；5 项回归测试包含 TRIG／ECHO 对调、误接 5 V、误接受控回流及错误信号方向的拒绝检查。未进行实物接线或通电测试，仍未制造放行。

[A1 原始审计](verification.json)、[A1 工程包](CyberTrack-schematic-A1.zip)及[扩展前的源码复核](checks/A1-source-recheck-20261030.json)按原字节保留；其旧哈希、五页 PDF 和 92 项检查只描述历史输入。完整 A2 导出校验绑定当时的源码、文档路径和文件哈希，可在 [A2 导出版本](https://github.com/miclle/cybertrack/tree/36c28fa36581dfc8bb5aff40fe74848fa137cef0)运行 `python3 scripts/check_current_audits.py` 复核。要单独核对现行固件引脚与已导出网表的连接，请在仓库根目录运行 `python3 scripts/check_schematic_netlist.py hardware/schematic/checks/CyberTrack.net.xml --output /tmp/cybertrack-connectivity.json`。

在安装了对应版本 KiCad 的环境中，可从仓库根目录复现导出和检查（`kicad-cli` 需在 PATH 中；A2 交付时执行过等效命令）：

```sh
kicad-cli sch export pdf --no-background-color --exclude-pdf-property-popups -o hardware/schematic/CyberTrack-schematic.pdf hardware/schematic/CyberTrack.kicad_sch
kicad-cli sch export netlist --format kicadxml -o hardware/schematic/checks/CyberTrack.net.xml hardware/schematic/CyberTrack.kicad_sch
kicad-cli sch erc --format json --severity-all --exit-code-violations -o hardware/schematic/checks/erc.json hardware/schematic/CyberTrack.kicad_sch
python3 scripts/check_schematic_netlist.py hardware/schematic/checks/CyberTrack.net.xml --output hardware/schematic/checks/connectivity.json
python3 scripts/tests/test_schematic_netlist.py
```

[生成脚本](../../scripts/generate_schematic.py)用于重建初始源文件。**重新生成会覆盖可编辑原理图**；直接在 KiCad 中修改后，先保存并审查差异，不要无条件重跑生成器。PDF 始终应从最终保存的根原理图重新导出。

完整设计约束和制板前资料要求见[原理图设计与 PCB 打板](../../docs/schematic-and-pcb.md)。固件引脚依据见 [action_outputs.h](../../firmware/esp32-audio/action_outputs.h) 与 [cybertrack_tools.cc](../../firmware/esp32-audio/cybertrack_tools.cc)，外围信号依据见[面包板工程](../../firmware/esp32-audio/README.md)。部件参数和证据见[接线总表](../../docs/wiring.md)、[电源与接口](../architecture/README.md)及对应部件记录。
