# Seeed 114993115 与 A1 的 DVP 接口核对

**A1 现板无法直接连接。** ESP32-S3 支持并口采集，Seeed 在 XIAO ESP32S3 Sense 上提供了这款长排线模组的示例。CyberTrack A1 使用自己的主板、引脚与电源设计。J1 是 USB 设备维护口，J2 是 3.3 V OLED，J15 只有受控 5 V 和地，J1–J16 中没有摄像头连接器。[A1 接口表](README.md#外接接口) · [Seeed 对应模组与示例](https://wiki.seeedstudio.com/xiao_esp32s3_camera_usage/)

## A1 已布板的引脚

核对 PCB1 的 U1 PAD_NET 与生产包内 FlyingProbeTesting.json 的 U1 焊盘分组。模组为 ESP32-S3-WROOM-1-N16R8。下表按模组焊盘编号，GPIO 编号另列。[PCB1 原生板文件](CyberTrack-A1/pcb/PCB1.epcb2) · [A1 飞针网络](CyberTrack-A1-Gerber.zip) · [乐鑫模组资料](https://www.espressif.com/sites/default/files/documentation/esp32-s3-wroom-1_wroom-1u_datasheet_en.pdf)

| U1 焊盘 | GPIO | A1 用途 |
|---|---|---|
| 4–9 | 4、5、6、7、15、16 | 数字麦克风与功放，两套音频时钟和数据 |
| 10–12、17–22 | 17、18、8、9、10、11、12、13、14 | 两路效果使能、A/B 电机 PWM 与方向、扩展口使能 |
| 13、14 | 19、20 | USB D−、D+ |
| 24、32、33 | 47、39、40 | 说话与音量键 |
| 26、27、31 | 45、0、38 | SW2 重新使能、BOOT 停止、锁存状态 |
| 34、35、38、39 | 41、42、2、1 | OLED SDA/SCL、超声波 ECHO/TRIG |
| 15、16 | 3、46 | 板上空网，启动绑带 |
| 23、25 | 21、48 | 板上空网，使用前复核固件板型配置 |
| 28–30 | 35–37 | 焊盘空网，N16R8 模组内部 Octal PSRAM 占用 |
| 36、37 | 44、43 | 板上空网，UART0 RX/TX，复用影响调试与启动日志 |
| 1–3、40、41 | — | 地、3.3 V、CHIP_EN 与地焊盘 |

八位 DVP 需要 8 根数据、PCLK、VSYNC、行有效和 XCLK，共 **12 根时序信号**。SCCB 的 SDA/SCL 另计，即使与 OLED 共享控制器也需要跨电压域核对地址、上拉与上电状态。RST、PWDN 另需确定硬件时序或控制脚。扣除三根模组内部已用的脚后，A1 空网最多只有六根，其中两根是绑带，两根是 UART0。即便允许这六根全部改用，也凑不齐视频总线。

## 模组 24 针

| 功能 | FPC 脚号与信号 | 新主板设计约束 |
|---|---|---|
| 八位数据 | D0…D7 对应 Y2…Y9，依次为 19、21、22、20、18、16、14、12 | 模组输出至 S3 的并口采集引脚 |
| 同步与时钟 | 7 VSYNC、9 HSYNC、17 PCLK、13 MCLK | 前三路入主控，核实行有效模式及极性；主控输出 MCLK/XCLK |
| 控制 | 3 SDA、5 SCL、6 RST、8 PWDN、1 STROBE | SCCB 管理，RST/PWDN 按电源时序处理；预览无闪光需求 |
| 电源 | 4 AVDD 2.8 V、24 AFVDD 2.8 V、11 DOVDD 1.8 V、10 DVDD 1.5 V／内供 | 按模组针表设计，10 脚的外围处理按供应商参考电路确认 |
| 地 | 2 AGND、15 GND、23 AF-GND | 按模组应用电路连接与去耦 |

芯片概览列出多个可用 I/O 电压，本批候选按模组接线图的 1.8 V 设计。A1 主控现有 3.3 V，缺少摄像头用的 1.8 V 和 2.8 V 电源。不能用 3.3 V 直连模组时钟、复位或 SCCB 上拉，也不能假定 1.8 V 视频高电平符合 3.3 V 主控门限。[模组资料第 3 页](../components/seeed-114993115/Seeed-OV5640-MJY5OAF-F3M-V1.pdf)

已按单 S3、PDM 麦克风和 16 位 I/O 扩展器排出[下一版完整分配](camera-revision/README.md)，并按百台列出[成本预算](camera-revision/unit-cost.md)。

## A1 审核时的设计约束

先在同一张引脚表上完成音频、按键、视频和调试的分配。低速普通按键可评估迁到 I/O 扩展器，音频时钟可评估能否共用。保留停止、锁存和电机时序；并口数据和同步须进入支持摄像头采集的硬件。仅迁移三个按键仍有缺口，应在布板前证明整张表可行。

再选带锁 24P／0.5 mm 顶插座，匹配触点面、插入深度、0.30 mm 补强与开锁行程。按摄像头关停、掉电防反灌、模拟电源去耦设计供电。分别核算双向开漏 SCCB、主控至模组的时钟与控制、模组至主控的同步和数据所需电平转换、边沿及 PCLK 采样裕量。结构模型中的连接器是空间占位。工程板须验证反复启停、带 Wi-Fi 和音频的端到端预览、错帧与温升后才能定版。[FreeCAD 试装](../model/studies/front-camera/README.md)
