# MOS 单次开关台架工程

版本 `0.1.1-mos-bench`，ESP-IDF **v5.5.1**，ESP32-S3 N16R8。用于本地串口控制 P01 MOS 成品开关模块的分阶段测试；不接网络，不改变正式固件的动作认证门槛。电源及接线核对见 [MOS 台架记录](../../docs/validation/bench.md)。

核对日期：2026-10-27。本工程保留独立 COREBOARD 的 `0.1.1-mos-bench`／GPIO4 配置；下方是该台架操作与历史记录，不是现用面包板固件。当前 ct21 水枪为 GPIO18、泡泡为 GPIO17、共用点火 MOS 低压控制为 GPIO21；接线见[总表](../../docs/wiring.md)。独立台架已有 5 秒喷水和 BOOT 提前停止的用户观察，后续本板语音喷水及并发另见[喷水记录](../../docs/validation/bench.md)。

当前辰克 5 V 电池包取代旧电源；两枪各有 P12 降压板，路径为 5 V→各自 MOS→枪内 P12→3.7 V。旧台架供电状态不描述当前实物，旧电源结果不转移；电流、定量温升、上电默认关闭、独立切断及完整故障矩阵继续待验。

## 信号与操作

- 临时 **GPIO4** 输出，应用启动后默认低；动作时持续高电平 5000 ms，不使用 PWM。只在确认高电平触发输入后连接 MOS 的 `TRIG/PWM`，ESP32 GND 接信号 GND；用户实物照片已确认 VIN+／VIN−／VOUT+／VOUT−，具体接线及分阶段测量见台架记录；实际为 5 V→MOS→降压板 3.7 V→水枪，负载保护及降压启动／关断仍待验证。
- 板载 **BOOT / GPIO0** 为临时停止输入，按下停，松开稳定 30 ms 后可重新人工使能。BOOT 是下载绑带，不按住它上电／复位。
- `a`：使能 3 秒；看到 `MOS ARMED (send g within 3s) outputs=OFF` 后，单独按 `g` 输出一次高电平；结束收到 `MOS DISARMED outputs=OFF`。
- `s` 或 BOOT 提前停止，结束后至少冷却 1 秒；每次动作需要重新 a，不循环、不排队、不自动重试。未知键、同一接收批次的多个命令、动作期间非换行输入撤销输出；旧电机命令 f／r 不会使能。
- 不粘贴 `ag`，也不使用宏。UART 异常／溢出清队列并关闭。UART 不能可靠检测电脑断开，关串口不是停止命令。

**先断开电机驱动板与 ESP32 的所有连接，GPIO4 不与电机控制共用。**2026-10-25 已改选何健弓 L298N；下文 DF-MD 接线／烧录反馈仅为旧板历史。首次烧录／无负载验证时 ESP32 引脚全部空接，只接 COM USB；用户于 2026-10-24 已确认此状态。后续连接负载时主控先启动、负载电源最后接通；先断负载电源，再拔 USB、复位、烧录或重新打开串口。3.7 V 是效果负载电源，不接 ESP32 3V3 或 GPIO。

内部下拉仅在应用配置后生效，不保证 MCU 失电、启动前、复位或烧录期间关闭。BOOT／串口停止不替代独立切断供能；没有电流、温度、欠压采样。5 秒期限只在正常调度和 GPIO 调用下成立，任务看门狗也不证明硬件关闭时限。驱动 API 失败只会尝试关断并锁住，实际电平需要测量。

## 编译与测试

仓库根目录执行：

```sh
mkdir -p build/mos-bench-host
cc -std=c11 -Wall -Wextra -Werror -fsanitize=address,undefined -g \
  -I firmware/esp32-mos-bench/main \
  firmware/esp32-mos-bench/main/bench_policy.c \
  firmware/esp32-mos-bench/tests/policy_test.c \
  -o build/mos-bench-host/policy_test
build/mos-bench-host/policy_test

export IDF_PYTHON_ENV_PATH=/Users/miclle/.espressif/python_env/idf5.5_py3.14_env
. /Users/miclle/esp/esp-idf/export.sh
idf.py -C firmware/esp32-mos-bench -B "$PWD/build/firmware-mos-bench" build
```

