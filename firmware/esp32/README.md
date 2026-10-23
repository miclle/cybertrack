# ESP32-S3 无负载启动、PSRAM 与 BOOT 停止检查

本工程固定 ESP-IDF **v5.5.1**、目标 `esp32s3`，用于已到货的 N16R8 板。当前版本为 `0.2.0-boot-stop-check`。它链接 CyberTrack 的 `src/control.c` 和 `src/inputs.c`，正常启动状态从 BOOT 进入 DISARMED；能力上限全零，没有本地使能、执行器 GPIO/PWM、网络或音频实现。此处的默认关闭检查只针对控制核心的逻辑输出，BOOT 键只用于本轮无负载停止输入验证，不代表执行器引脚电平、供能切断或完整 F2b 已验收。

Flash 为 16 MB、DIO 40 MHz；PSRAM 为 Octal 40 MHz，启动初始化及 ESP-IDF 内置内存检查开启，初始化失败不允许忽略。采用显式 `MALLOC_CAP_SPIRAM` 分配，普通堆仍留在内部 RAM。DIO 是本次固件访问模式，不改变此前识别到的 Flash quad 硬件能力。

## 构建、烧录与读取

在仓库根目录，先激活已安装的 ESP-IDF v5.5.1 环境：

```sh
. "$IDF_PATH/export.sh"
idf.py -C firmware/esp32 -B "$PWD/build/firmware-esp32" build
```

保持仅接板背标注 COM 的 USB 线、不接电机及其他执行器。确认串口实际路径后，以 `<COM_PORT>` 替换以下占位符。烧录会替换当前应用；需要保留原程序时先备份将覆盖的 Flash 扇区，备份只存本机忽略目录，不能提交其中可能存在的凭据。本次覆盖区域均低于 1 MiB，因此备份了前 1 MiB，未执行全片擦除。

验证使用独立环境的 esptool **5.6.0**，低速 ROM 通路；首次完整烧录命令如下。2026-10-24 的更新只写 0x10000 处的应用镜像，保留已有 bootloader 和分区表：

```sh
esptool --chip esp32s3 --port <COM_PORT> --baud 115200 --no-stub \
  write-flash --flash-mode dio --flash-size 16MB --flash-freq 40m \
  0x0 build/firmware-esp32/bootloader/bootloader.bin \
  0x8000 build/firmware-esp32/partition_table/partition-table.bin \
  0x10000 build/firmware-esp32/cybertrack_board_check.bin
```

通过 COM 以 115200 baud 读取串口，按 RST 可重复自检。`tools/capture_check.py` 使用 pyserial，经 DTR/RTS 自动复位并捕获三次检查：

```sh
python firmware/esp32/tools/capture_check.py --port <COM_PORT> \
  --output build/board-validation-private/serial
```

## 检查范围

1. 确认 PSRAM 初始化，检测容量恰为 8 MiB。
2. 显式分配 6 MiB 外部 RAM，并验证指针位于外部 RAM。
3. 对完整分配区依次写入、读回全零、全一、`AAAAAAAA`、`55555555`、地址相关数据及其反码。每轮先写满再读回；覆盖区大于缓存，访问使用 volatile，避免仅验证缓存或被优化掉。每 16384 字让出一个 tick。
4. 释放测试区并检查堆完整性；失败打印 `VALIDATION FAIL`，能力保持零。
5. 自检成功后调用真实控制核心的 `ct_boot_complete`，检查 DISARMED 和零逻辑输出。每 10 ms 采样 BOOT、处理停止并调用 `ct_tick`，每 100 次输出心跳；无按键采集器等待 6000 次 tick，且拒绝重启、panic 或失败日志。

这不是全 8 MiB 逐字节覆盖、长时老化、掉电／欠压、全 Flash、实体输出或看门狗故障注入测试。测试结果与构建哈希见[板卡实物记录](../../hardware/components/ESP32-S3-N16R8/physical-verification.md)。

## BOOT 停止输入测试

用户授权在无电机条件下临时使用板载 BOOT／GPIO0，低电平有效，配置为输入并启用内部上拉。只在 PSRAM 自检结束后开始采样；不支持在上电或复位时按住 BOOT 的正常应用测试，因为该引脚同时控制下载启动。RST 是复位，不是独立电源切断。

复用通用输入滤波器：按下在被采样的当轮立即断言，松开稳定 30 ms 后释放输入；调用 `ct_set_stop` 先于普通 tick。按下后控制核心保持 `CT_FAULT / CT_STOPPED`，松开不恢复使能。此工程没有本地使能入口、活动动作或执行器输出，不能证明 ACTIVE 带载停止。

```sh
python firmware/esp32/tools/capture_stop.py --port <COM_PORT> \
  --output build/boot-stop-private/serial
```

采集器先通过 COM 自动复位一次。看到 `BOOT_STOP READY ... held=0` 后，人工按住 BOOT 约 2 秒、松开等待至少 3 秒；再短按一次、松开等待至少 3 秒。确认 BOOT 已松开后短按 RST。采集器等待第二次启动自检通过且保持未使能约 10 秒后结束；全过程限时 20 分钟，日志连续写入。

`observed_to_apply_us` 只测从软件采样点到应用停止状态的时间，`max_poll_gap_us` 是观察到的最大轮询间隔；两者都不是机械触点边沿到电机停止的测量。GPIO 未使用中断，短于采样间隔的脉冲不保证捕获。后续仍需专用停止输入、独立供能切断及带载验收。

2026-10-24 的人工两次按键与 RST 测试已通过，详见[BOOT 停止实物记录](../../hardware/components/ESP32-S3-N16R8/boot-stop-verification.md)。
