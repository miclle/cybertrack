# 到货板核对、无负载启动与 PSRAM 验证

日期：2026-10-23。来源为用户提供的[正面照片](ESP32-S3-front.jpg)、[背面照片](ESP32-S3-back.jpg)、用户实测尺寸，以及当前电脑 USB 枚举和 ROM 查询结果。机器可读记录及照片哈希见 [physical-verification.json](physical-verification.json)。原始照片未改写；未提交设备 MAC、USB 序列号或原有程序数据；新增无负载工程的启动日志经过检查后保存。

## 外形与照片

| 项目 | 结果 | 证据边界 |
|---|---|---|
| 含天线总长 × 板宽 × 焊针后总高度 | **63.6 × 28.2 × 13.2 mm** | 用户实测；量具和误差未提供。后续整板包络采用此值，不能据此补定 PCB 厚度、孔径和线缆空间 |
| 与供应商图纸差值 | 总长 +0.21 mm，板宽 +0.26 mm | 相对图示 63.39 × 27.94 mm 的算术差；不是制造公差判定 |
| 模组屏蔽罩 | `S3 N16R8`，另有 WIFI+BT 等标记 | 没有可见的完整乐鑫 WROOM-1 订货型号，不能据此认证为原厂 WROOM 模组 |
| 天线 | 可见 PCB 天线和外接同轴天线座 | 当前射频通路选择、外接天线是否需要及 RF 性能未验证 |
| PCB | 背面 `ESP32-S3`，接口背标 `COM`、`USB` | 未看到明确 PCB 修订版；不能确认 V1.4 |
| 排针与按键 | 可见丝印顺序与图纸相符；有 RST／BOOT、RGB、双 Type-C | 只做可见标记核对，没有通断／电平测试 |
| 稳压器 | 可辨识 `1117 3.3V` | 与原理图 U3 的 CJ6107A33GW 标注不一致，须按实物确认器件与电源额定能力 |
| 串口桥 | 小字不足以可靠认定完整型号；COM 枚举成功 | 不仅凭原理图认定为 CH343P，也不凭 VID/PID 认定精确芯片修订版 |

主控测量与型号证据已更新到 [board-data.json](board-data.json)。整机当前仍是主控／驱动／电源共用的电子分配区；本次不覆盖正在修改的整机 CAD，不把整板包络当成已完成安装验证。

## 两个 USB 接口

1. 初始接在用户所说的 USB 口：macOS IORegistry 识别 `Espressif Device`／`Espressif Systems`，VID:PID 为 `303a:4001`，出现 CDC 串口。被动监听 3 秒接收 18 字节，无可识别的固件版本标记；没有发送串口数据或保留原文。不能由设备描述符确定固件版本、内存大小或完整芯片身份。
2. 用户换到 COM 后：第一次未看到新 USB 设备或串口。该次失败保留，不归因于驱动。
3. 用户翻转板端 Type-C 插头 180° 并重新插紧，报告电源灯亮：识别 `USB Single Serial`，VID:PID 为 `1a86:55d3`，CDC 接口和串口均出现。随后通过该口完成 ROM 查询。

两个接口已分别有枚举证据。COM 初次失败与重插后的成功不能单独证明连接器方向性故障；接触、插入到位或方向问题尚未通过重复 A/B 测试区分。当前状态是已连接方向可用，不是两个插入方向均通过。`system_profiler SPUSBDataType` 本次返回空列表，实际枚举证据使用 `ioreg` 的 IOUSBHostDevice／IOUSBHostInterface 与串口节点。

## 芯片与存储查询

工具为官方 esptool 5.6.0，安装在临时环境中。使用下列命令；`<COM_PORT>` 代表当次实际枚举端口，端口名不固定：

```sh
esptool --chip esp32s3 --port <COM_PORT> --baud 115200 --no-stub --before default-reset --after hard-reset flash-id
```

| 查询项 | 返回结果 |
|---|---|
| 芯片 | ESP32-S3（QFN56），revision v0.2 |
| 特性 | Wi-Fi、BT 5（LE）、Dual Core + LP Core、240 MHz |
| 封装内 PSRAM | 8 MB，AP_3v3 |
| 晶振 | 40 MHz |
| Flash ID | Manufacturer `68`，Device `4018`（工具原始显示） |
| Flash 容量 | 16 MB |
| eFuse 中 Flash 配置 | quad（4 data lines），3.3 V |
| 退出 | 返回码 0，工具报告通过 RTS 硬复位 |

首次 ROM 查询结果与 N16R8 标称一致。PSRAM 容量为芯片特征识别，不是 PSRAM 初始化或读写测试；Flash 容量为 ID 检测，不是全片读写测试。首次 ROM 查询未读取 Flash 内容、未上传 RAM stub、未烧录或擦除 Flash，也未改写 eFuse；后续经用户授权的烧录另见下节。工具执行了进入下载模式和结束复位；未验证原有应用的完整运行状态。