`main/bench_policy.c` 独立管理单次使能、期限、停止、冷却和时钟故障；沿用电机台架的策略结构但移除方向和 PWM，不修改原工程。`main/mos_bench.c` 以 5 ms 周期先处理 BOOT／期限，再处理有界 UART 输入，动作期间不打印日志。

2026-10-24 主机 ASan／UBSan 测试通过：无使能拒绝、3 秒使能到期、1 秒输出期限、冷却、重复／批量输入、旧电机命令拒绝、停止及松开、时钟回退／溢出与重建状态。ESP-IDF v5.5.1 交叉编译通过，应用 237072 bytes；构建日志在本机忽略目录 `build/mos-bench-host/idf-build.log`。这不是 MOS 实物或水枪启停验收。

## 烧录与串口

沿用现有分区，仅更新应用的命令如下；`<COM_PORT>` 替换为实际 COM 串口，先确认引脚空接或负载电源断开。分区／bootloader 不一致时不能直接套用应用偏移。

```sh
python -m esptool --chip esp32s3 --port <COM_PORT> --baud 115200 --no-stub \
  write_flash --flash_mode dio --flash_size 16MB --flash_freq 40m \
  0x10000 build/firmware-mos-bench/cybertrack_mos_bench.bin
```

串口使用 COM USB、115200 baud。打开串口可能复位，DTR／RTS 预设也不证明无瞬态；带载测试必须复用已建立的连接，连接丢失后先断负载供电。本次板上运行结果见下文。


## 2026-10-24 烧录与无负载命令检查

用户明确选择 3.7 V 水枪为下一阶段负载，并确认 ESP32 已与 DF-MD 断开、引脚无连接线。检查本机串口没有现有占用；目标仍为原 COM USB 桥。MOS 工程与原电机工程生成的分区表逐字节一致，使用 esptool 4.12.dev2、115200 baud、no-stub 仅更新 0x10000 应用，保留 bootloader／分区表及其余 Flash，不改 eFuse。

应用 237072 bytes，工具按块填充写入 237568 bytes，哈希校验通过。SHA-256：`41fb8006b14d9c44985af27e424d895b1a79e81bc7911d1c3a6a79b6830a89de`。日志：本机 `build/mos-bench-private/flash-0.1.0.log`。

在引脚空接下建立 Homebrew GNU Screen 持久会话 `cybertrack-mos`，读到项目 `cybertrack_mos_bench`、`0.1.0-mos-bench`、ESP-IDF v5.5.1 及：

```text
MOS READY 0.1.0 GPIO4=TRIGGER active=HIGH pulse=1000ms
```

16:05:03（Asia/Shanghai）起复用同一连接依次发送 s → 收到 DISARMED；a → 收到 ARMED；仅一次 g → 收到 DISARMED；最后 s → 再收到 `MOS DISARMED outputs=OFF`。电脑观察 g 至关闭回执约 1033.4 ms，包含串口和日志读取延迟，不能作为电气脉宽。期间未重连、复位或重试。

这是**未连接 MOS／负载时的板上命令流程检查**，未测量 GPIO 电平，没有水枪动作，也未验证实体 BOOT 停止。原始记录在本机 `build/mos-bench-private/unloaded-check-0.1.0.json`、`serial-0.1.0.log`。最终软件报告关闭，串口保持连接；实物输出、MOS 端子／保护与带载试验仍待补。

可在终端共享查看现有连接：

```sh
/opt/homebrew/bin/screen -x cybertrack-mos
```

Ctrl+A 后按 D 脱离并保留连接；不要再启动另一串口程序。接入负载后若连接丢失，先断负载供电再重连。


