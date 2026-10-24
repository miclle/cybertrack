# 彩菊音频板：CyberTrack 状态／停止语音联调

此适配层用于现有 `bread-compact-wifi` 音频板，基于本机已验证的 `xiaozhi 2.0.3`，生成 `2.0.3-ct2`。**没有执行器驱动、动作工具或本地使能入口**。保留彩菊绑定、音频、OLED、唤醒词和原有对话／音量按键；不控制另一块水枪 ESP32。

## 来源与配置证据

- 上游：[`78/xiaozhi-esp32`，`e8ed16bb42ed9b199cbc9376011653e5037de8d8`](https://github.com/78/xiaozhi-esp32/tree/e8ed16bb42ed9b199cbc9376011653e5037de8d8)。
- 本机原构建 ELF SHA-256：`f7e8809ce981ee4182fb6c3eb15b20aa785111c7f1e4b1e2f059e4debc813b45`，与音频板完整 Flash 中的应用描述一致；原 `xiaozhi.bin` 的 2,531,056 bytes 也与备份 `0x20000` 起的数据逐字节一致。
- 原 `sdkconfig` 固定在 `sdkconfig.baseline`，其有效配置与新构建逐项比较无差异；原依赖版本在 `dependencies.lock` 中。使用本机原组件缓存的独立副本，避免下架组件引起依赖升级。
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
| BOOT：原有对话开关 | 0 |
| 按住说话按键 | 47 |
| 音量增加／减少 | 40／39 |

**GPIO4 已被麦克风占用，不能照搬水枪板的 GPIO4 接线或固件。** BOOT 在这块音频板上仍是原有对话按键，不是水枪台架的紧急停止输入；启动且未联网时按它还可能进入原有重新配网流程。实际执行器及独立停止输入需后续另行设计。

上游示例 `LampController` 会占用 GPIO18 并注册开灯工具。本适配不实例化它，替换为两项 CyberTrack 工具；音频与显示板级定义保持原样。

## 工具语义

- `self.tank.get_status`：读取本板 CyberTrack 控制核心的逻辑状态。初始 `DISARMED`；能力全部关闭，`physical_feedback=false`、`actuator_backend=not_installed`。
- `self.tank.stop`：在同一个序列化主任务内调用 `ct_stop`，进入 `FAULT/stopped` 并清除逻辑输出；重复调用仍保持锁定。不终止 TTS、不禁用屏幕，不声称实体停止或已控制另一台设备。
- 两项工具只接受空参数；额外参数在执行前拒绝，schema 标明 `additionalProperties=false`。不提供 GPIO、喷水、行走、泡泡或重新使能工具。
- 回执带本板 MAC、随机启动标识、单调递增请求序号及运行时间，便于对照平台真实工具调用。状态不会在重新开始对话时自动解除停止；重启后仍为不可动作的 DISARMED。
- 复用 `firmware/src/control.c`，通过 `apply_overlay.py` 复制到临时构建目录，不另写一套动作状态机。

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

`test.sh` 运行 ASan／UBSan 主机检查，验证初始关闭、停止锁定、重复停止、状态序号和时钟故障。它不代表音频、实物停止或端到端语音通过。

`monitor.py --port <设备串口> --log build/audio-private/session.jsonl` 只监听和筛选 CT_AUDIO 回执、运行状态及少量启动信息，不发送串口命令，不保存原始串口日志或录音。平台工具记录和用户现场音频／屏幕观察共同构成语音联调证据。详见[验证记录](../../docs/audio-board-validation.md)。


## 平台角色配置

现有“彩菊”智能体的助手昵称调整为“小D”；设备绑定沿用。角色介绍原文保存在 `role-prompt.txt`，用于灵矽角色配置的“角色介绍”字段，昵称使用 `{{assistant_name}}`。语气改为友好简洁，状态和停止按真实工具回执回答；`FAULT/stopped` 解释为主动停止锁定，其他故障仍如实报告。音色和模型保持现有选择。平台提示保存后需重启设备生效；修改昵称不会更改固件唤醒词“你好小智”。提示词不是固件动作限制的替代品。


平台意图识别已由分离模式调整为统一模式，用于让聊天模型直接选择工具；原分离模式下泛称“查询状态”曾误选通用设备信息工具。统一模式下相同说法已正确调用 CyberTrack 工具，停止和停止后查询也已实测通过；详见验证记录。这是本轮有限样本结果，不保证所有表达方式。
