# CyberTrack ESP32-S3 固件

A4 分域供电主板使用 `--mainboard-a4` 构建，A1 使用 `--mainboard-a1` 构建，负责唤醒、音频、OLED 和本地控制。原面包板构建保留用于旧设备回归。v2 使用三路输出，分别驱动履带、喷水与泡泡。网页与灵矽语音共享设备端的互斥、计时和停止规则。[控制接口](../CAPABILITIES.md) · [网页控制](../../docs/lan-control.md) · [当前版本与部署](../../docs/current-status.md)

## 来源与配置证据

- 上游：[`78/xiaozhi-esp32`，`e8ed16bb42ed9b199cbc9376011653e5037de8d8`](https://github.com/78/xiaozhi-esp32/tree/e8ed16bb42ed9b199cbc9376011653e5037de8d8)。
- 本机原构建 ELF SHA-256：`f7e8809ce981ee4182fb6c3eb15b20aa785111c7f1e4b1e2f059e4debc813b45`，与面包板完整 Flash 中的应用描述一致；原 `xiaozhi.bin` 的 2,531,056 bytes 也与备份 `0x20000` 起的数据逐字节一致。
- 原 `sdkconfig` 固定在 `sdkconfig.baseline`，其有效配置与 ct2 构建逐项比较无差异；ct3 至 ct6 仅在导出源码配置中将 tick 改为 1000 Hz、任务看门狗改为 2 秒及 panic；原依赖版本在 `dependencies.lock` 中。使用本机原组件缓存的独立副本，避免下架组件引起依赖升级。
- ESP-IDF v5.5.1；ESP32-S3 N16R8；SSD1306 128×32；独立输入／输出 I2S；输入 16 kHz、输出 24 kHz；原唤醒模型保留。

可选 Wi-Fi 配置和本地凭据的处理见[网络配置](../../docs/wifi-configuration.md)。板卡和实际线束需逐线核对。[接线总表](../../docs/wiring.md)

## GPIO 配置

A1 的引脚和电路以 [A1 接口表](../../hardware/pcb/README.md#外接接口) 为准。下表用于旧面包板固件回归。音频引脚来自原镜像对应的板级源码与配置，执行器引脚来自当前输出驱动；桥身份和完整接线未独立逐线测量，不能以软件配置代替电气验收。

| 用途 | GPIO |
|---|---|
| 麦克风 WS／SCK／DIN | 4／5／6 |
| 扬声器 DOUT／BCLK／LRCK | 7／15／16 |
| OLED SDA／SCL | 41／42 |
| 板载 LED | 48 |
| BOOT：本地停止 | 0 |
| 水枪 MOS TRIG/PWM（ct3 起） | 18 |
| 泡泡 MOS（已部署；有出泡影像，逐线核对及完整电气验收待完成） | 17 |
| 超声波 TRIG／ECHO | 1／2 |
| L298N A：ENA／IN1／IN2（ct21 映射右轨） | 8／9／10 |
| L298N B：ENB／IN3／IN4（ct21 映射左轨） | 11／12／13 |
| 按住说话按键 | 47 |
| 音量增加／减少 | 40／39 |

旧面包板的 GPIO4 由麦克风占用。BOOT 按下即停止，松开后需要新指令。GPIO21 已退出执行器配置。

## A4 履带与故障恢复

| 用途 | A4 连接与行为 |
|---|---|
| 履带 A／B | GPIO8 → U28 → U6 → J11，GPIO11 → U28 → U24 → J12。软件按 A 为右轨、B 为左轨映射，首板架空核对左右归属及正转符号。 |
| 方向 | U12 TCA9539 地址 0x74，P00／P01 为 A 的正／反向，P02／P03 为 B 的正／反向。换向先停两路 PWM，以一次端口写入设置四位，核对配置、输出锁存及实际引脚，再复读 GPIO38 和 BOOT。 |
| 停止与许可 | GPIO0 为本地停止，GPIO45 为 U10／U27 的公共时钟，GPIO38 回读 U27.Q。U6 或 U24 的 nFAULT、12 V 母线跌落、SW2 断开均可异步撤销双侧 PWM。硬件只提供汇总反馈。 |
| 其他直接输出 | GPIO18 喷水、GPIO17 泡泡、GPIO14 扩展口。联锁失效时清除动作和待执行序列，扩展口保持低电平。 |
| 人机接口 | GPIO41／42 共用 I²C，OLED 地址 0x3D。U12 P04／P05／P06 对应说话／音量减／音量加。PDM 输入用 GPIO5／6，16 kHz、128 倍抽取；扬声器用 GPIO7／15／16，测距用 GPIO1／2。应用控制台走原生 USB。摄像头控制端依靠板上安全偏置保持关闭，编码器和 IMU 闭环另行集成。 |

冷启动先清输出，GPIO45 的第一枚上升沿唤醒执行器电源。后续脉冲间隔至少 100 ms，硬件仅在电源和两桥就绪时锁存行走许可。固件连续观察 GPIO38 高电平至少 5 ms 后才接纳动作。行走中丢失许可即撤销网页租约、语音授权和排队动作。故障释放后重新确认方向全零并恢复许可，履带等待新指令。状态回执中的 `drive_armed` 是经过上述确认的许可，`actuator_disarmed` 可由 SW2、母线或任一驱动故障引起。

独立任务每轮读回 U12 后等待 20 ms。NACK、方向不符或有效回读超过 100 ms 未更新会锁存 `output_fault` 并关闭直接输出。恢复 I²C 通信后此故障仍保持，需排查后重启。DRV8874 自身的过流锁止可能还需用 SW2 断能复位。首件先断开电机，分别注入两侧 nFAULT 和母线欠压，用示波器同步观察 GPIO45、GPIO38、两侧 PWM_SAFE 和桥输入。100 ms／5 ms 是样板候选值，需以电源爬升、驱动唤醒和实际停止波形复核。[A4 电路与故障注入步骤](../../hardware/pcb/power-revision/README.md)

## 重现构建

在仓库根目录操作，先加载 ESP-IDF v5.5.1 环境。源码准备需要包含原始 ELF、sdkconfig 和锁定组件缓存的上游工作区，以及支持 tarfile data filter 的 Python 和 PyYAML。导出目标须是 `build/` 下尚不存在的目录。以下命令生成 A4 镜像；构建 A1 时使用 `--mainboard-a1` 和独立目录。

```sh
python firmware/esp32-audio/prepare.py /path/to/original/xiaozhi-esp32 --mainboard-a4 --target build/xiaozhi-ct82-a4-src
idf.py -C build/xiaozhi-ct82-a4-src -B "$PWD/build/firmware-ct82-a4" build
```

旧面包板回归使用独立目录。

```sh
python firmware/esp32-audio/prepare.py /path/to/original/xiaozhi-esp32 --target build/xiaozhi-ct82-breadboard-src
sh firmware/esp32-audio/test.sh
node firmware/esp32-audio/tests/web_ui_test.mjs
python firmware/esp32-audio/tests/run_mcp_tests.py --source build/xiaozhi-ct82-breadboard-src
python firmware/esp32-audio/tests/run_display_tests.py --source build/xiaozhi-ct82-breadboard-src
idf.py -C build/xiaozhi-ct82-breadboard-src -B "$PWD/build/firmware-ct82-breadboard" build
```

A1 通过 GPIO38 读取断电锁存状态，通过 GPIO45 重新使能执行器，GPIO14 保持扩展口关闭。[A1 断电与恢复](../../hardware/pcb/README.md#sw2-断电与恢复)

应用版本由 `apply_overlay.py` 设置。历史部署只写入核对过的应用分区，保留引导、NVS、OTA 选择与资源区。设备版本、备份及镜像回读见[ct78 应用部署记录](../../docs/validation/ct78-deployment.md)。

## 验证与观察

[ct82 检查记录](verification-ct82.json)包含 A4、A1 和面包板镜像身份、A4 故障注入模型及停止回归。[ct81 检查记录](verification-ct81.json)包含两种板型的构建摘要和跨避障闭锁的回归结果。[ct80 检查记录](verification-ct80.json)给出两个镜像的 SHA-256、SW2 主机测试及该版本停止矩阵结果。[ct79 检查记录](verification-ct79.json)涵盖本地构建、实际 MCP／HTTP 处理、音频、网页与停止矩阵回放。需要对齐现场日志时，`monitor.py --port <设备串口> --log build/audio-private/session.jsonl` 只读筛选回执和状态。真人拾音、扬声器、动作与机械停止按[现场记录方法](../../docs/validation/README.md)分别观察。

## 平台角色配置

[role-prompt.txt](role-prompt.txt) 是灵矽角色的唯一维护源。角色需另外同步并回读，流程见[角色维护与语音回归](../../docs/agent-role.md)。