2026-10-24 16:16:29（Asia/Shanghai），用户确认 MOS 控制两线已接、功率输入未供电、水枪断开、静态 TRIG/PWM=0 V。复用持久串口执行一次 1 秒 g 命令，收到到期关闭及追加 s 的关闭回执；用户随后报告电压升至约 3 点几伏，随后确认结束回到 0 V；不据近似读数认定 MOS 功率开关通过。完整记录见[MOS 台架测试](../../docs/validation/bench.md)。


2026-10-24 16:21:48（Asia/Shanghai），用户报告 MOS 已接通 5 V，要求省略电阻直接测试；沿用此前水枪未连接状态，复用串口执行一次 1 秒命令并取得到期与 s 关闭回执。指示灯及功率输出结果待观察；不作为水枪或 3.7 V 适配通过。详见[MOS 台架记录](../../docs/validation/bench.md)。


## 0.1.1：按用户要求延长至 5 秒

单次 GPIO 高电平期限从 1000 ms 改为 5000 ms，保留使能、冷却和停止机制。ASan／UBSan 主机测试通过，增加原 1 秒边界仍活动、5 秒边界关闭、2.5 秒附近提前停止、冷却和长时限溢出检查；ESP-IDF v5.5.1 编译通过，镜像 237088 bytes。用户已确认 MOS 5 V 断开、USB 保留；烧录／启动及实际 5 秒动作结果另记。


0.1.1 更新完成：用户确认 MOS 的 5 V 断开后更新应用。首次工具因原 miniterm 在 Screen 退出后仍占用串口而未能打开设备，没有写入；识别并结束本任务遗留的 miniterm，确认端口释放后重试成功。仅写 0x10000 应用，237088 bytes，按块填充 237568 bytes，哈希校验通过；保留 bootloader／分区及其他 Flash。镜像 SHA-256：`9c51cf1857f0b0d1ba581005cf37356ff28d5ccdea3d3b4f57e7e2a89acf9b96`。日志为本机 `build/mos-bench-private/flash-0.1.1-retry.log`；首次端口占用记录另存于 `flash-0.1.1.log`。

在功率断电下重新建立 `cybertrack-mos` 持久串口，确认 `MOS READY 0.1.1 ... pulse=5000ms`；只发送 s 并取得 `MOS DISARMED outputs=OFF`，启动记录在本机 `ready-0.1.1.txt`、`serial-0.1.1.log`。用户随后确认 5 V 已接回、水枪静止、供水就绪并授权试喷。

16:27:40（Asia/Shanghai）起复用连接，s→DISARMED、a→ARMED，仅发送一次 g，收到到期 DISARMED，再发 s 获得关闭回执。配置为持续高电平 5000 ms；电脑观察 g 至关闭回执约 5049.5 ms，含通信／读取开销，不是实测脉宽或喷水时长。未重连、复位、循环或自动重试。本机原始记录：`water-gun-5s-20261024-162740.json`。用户随后确认“水枪正常喷水，5 秒结束后也自动停止了”。据用户现场观察与本次串口记录，单次喷水及到期自动停止功能检查通过；实际喷水时长／停止延迟、带载电流／电压、温升及该次尚未验证的提前停止与复位／失电边界仍待验证（后续 BOOT 子项见下节），不构成完整带载或安全验收。


## 2026-10-24 BOOT 带载提前停止结果

沿用 0.1.1 和既有串口连接，约 16:49:13（Asia/Shanghai）发送一次 g；在 5 秒期限前收到 `MOS DISARMED outputs=OFF BOOT held`，随后 s 再确认关闭。用户确认喷水过程中按下 BOOT 就立即停止，松开后没有恢复。本次 BOOT 带载提前停止／松开不自动恢复功能检查通过；未测精确停止延迟，不代表复位／失电或独立切断通过。s 带载提前停止与重复性仍待验证。详细时间、原始记录位置及证据边界见[MOS 台架记录](https://github.com/miclle/cybertrack/blob/c25b0af729bd216b69779db2bba75f32f9475cdd/docs/mos-bench.md#2026-10-24-boot-带载提前停止)。