命令行为依据：[esptool 基本命令](https://docs.espressif.com/projects/esptool/en/latest/esp32s3/esptool/basic-commands.html)、[reset 与 no-stub 选项](https://docs.espressif.com/projects/esptool/en/latest/esp32s3/esptool/advanced-options.html)。

## CyberTrack 无负载固件与 PSRAM（实物通过）

用户授权仅接 USB、不接电机，完成启动与 PSRAM 初始化／读写验证。新增[最小检查工程](../../../firmware/esp32/README.md)，复用现有 `control.c`；没有执行器 GPIO/PWM、网络或音频驱动，也没有调用本地使能。完整运行层尚未移植。

| 项目 | 本次结果 |
|---|---|
| 构建环境 | ESP-IDF v5.5.1，目标 esp32s3，CPU 160 MHz；版本及源码哈希见机器记录 |
| Flash／PSRAM 配置 | 16 MB Flash，DIO 40 MHz；8 MB Octal PSRAM，40 MHz；SDK 内置启动内存检查开启 |
| 烧录 | COM、115200 baud、esptool 5.6.0、no-stub；bootloader、分区表与应用三个镜像的写入哈希均通过 |
| 应用镜像 | 217776 字节，版本 `0.1.0-board-check`，放入 1 MiB factory 分区 |
| PSRAM 初始化 | 三轮均识别 8388608 字节，SDK 日志 `SPI SRAM memory test OK` |
| 应用内存读写 | 三轮均显式分配外部 RAM 6291456 字节（6 MiB）；全零、全一、交替位、地址相关模式及反码共六轮均通过；释放后堆完整性通过 |
| 控制核心启动 | 三轮均从 BOOT 进入 DISARMED，所有能力上限为零，逻辑输出为零 |
| 稳定观察 | 每次内存自检完成后观察 600 次约 100 ms tick，约 60 秒；每轮日志覆盖到启动后 72630 ms，未出现 panic、意外重启或失败标记 |
| 复位方式 | COM 的 RTS 触发 EN；芯片报告 POWERON／reset_reason=1。没有拔插断电，因此不计为真实断电重启试验 |

配套验证：ESP-IDF 构建通过；最新主机回归 13/13 通过；源文件、日志和部件资产哈希及文档链接检查通过。

三次日志：[第 1 轮](validation-2026-10-23/boot-1.log)、[第 2 轮](validation-2026-10-23/boot-2.log)、[第 3 轮](validation-2026-10-23/boot-3.log)。[机器记录](validation-2026-10-23/result.json)包含配置、源文件／镜像／日志哈希和未测范围。原始 Flash 备份仅在本机忽略目录 `build/board-validation-private/pre-validation-first-1MiB.bin`，大小 1048576 字节，覆盖全部改写扇区；不提交其内容。仅改写 bootloader、分区表和应用所需扇区，未全片擦除、未改写 eFuse。该阶段运行 0.1.0 检查固件；后续安装版本见下方 BOOT 停止记录。

首次尝试用 RAM stub、460800 baud 备份整片 Flash，在约 32 KiB 时出现 `Invalid head of packet (0x92)`，未进入写入。随后 ROM 115200 整片读取因耗时主动终止，改为前 1 MiB 备份成功；后续低速 ROM 烧录与哈希验证通过。该高速串口问题未定位，不把它归因于 PSRAM，也不宣称高波特率可靠。

本次 6 MiB 模式测试覆盖大于数据缓存的区域，先完整写入再读回；它不是全部 8 MiB 的应用级逐字节测试或长时老化。零逻辑输出也不代表实体引脚电平、负载关断或物理停止已通过。F2b 仅关闭无负载启动／内存子项，完整 F2b、供电／散热与整机验收仍开放。

## 2026-10-24：BOOT 键本地停止补充

用户授权后已安装 0.2.0-boot-stop-check；两次实体按下均锁定停止，松开不恢复，人工 RST 后回到未使能，结果见[BOOT 停止验证](boot-stop-verification.md)。这只验证无负载软件停止输入，不代表执行器电源切断。

## 后续剩余项

- 仍需匹配实物板级版本、串口桥／稳压器完整型号、GPIO3 与 IN-OUT 焊装及通断；射频通路也需核对。
- PSRAM 初始化及本次 6 MiB 测试、无负载启动与逻辑默认关闭已通过；全容量／长时内存测试、专用停止输入／供能切断、执行器引脚电平、调度时限与看门狗仍未验收。F2b 未完成。
- 安装孔／固定方式、USB 插头与线缆空间、天线净空、供电与散热尚未验收。
- COM 插头方向／接触问题保留待复查；在不接负载时分别核对两方向。
