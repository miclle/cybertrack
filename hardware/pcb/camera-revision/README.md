# v2 前摄主板引脚方案

保留 Seeed 114993115 的右前脸光轴 (−31, −80, 190) mm。下一版继续用一块 96 × 80 mm 四层定制 PCB 和一颗 ESP32-S3-WROOM-1-N16R8。A2 原理图与 PCB 已采用下列分配。表内 FPC 针号均指模组承认书针号。J17 焊盘号 = 25 − FPC 针号。[A2 工程](../CyberTrack-A2/CyberTrack-A2.eprj3) · [核对记录](../verification-A2.json) · [镜头试装](../../model/studies/front-camera/README.md) · [A1 接口缺口](../camera-dvp.md) · [整机成本](unit-cost.md)

## ESP32-S3 完整引脚表

方向以主控为准。GPIO0、3、45、46 四个绑带保留 A1 复位条件，GPIO35–37 保留给八线 PSRAM。GPIO22–34 并非本模组可分配的外设焊盘。每行第一列为模组焊盘号。[模组资料](https://www.espressif.com/sites/default/files/documentation/esp32-s3-wroom-1_wroom-1u_datasheet_en.pdf) · [乐鑫启动与 USB 设计说明](https://docs.espressif.com/projects/esp-hardware-design-guidelines/en/latest/esp32s3/schematic-checklist.html)

| U1 焊盘 | GPIO | A2 用途 | 相对 A1 |
|---:|---:|---|---|
| 1 | — | 系统地 | 保留 |
| 2 | — | 3V3_CTRL | 保留 |
| 3 | — | CHIP_EN、J7 复位 | 保留 |
| 4 | 4 | CAM_D4 入，FPC 18／Y6 | 释放原 MIC_WS |
| 5 | 5 | PDM_CLK 出 | 麦克风时钟 |
| 6 | 6 | PDM_DATA 入 | 麦克风数据 |
| 7 | 7 | I2S_TX_DATA 出 | 保留功放 |
| 8 | 15 | I2S_TX_BCLK 出 | 保留功放 |
| 9 | 16 | I2S_TX_WS 出 | 保留功放 |
| 10 | 17 | J14 既有支路使能，出 | 保留默认关闭 |
| 11 | 18 | J13 既有支路使能，出 | 保留默认关闭 |
| 12 | 8 | L298P ENA，直连硬件 PWM 出 | 保留 |
| 13 | 19 | USB D− | 保留 J1 |
| 14 | 20 | USB D+ | 保留 J1 |
| 15 | 3 | 绑带，留空 | 保留 |
| 16 | 46 | 绑带，留空 | 保留 |
| 17 | 9 | CAM_D0 入，FPC 19／Y2 | A_IN1 移至扩展器 |
| 18 | 10 | CAM_D1 入，FPC 21／Y3 | A_IN2 移至扩展器 |
| 19 | 11 | L298P ENB，直连硬件 PWM 出 | 保留 |
| 20 | 12 | CAM_D2 入，FPC 22／Y4 | B_IN1 移至扩展器 |
| 21 | 13 | CAM_D3 入，FPC 20／Y5 | B_IN2 移至扩展器 |
| 22 | 14 | J15 AUX_EN 出 | 保留默认关闭 |
| 23 | 21 | CAM_D5 入，FPC 16／Y7 | A1 空网 |
| 24 | 47 | CAM_PCLK 入，FPC 17 | 说话键移至扩展器 |
| 25 | 48 | CAM_VSYNC 入，FPC 7 | A1 空网，固件移除旧板 LED 驱动 |
| 26 | 45 | ARM_CLK 出 | 保留 A1 锁存及复位下拉 |
| 27 | 0 | BOOT／本地停止入 | 保留 J6 |
| 28 | 35 | Octal PSRAM | 模组内部占用 |
| 29 | 36 | Octal PSRAM | 模组内部占用 |
| 30 | 37 | Octal PSRAM | 模组内部占用 |
| 31 | 38 | ACT_ARMED 入 | 保留 SW2 状态读回 |
| 32 | 39 | CAM_D6 入，FPC 14／Y8 | 音量减移至扩展器 |
| 33 | 40 | CAM_D7 入，FPC 12／Y9 | 音量加移至扩展器 |
| 34 | 41 | I²C SDA 双向 | OLED、扩展器、隔离后的 SCCB 共用 |
| 35 | 42 | I²C SCL 开漏 | 同上 |
| 36 | 44 | CAM_HREF 入，FPC 9／HSYNC | 复用默认 UART0 RX |
| 37 | 43 | CAM_XCLK 出，FPC 13／MCLK | 复用默认 UART0 TX，复位期间隔离摄像头 |
| 38 | 2 | US_ECHO 入 | 保留 J3，按实际模块确认 3.3 V 电平 |
| 39 | 1 | US_TRIG 出 | 保留 J3 |
| 40 | — | 系统地 | 保留 |
| 41 | — | 裸焊盘接地 | 保留 |

12 根相机时序线全部直达 S3 的 GPIO 矩阵，中间只做电平转换。量产下载和日志走 J1 原生 USB Serial/JTAG，板外独立 5 V 供电；禁用应用 UART0 控制台和 GPIO39–42 的外部引脚 JTAG，保留 BOOT/RESET 下载恢复。上电及软件复位均须检查 ROM 的 GPIO43 输出。移除旧板 GPIO 按键初始化，避免把视频引脚重新配成按键或 LED。当前行走与 A1 同为开环；电机带编码器，本表未安排四路 AB 相采集。

## 扩展器和停止路径

TCA9539PWR 接常供 3.3 V，A1/A0 地址脚接地时 7 位地址为 0x74。P00–P03 依次接 L298P 的 A_IN1、A_IN2、B_IN1、B_IN2，四路保留下拉。P04、P05、P06 为说话、音量减、音量加三个上拉输入，以轮询方式读取，INT 可留测试点。P07 留空。P10、P11 独立控制摄像头 1.8 V、2.8 V LDO 的 EN，外部下拉。P12 为高速转换器 OE_N，外部上拉关断；P13、P14 分别控制 CAM_RST_N、CAM_PWDN；P15–P17 预留。全表有 12 根摄像时序、19 根其余已用主控信号、2 根保留绑带和 3 根内部 PSRAM 引脚。摄像头侧 RST_N 下拉、PWDN 上拉至 DOVDD。扩展器 RESET 要随板级复位可靠复位，区分整板上电和仅 S3 软件重启。[TI TCA9539](https://www.ti.com/product/TCA9539)

两路 EN/PWM、本地停止和 SW2 独立硬件切断保持直接控制。每次换向先将相应 EN 拉低，等待驱动关断后用一次端口写入改变方向，核对输出寄存器及故障状态后才允许恢复 PWM。超时、NACK、总线持续拉低、控制任务失联或方向不确定时由独立任务关两路 EN；停止路径不等待 I²C 锁。扩展器上电时先在输入态预写安全输出锁存值，再切换方向寄存器。启动和快速重合先清输出并重读锁存状态，再接受新命令。驱动中保留事务互斥和命令代际检查，摄像头初始化或 OLED 刷屏分段，防止迟到的写操作恢复已停止的履带。总线故障允许预览和行走同时中断，恢复须收到新命令。

## 摄像头电气与排线

下一版选用 Seeed 114993115。以下针号、电源、OLED 地址与装配均按该自动对焦模组定义。[模组承认书及采购信息](../../components/seeed-114993115/README.md)

- **电源。** 两颗带 EN 的 TLV75518PDBVR、TLV75528PDBVR 由 3V3_CTRL 分别生成 1.8 V 和 2.8 V。FPC 11 接 1.8 V，4、24 接 2.8 V 模拟及 AF 分支，各就近去耦；2、15、23 接地。10 是内供核心电压，外围去耦依模组参考电路确认；1 STROBE 留空。独立 EN 用于满足供应商上／下电顺序，电源稳定后再释放 PWDN 和 RST。预算包含滤波、控制上下拉及复位隔离小料。500 mA 为各 LDO 的器件额定，电池输出能力、既有 3.3 V 电源余量和热裕量均须在音频、Wi-Fi、AF 和运动并发下测定。[模组 24 针原图](../../components/seeed-114993115/Seeed-OV5640-MJY5OAF-F3M-V1.pdf) · [TI TLV755P](https://www.ti.com/product/TLV755P)
- **并口。** 两颗 SN74AXC8T245PWR 均以 A 侧接常供 3.3 V、B 侧接摄像头 1.8 V。第一颗八路 B→A 传 D0–D7；第二颗一个四路组 B→A 传 PCLK、VSYNC、HREF，另一组 A→B 传 XCLK、RST_N、PWDN，未用输入处理依数据手册。这样时钟及数据均有确定方向。OE_N 默认高，两颗共用，控制逻辑参考 A 侧。布局按两个芯片间的传播偏差核算 PCLK 建立／保持时间。复位、摄像头断电和失电过渡期需验证无反灌。[TI SN74AXC8T245](https://www.ti.com/product/SN74AXC8T245)
- **控制总线。** TCA9406DCUR 的 A 侧接 1.8 V，B 侧接 3.3 V。FPC 3／5 分别为 SDA／SCL。OE 随相机低压域，检查与内部 10 kΩ 上拉及 OLED 板上上拉的并联值和掉电漏电。OLED 以实件的 0x3C 或 0x3D 确认，OV5640 预期 7 位地址为 0x3C，**OLED 必须选可配 0x3D 的版本并固定为 0x3D**。若模组实测地址不同则据实更新。预算按可选址 OLED 计。驱动共享已有 I²C 控制器、统一仲裁；关闭预览只释放相机资源。相机 RST／PWDN 由板级扩展器驱动，应用绕开相机库的原生 GPIO 自动复位流程。[TI TCA9406](https://www.ti.com/product/TCA9406) · [乐鑫 OV5640 驱动](https://github.com/espressif/esp32-camera/blob/master/driver/include/sensor.h)
- **连接器。** J17 采用 Hirose FH12-24S-0.5SVA(54)，采购号 C3169218。板顶坐标 (17, 27) mm，封装旋转 180°。24 路 0.5 mm 触点分到两排交错焊脚，同排间距 1 mm；四个固定焊盘独立。原装 FPC 两处 R4 转弯后露铜面朝前（−Y），锁扣朝后（+Y）。在顶视图上，模组 1 脚位于 +X，Hirose 1 脚位于 −X。模组 1 → J17-24（空），模组 24 → J17-1（AF 2.8 V）。首板断电按下表测通断与对地阻抗，再接摄像头。[Hirose 工程图、三维模型及操作指南](https://www.hirose.com/en/product/p/CL0586-0814-9-54) · [Seeed 原图第 3 页](../../components/seeed-114993115/Seeed-OV5640-MJY5OAF-F3M-V1.pdf)

| 模组 FPC | J17 | 网络 | 模组 FPC | J17 | 网络 |
|---:|---:|---|---:|---:|---|
| 1 | 24 | 空（STROBE） | 13 | 12 | XCLK_FPC |
| 2 | 23 | GND_SYS | 14 | 11 | D6_1V8 |
| 3 | 22 | SDA_1V8 | 15 | 10 | GND_SYS |
| 4 | 21 | CAM_2V8 | 16 | 9 | D5_1V8 |
| 5 | 20 | SCL_1V8 | 17 | 8 | PCLK_FPC |
| 6 | 19 | RST_1V8 | 18 | 7 | D4_1V8 |
| 7 | 18 | VSYNC_1V8 | 19 | 6 | D0_1V8 |
| 8 | 17 | PWDN_1V8 | 20 | 5 | D3_1V8 |
| 9 | 16 | HREF_1V8 | 21 | 4 | D1_1V8 |
| 10 | 15 | CAM_CORE_CAP | 22 | 3 | D2_1V8 |
| 11 | 14 | CAM_1V8 | 23 | 2 | GND_SYS |
| 12 | 13 | D7_1V8 | 24 | 1 | CAM_2V8 |

### A2 制板与装配

J17 焊盘及钢网按偶数位垂直型核对。24 个信号焊盘为 0.60 × 1.60 mm，钢网开口 0.50 × 1.50 mm；四个固定焊盘为 0.80 × 1.90 mm，开口 0.65 × 1.75 mm。按 Hirose 系列图纸 p.10 与贴片厂复核钢网厚度、锡量及连接器平面度。A2 含焊盘内过孔，交付板厂时指定填树脂、盖铜、整平后再做表面处理，摄像头座旁的贴装焊盘按成品平面度验收。FPC 厂商只给出了带补强总厚，Hirose 对单独补强层另列 0.188 mm 下限，需向模组供应商确认叠层。[Hirose 原厂资料](https://www.hirose.com/en/product/p/CL0586-0814-9-54) · [A2 工程校验](../verification-A2.json)

## 并发与首板判定

A1 的 ICS-43434 已进入退市阶段。A2 采用 Infineon IM69D128SV01XTMA1 用两个 GPIO，经 I2S0 的 PDM→PCM 硬件接收；16 kHz PCM 选 128 倍抽取，PDM CLK 为 2.048 MHz，在麦克风 1.2–3.3 MHz 正常时钟范围内。MAX98357A 继续用 I2S1 标准 TX，独立 24 kHz 播放。新麦克风为底部声口，要按新封装复核 PCB 声孔和密封，并更换采集驱动，验证自播回声及运动噪声。摄像头走独立 LCD_CAM 和 DMA，使用 OV5640 JPEG 直出及 PSRAM 帧缓冲；驱动、音频 DMA 和应用共用内部内存与 Wi-Fi 带宽。[TDK 生命周期](https://www.invensense.tdk.com/en-us/products/microphone/ics-43434) · [Infineon 麦克风与量产状态](https://www.infineon.com/part/IM69D128S) · [ESP-IDF 5.5.1 音频时钟](https://docs.espressif.com/projects/esp-idf/en/v5.5.1/esp32s3/api-reference/peripherals/i2s.html) · [乐鑫相机驱动](https://github.com/espressif/esp32-camera)

建议以同一台工程板测试 VGA JPEG、手机端实际 ≥15 fps 作为首轮流畅度目标，同时运行 16 kHz 拾音、24 kHz 播放、双履带和超声波。记录帧间隔尾延迟、音频欠载、测距超时、停止延迟、最低电压和闭壳温升。反复开关预览、模拟 SCCB 被拉低及板级／软件复位，验证停机并保持关闭。引脚分配只证明资源可同时分配；续航、帧率、抗干扰与整机供电仍待该版样板验证。现有履带 PWM 使用 LEDC timer 2、通道 2/3；相机时钟不得重配这些资源。按两台电机铭牌额定点 12 V × 0.55 A × 2，仅电机端已需约 13.2 W。作预算示例，若升压效率为 85%，仅这一项折合 5 V 输入约 3.1 A，尚未计 H 桥压降和主控、音频及摄像头。应量测 J8 峰值和两条摄像头电源轨，闭壳验证热表现。[履带 PWM 分配](../../../firmware/esp32-audio/action_outputs.h) · [电机资料](../../components/37R-520/README.md)
