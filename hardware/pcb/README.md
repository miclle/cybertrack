# CyberTrack 一体主板

[A2 摄像头主板原生工程](CyberTrack-A2/CyberTrack-A2.eprj3)收录右前脸 Seeed 114993115 的 DVP 总线、供电及电平转换。复制时保留整个 CyberTrack-A2 目录。[电路与排线针序](camera-revision/README.md) · [A2 样板 Gerber、钢网与钻孔](CyberTrack-A2-Gerber.zip) · [A2 检查记录](verification-A2.json) · [FreeCAD 插拔试装](../model/studies/front-camera/CyberTrack-A2-front-camera.FCStd)

## A1 工程样板

用嘉立创 EDA 专业版打开 [CyberTrack-A1.eprj3](CyberTrack-A1/CyberTrack-A1.eprj3)，在工程树中选择 PCB1。复制时保留整个 `CyberTrack-A1/` 目录。A1 为 96 × 80 mm 四层工程样板，集成 ESP32-S3-WROOM-1-N16R8、音频、3.3 V 主控电源、12 V 升压、L298P 双履带驱动及三路受控 5 V 电源输出。

[布板预览](CyberTrack-A1.png) · [样板 Gerber 与钻孔](CyberTrack-A1-Gerber.zip) · [装配 STEP](CyberTrack-A1-STEP.zip) · [BOM](BOM-A1.md) · [校验记录](verification-A1.json) · [A0 旧版接口与文件](A0.md)

六页原理图与 PCB 共 119 个器件位号、79 个已连接网络。373 个已分配引脚均经网表比对，并核对了 Gerber 包飞针测试数据中的网络分组。嘉立创 EDA 原生 DRC 违规 0 项，未布通飞线 0 条。

前置 Seeed 摄像头的 DVP 时序线、电压和可用引脚见[逐组核对](camera-dvp.md)。下一版的[完整引脚分配](camera-revision/README.md)和[整机单台成本](camera-revision/unit-cost.md)供改板评审。

## 三路受控 5 V

电源路径为 J8 电池 → F1 → 主电源开关 → F3 → Q5 → J10 外接 SW2 → 5V_ACT → 各路保险 → 各路高侧开关 → 输出插座 1 脚。三个插座均为 XH 型、有方向的 2.50 mm 两针插座，2 脚直接接系统地。J13、J14 向枪内原有 P12 输入端供电，P12 输出约 3.7 V 接泵或风机。线束压接后从插座焊盘到 P12 输入逐针复核极性。

| 接口 | 控制 | 高侧开关与保险 | 限流电阻 | 样板典型限流点 |
|---|---|---|---:|---:|
| J13 WATER | GPIO18 | U7、F5 | R34，45.3 kΩ | 1.22 A |
| J14 BUBBLE | GPIO17 | U8、F6 | R37，45.3 kΩ | 1.22 A |
| J15 AUX | GPIO14（模组 22 脚） | U9、F7 | R40，100 kΩ | 0.55 A |

