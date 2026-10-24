# 彩菊音频板：CyberTrack 状态／停止语音联调

此适配层用于现有 `bread-compact-wifi` 音频板，基于本机已验证的 `xiaozhi 2.0.3`，原 `2.0.3-ct2` 已完成无执行器状态／停止联调；当前 `2.0.3-ct5` 提供 GPIO18 按指令定时喷水台架（单次最多 30 秒），按用户要求取消逐次按键授权。保留彩菊绑定、音频、OLED、唤醒词、音量和触摸说话按键；BOOT 仅用于本地提前停止。只控制本板接入的 MOS，不控制另一块 ESP32。喷水接线、策略和本轮验收见[音频板喷水记录](../../docs/audio-water-validation.md)。

## 来源与配置证据

- 上游：[`78/xiaozhi-esp32`，`e8ed16bb42ed9b199cbc9376011653e5037de8d8`](https://github.com/78/xiaozhi-esp32/tree/e8ed16bb42ed9b199cbc9376011653e5037de8d8)。
- 本机原构建 ELF SHA-256：`f7e8809ce981ee4182fb6c3eb15b20aa785111c7f1e4b1e2f059e4debc813b45`，与音频板完整 Flash 中的应用描述一致；原 `xiaozhi.bin` 的 2,531,056 bytes 也与备份 `0x20000` 起的数据逐字节一致。
- 原 `sdkconfig` 固定在 `sdkconfig.baseline`，其有效配置与 ct2 构建逐项比较无差异；ct3 至 ct5 仅在导出源码配置中将 tick 改为 1000 Hz、任务看门狗改为 2 秒及 panic；原依赖版本在 `dependencies.lock` 中。使用本机原组件缓存的独立副本，避免下架组件引起依赖升级。
- ESP-IDF v5.5.1；ESP32-S3 N16R8；SSD1306 128×32；独立输入／输出 I2S；输入 16 kHz、输出 24 kHz；原唤醒模型保留。
- 原上游 checkout 及其中已有 Kconfig 修改没有被改动。源码导出和构建都在本仓库忽略的 `build/` 下进行。

## GPIO 配置

下表来自与原镜像对应的板级源码及构建配置，未另外逐线测量实物。

| 用途 | GPIO |
|---|---|
| 麦克风 WS／SCK／DIN | 4／5／6 |
| 扬声器 DOUT／BCLK／LRCK | 7／15／16 |
| OLED SDA／SCL | 41／42 |
| 板载 LED | 48 |
| BOOT：本地停止 | 0 |
| MOS TRIG/PWM（ct3 起） | 18 |
| 按住说话按键 | 47 |
| 音量增加／减少 | 40／39 |

**GPIO4 已被麦克风占用，不能照搬水枪板的 GPIO4 接线或固件。** ct3 取消 BOOT 原对话／启动配网回调，由独立任务读取。待机时先语音唤醒建立会话，明确口述喷水和时长即可请求一次最长 30 秒输出。BOOT 按下即取消／停止，松开不恢复；新的语音指令可在按键释放及冷却结束后再次启动。独立功率切断仍须保留。

上游示例 `LampController` 会占用 GPIO18 并注册开灯工具。本适配不实例化它，ct2 替换为两项 CyberTrack 工具；ct3 由受限喷水任务使用 GPIO18，音频与显示板级定义保持原样。

## ct2 历史工具语义

- `self.tank.get_status`：读取本板 CyberTrack 控制核心的逻辑状态。初始 `DISARMED`；能力全部关闭，`physical_feedback=false`、`actuator_backend=not_installed`。
- `self.tank.stop`：在同一个序列化主任务内调用 `ct_stop`，进入 `FAULT/stopped` 并清除逻辑输出；重复调用仍保持锁定。不终止 TTS、不禁用屏幕，不声称实体停止或已控制另一台设备。
- 两项工具只接受空参数；额外参数在执行前拒绝，schema 标明 `additionalProperties=false`。不提供 GPIO、喷水、行走、泡泡或重新使能工具。
- 回执带本板 MAC、随机启动标识、单调递增请求序号及运行时间，便于对照平台真实工具调用。状态不会在重新开始对话时自动解除停止；重启后仍为不可动作的 DISARMED。
- 复用 `firmware/src/control.c`，通过 `apply_overlay.py` 复制到临时构建目录，不另写一套动作状态机。

## ct5 工具语义

- `self.tank.water` 只接受整数 `duration_ms`，范围 1–30000 ms；不再暴露 permit，不要求长按 BOOT。必须是明确的喷水指令；状态查询不会喷水。角色将秒数转换为毫秒，超过 30 秒按 30 秒执行并说明；未说明时长先询问，不沿用历史请求。固件拒绝零、负数、非整数和超出 30000 的参数，不自动分段。
- `get_status` 与 `stop` 只接受空参数。状态报告本板水枪逻辑输出，`local_authorization_required=false`、`physical_feedback=false`。主动停止为 `STOPPED/fault=stopped`，不是硬件损坏；故障仍为 FAULT。
- 复用 `esp32-linx/main/water_policy.c` 的截止与冷却策略，新增 `water_request_timed` 接口允许 1–30000 ms；原 `water_request` 的固定 5000 ms 行为不变，授权函数仅在本地请求执行时原子调用，不作为用户操作门槛。`water_guard.h` 校验网络接收时的就绪状态，并为队列创建内部票据；停止、BOOT、断线取消所有待执行票据，超过 5 秒未执行的请求拒绝。
- 同一音频会话最多记住 128 个喷水 RPC ID，重复 ID 拒绝，不逐出旧 ID；表满拒绝进一步喷水，新会话重新开始。内部票据跨会话不复用；不宣称跨重启持久化防重放。
- 独立优先级 10 控制任务每 5 ms 检查 BOOT、连接与期限。截止由本次 duration_ms 决定，上限 30000 ms，活动时不续时，结束后冷却 1 秒。BOOT 释放需稳定 30 ms；松开或恢复网络本身都不启动动作。
- 停止在网络接收时立即关断，再通过主任务返回回执。已检测的 Wi-Fi／WebSocket 断线、复位与升级均关闭输出。活动输出期间控制任务不进行显示、日志、网络或堆分配。

ct3 的逐次物理授权流程和 ct4 的固定五秒要求已被用户明确取消，历史结果保留在[喷水验证记录](../../docs/audio-water-validation.md)。用户已确认控制线纠正后喷水测试正常，带载 BOOT 提前停止及松开不恢复也已确认。上述结果属于 ct4 五秒配置；ct5 已通过功率断开的 1／7 秒及 40 秒请求限为 30 秒的语音核验，用户确认音频／屏幕正常，不能推导 30 秒带载已通过。真实断网故障矩阵、独立硬件切断和完整供电验收仍未完成，软件输出回执本身不证明有水流。

## 重现构建

需保留原始源码 checkout、原构建 ELF 及组件缓存；不要求联网下载替代版本。`prepare.py` 要求一个尚不存在的 `build/xiaozhi-audio-src`，不会覆盖已有导出或修改原 checkout。

```sh
# 先激活 ESP-IDF v5.5.1 的 Python 环境与 export.sh。
python firmware/esp32-audio/prepare.py /path/to/original/xiaozhi-esp32
sh firmware/esp32-audio/test.sh
idf.py -C build/xiaozhi-audio-src -B "$PWD/build/firmware-audio" build
```

应用分区是 `ota_0`，起点 `0x20000`、大小 `0x3f0000`，与水枪台架分区不同。更新前需核对设备 MAC、分区表、OTA 选择及已有备份；本轮仅写该应用，不执行完整 `idf.py flash`，不覆盖引导、NVS、OTA 数据或 8 MB assets。

## 验证与观察

`test.sh` 运行 ASan／UBSan 主机检查，验证 ct2 只读核心，以及 ct5 可变时长启动、截止边界与非法时长拒绝、忙碌／冷却拒绝、BOOT／停止取消排队请求、断线、复位、重复 RPC、队列过期和时钟故障。它不代表音频、实物停止或端到端语音通过。

`monitor.py --port <设备串口> --log build/audio-private/session.jsonl` 只监听和筛选 CT_AUDIO 回执、运行状态及少量启动信息，不发送串口命令，不保存原始串口日志或录音。平台工具记录和用户现场音频／屏幕观察共同构成语音联调证据。详见[验证记录](../../docs/audio-board-validation.md)。


## 平台角色配置

现有“彩菊”智能体的助手昵称调整为“小D”；设备绑定沿用。角色介绍原文保存在 `role-prompt.txt`，用于灵矽角色配置的“角色介绍”字段，昵称使用 `{{assistant_name}}`。角色聚焦响应指令与报告状态，通常只说一句结果，不寒暄、不重复指令、不主动展开或追问；按真实工具回执回答，主动停止不解释为硬件损坏。音色和模型保持现有选择。平台提示保存后需重启设备生效；修改昵称不会更改固件唤醒词“你好小智”。提示词不是固件动作限制的替代品。


平台意图识别已由分离模式调整为统一模式，用于让聊天模型直接选择工具；原分离模式下泛称“查询状态”曾误选通用设备信息工具。统一模式下相同说法已正确调用 CyberTrack 工具，停止和停止后查询也已实测通过；详见验证记录。这是本轮有限样本结果，不保证所有表达方式。
