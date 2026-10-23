# BOOT 键无负载本地停止验证

日期：2026-10-24（Asia/Shanghai）。用户明确授权使用板载 BOOT，保持 COM USB 供电、不接电机；按提示完成人工按键和 RST。固件 `0.2.0-boot-stop-check`，ESP-IDF v5.5.1。构建、3 项相关主机回归和应用烧录哈希校验均通过，板上保留此版本。

## 方法与实际结果

GPIO0 配置为低有效输入并启用内部上拉。正常启动的 PSRAM 自检完成后，按 10 ms 名义周期采样，复用 `ct_inputs` 的立即断言／30 ms 松开去抖；`ct_set_stop` 先于普通 tick。没有会话、本地使能、活动动作或执行器 GPIO/PWM，全部能力上限为零。

| 操作／观察 | 设备日志结果 |
|---|---|
| 首次启动 | 8 MB PSRAM 初始化、6 MiB 六模式读写与堆检查通过；DISARMED、零逻辑输出 |
| 第一次按下 BOOT | uptime 55862 ms，进入 FAULT／STOPPED，held=1 |
| 第一次松开 | uptime 57672 ms，held=0，仍为 FAULT／STOPPED；两事件间 1810 ms，包含松开去抖时间 |
| 第二次短按 | uptime 64112 ms，再次记录停止，保持 FAULT／STOPPED |
| 第二次松开 | uptime 64402 ms，held=0，继续锁定；两事件间 290 ms，包含松开去抖时间 |
| 松开后的连续观察 | 心跳一直保持 FAULT、held=0、逻辑输出为零；没有自动恢复 |
| BOOT 松开后人工短按 RST | 第二次启动再次完成全部内存检查，回到 DISARMED，presses=0；随后观察 1000 次 tick，约 10 秒，逻辑输出为零 |

连续日志见 [boot-stop.log](validation-2026-10-24-boot-stop/boot-stop.log)，采集判定及起止 UTC 时间见 [capture-result.json](validation-2026-10-24-boot-stop/capture-result.json)。[result.json](validation-2026-10-24-boot-stop/result.json)保存事件、源码／镜像／日志哈希及未测范围。日志出现两次应用启动：首次为采集器 RTS 自动复位，第二次由用户 RST；芯片均报告 POWERON／reset_reason=1，不计为拔线断电测试。

四个输入变化事件的软件采样至状态应用耗时均为 **5 µs**；记录到的最大轮询间隔为 **10000 µs**。这两项只反映本次无负载程序内部时序，不能合成为机械触点边沿到输出关闭的实测值，不能据此宣称带载 ≤100 ms 停止通过。

本次仅写应用镜像 223232 字节至 0x10000，覆盖扇区范围为 [0x10000, 0x47000)；COM 115200 baud、esptool 5.6.0、no-stub，写入哈希验证通过。没有改写 bootloader、分区表或 eFuse；此前原始 Flash 前 1 MiB 的本机备份仍保留，本次未再备份或全片擦除。

## 验证边界

此次通过的是**实体 BOOT 输入 → 软件停止锁定 → 松开不恢复 → RST 后未使能**。首次停止发生在 DISARMED，没有测试 ACTIVE 动作中断，也没有负载、电平测量、独立供能切断、本地重新使能、欠压或看门狗故障注入。

BOOT 是启动绑带：不按住它上电或复位；本轮不验证该组合。停止采样从 PSRAM 自检后开始，早期启动／自检期间和短于采样间隔的脉冲不保证捕获。后续生产停止输入与电源切断仍需单独设计；F2b 和 V04 只增加本项证据，不整体关闭。