U7–U9 采用 TPS25221DBVR，切换标称 5 V 支路的正极。各路 EN 串接 100 Ω，开关处有独立 10 kΩ 下拉。每个开关就近配置 1 µF 输入电容和 10 µF 输出电容。芯片有软启动、限流及过温保护，FAULT 开漏引脚留空。SW2 可一起切除三路和电机支路电源，主控由 F2 单独供电。输出带载电压取决于电池、线束、开关和铜箔压降。[TI TPS25221 数据手册，第 7、9 节](https://www.ti.com/lit/ds/symlink/tps25221.pdf)

表中数值为工程样板设置。按 TI 式（1）和 1% 电阻计算，水枪及泡泡支路限流点约为 1.10–1.32 A，扩展支路约为 0.48–0.61 A。每口的持续负载能力与同时带载总额均待实测。J15 预留给额定 5 V 外设；后续接入裸电机或线圈时，应在负载端配置与电流和关断能量匹配的续流保护。A1 版 ct80 驱动 GPIO18、GPIO17，并将扩展口使能 GPIO14 保持低电平。复位时三路由 EN 下拉保持关闭。[现有固件引脚](../../firmware/esp32-audio/action_outputs.h)

## SW2 断电与恢复

SW2 需要两组机械联动、相互绝缘的触点。J10 接能分断执行器总直流电流的主触点，J16 接 RUN 时闭合的辅助干接点。辅助触点需在主触点断开前或同时断开，在主触点闭合后或同时闭合。J16 仅接板上 3.3 V 逻辑，两个接口分别接线。

打开 SW2 时，主触点切断 5V_ACT，同时 R42 将 U10 的异步清零端拉低。U10 的 Q 输出变低并关断 Q6、Q5，即使两个开关动作都发生在两次固件采样之间，重新合上 SW2 也会保持关断。U11 在主控电源上电或欠压复位时经辅助触点清零 U10。J16 拔出时 R42 同样保持清零。

A1 版 ct80 通过 GPIO38 读取 Q，撤销旧网页会话、语音请求及序列。安全任务先把电机、喷水、泡泡和扩展口的控制输出清零，再通过 GPIO45 发脉冲使能 Q5。执行器动作需要新指令。GPIO45 是 VDD_SPI 启动配置脚，R43 的 10 kΩ 下拉配合其复位默认电平。构建 A1 固件时需给 `prepare.py` 加 `--mainboard-a1`。[固件构建说明](../../firmware/esp32-audio/README.md#重现构建) · [ESP32-S3-WROOM-1 数据手册，第 4 节](https://www.espressif.com/sites/default/files/documentation/esp32-s3-wroom-1_wroom-1u_datasheet_en.pdf)

## 外接接口

以下顺序按 EDA 的焊盘编号，从 1 脚起读。与现有线束对接时以实际插座配对方向核对。各分支电流返回自己的功率接口。

| 位号 | 接口 | 焊盘顺序或定义 |
|---|---|---|
| J1 | USB-C 设备维护 | D− 经 R5 到 GPIO19，D+ 经 R6 到 GPIO20，两根 CC 各接 5.1 kΩ 下拉；VBUS 无板内供电连接 |
| J2 | 3.3 V OLED | 3V3、GND、SCL（GPIO42）、SDA（GPIO41） |
| J3 | 3.3 V 超声波 | 3V3、TRIG（GPIO1）、ECHO（GPIO2）、GND |
| J4 | 面板按键 | GND、说话（GPIO47）、音量加（GPIO40）、音量减（GPIO39） |
| J5 | 扬声器 | SPK_P、SPK_N，两根均为功放输出 |
| J6 | 外接 BOOT／本地停止 | GPIO0、GND，常开瞬时触点 |
| J7 | 外接复位 | CHIP_EN、GND，常开瞬时触点 |
| J8 | 电池输入 | +5 V、GND |
| J9 | SW1 主电源请求 | Q2 栅极请求、GND，闭合接通主电源 |
| J10 | SW2 执行器切断 | ACT_FEED、5V_ACT，串联 SW2 的直流主触点，断开后 F2 主控支路继续供电 |
| J11、J12 | 左右电机 | J11 为 MA1、MA2；J12 为 MB1、MB2。装机时核对 A/B 对应履带和正转方向 |
| J13 | 水枪，WATER | 受控 +5 V、GND。接枪内 P12 的 IN+、GND |
| J14 | 泡泡枪，BUBBLE | 受控 +5 V、GND。接枪内 P12 的 IN+、GND |
| J15 | 预留扩展，AUX | 受控 +5 V、GND。预留给带明确用电规格的 5 V 外设 |
| J16 | SW2 联动辅助触点 | 1 脚 ACT_POR_N，2 脚 ACT_CLR_N，接 SW2 的 RUN 常开辅助干接点 |

## 样板验证

- F1–F7 仅预留 2410 焊盘，保险定值待实测，均已从装配 BOM 排除。先核对电池极性，用限流电源和假负载逐口测量开启、关闭及限流点。在 J13／J14 接入完整枪体后分别记录启动峰值、持续电流和枪内 P12 的带载输出，最后再验证并发负载时的总电流、压降和温升。
- 断电时逐针检查 J13–J15 的 2 脚共地、三个正极独立。核对复位、控制引脚高阻、SW2 断开及恢复时各口电压、输出电容放电和实际停止时间。用限流电源、假负载和示波器同时观察 J10、ACT_ARMED、各路 EN 与受控输出。分别验证上电、拔掉 J16、动作中断开及快速重合 SW2。重合后旧动作应保持停止，重新发出指令才应启动。测量两组触点实际先后顺序及 Q5 在并发负载下的压降和温升。
- 目标板厚 1.6 mm，四个 Ø2.8 mm 安装孔。最终 STEP 在整机 CAD 中与头壳、托盘、供液管及已有线束走廊的相交体积均为 0 mm³，穿板端子下端至托盘的最小间隙约为 1.39 mm。实物还需核对支柱、三组配对插头、线束弯曲空间、天线及麦克风声道。USB-C 维护时由外部 5 V 给主板供电。U5 封装的 0.20 mm 散热过孔填孔工艺和 J1 工程焊盘按首件复核。[整机装配](../../docs/assembly.md) · [电源测量表](../schematic/parameter-confirmation.md)
