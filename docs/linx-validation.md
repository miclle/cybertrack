# 灵矽绑定、状态／停止与受限喷水实测

日期：2026-10-24，时间均为 Asia/Shanghai。范围为 ESP32-S3 N16R8 的设备绑定、真实 WSS、端侧 MCP 状态／停止，以及后续 0.2.0 受限喷水联调。不含音频硬件或其他执行器动作。前四节记录 0.1.0 阶段。

## 配置与烧录

- 用户确认 MOS 的 5 V 功率供电已断开，ESP32 保留 USB 供电；随后在本机私有文件填写 Wi-Fi。
- 用户选择新建独立 **CyberTrack** 智能体，未改变已有智能体或其设备。新角色要求查询／停止调用对应工具，并依据设备回执报告。
- 使用 `firmware/esp32-linx/`，ESP-IDF v5.5.1，`esp_websocket_client` 1.8.0。工具能力、动作时效预算全零，没有 GPIO4 高电平路径。
- 初次镜像加入 Wi-Fi／TLS 后超过原 factory 分区；启用尺寸优化及官方常用 CA 集后可容纳。保留已有 1 MiB factory 分区，分区表与 MOS 台架构建逐字节一致。
- 两次均仅更新 0x10000 应用区，115200 baud／no-stub，写入哈希检查通过；未改 bootloader、分区表或 eFuse，未擦除其他 Flash。第二次补齐 SNTP 与证书有效期验证及受控诊断。
- 最终镜像版本 `0.1.0-linx-readonly`，大小 **1,001,200 bytes**，SHA-256 `fe311a87d45636a40b251fc852526bd42207019635ef0d952a01af7e39860eca`。1 MiB 分区剩余 47,376 bytes，后续音频／动作扩展需重新核对容量。
- 首次配网后再次烧录应用，Wi-Fi 设置和 Client-Id 保留，设备未重复绑定。凭据不进入源码、构建参数或项目日志。原型 NVS 未加密。

## 真实链路证据

| 本地时间 | 观察结果 | 证据意义 |
|---|---|---|
| 17:09:51 | ESP32 报告 Wi-Fi 已连接 | 首次私有串口配网成功 |
| 17:10:11 | 智控台 CyberTrack 下出现 `cybertrack-s3-readonly` 设备 | 平台设备绑定成功 |
| 17:10:14 | WSS、hello、initialize、tools/list 成功 | 平台实际发现 `self.tank.get_status` 与 `self.tank.stop`，无动作工具 |
| 17:10:30 | 第一次查询触发平台“额度不足，请联系灵矽商务” | 当时没有工具调用成功证据；用户随后报告已购买并要求重试 |
| 17:14 | 智控台显示资源包正常 | 后续重试的账号条件已恢复，未由代理购买资源 |
| 17:14:36／17:14:46 | 首次 SNTP 等待超时，自动重试成功 | 超时期间未放宽证书校验；成功后才重新访问网关 |
| 17:14:47–48 | 最终固件报告绑定、WSS、hello、initialize 与 tools/list 成功 | 证书链、主机名及有效期校验启用后的真实连接 |
| 17:15:12 | 平台调用 `self.tank.get_status`，ESP32 回复 `isError=false`、`DISARMED`、`fault=none` | 真实查询闭环通过 |
| 17:15:26 | 平台调用 `self.tank.stop`，回复 `logical_outputs_cleared; local_reenable_required` | 真实停止工具闭环通过，控制核心进入锁定 |
| 17:15:28 | 平台再次调用状态，回复 `FAULT`／`stopped`，左右逻辑输出为 0，water／bubbles 为 false | 停止后状态闭环通过；三项动作能力仍为 false，`physical_feedback=false` |

测试通过串口 `status`／`stop` 发送固定 `listen.detect.text` 文本至灵矽，由灵矽发起真正的 `tools/call`。设备没有自行伪造平台调用。平台聊天记录也显示三次工具调用及返回值（平台界面将点号显示为下划线；设备协议仍用原工具名）。服务端 TTS 消息／二进制流未播放，不作为音频链路验收。

## 本地验证与证据位置

- `sh firmware/esp32-linx/tests/run.sh`：ASan／UBSan 通过；覆盖网关错误／凭据缺失／地址及 CR/LF 拒绝、hello、全部双段切分与 continuation、非法长度／乱序、仅两项工具、动作拒绝、重复停止、状态和重连未使能。
- ESP-IDF 最终构建通过，应用大小检查通过。编译不是实物电气验收。
- 本机忽略目录 `build/linx-private/` 保留 `session.log`、两次烧录日志、`device-bound.png`、`platform-quota.png`、`platform-tools.png`。绑定码只临时写入忽略的私有文件，收到已绑定状态后删除，不写入日志。
- 固件及配网／测试命令见[联网工程说明](../firmware/esp32-linx/README.md)。

## 验收边界和下一步

0.1.0 阶段已完成真实设备绑定、WSS／MCP 能力发现、状态查询、停止及停止后状态查询。当时仅开放这两项工具；后续 0.2.0 单次喷水结果见下节。

0.1.0 测试时 MOS 功率断开；没有重新测 GPIO 电压、实体 MOS 关断、带载停止延迟或独立供能切断。重复停止／非法动作／分片故障属于主机测试；真实断网、重复请求与断电恢复的完整故障矩阵未完成。当时音频采集／播放、喷水动作、实际存储防重放和整机验收尚未通过。后续在再次核对固件／供电及测试条件后开展的受限喷水结果见下节。

## 0.2.0 受限喷水联调（2026-10-24）

用户要求继续接入水枪，保留 5 秒自动停止与 BOOT 提前停止，并再次确认 MOS 5 V 功率断开、USB 保留。新增本机单次授权的喷水台架适配层；正式动作核心仍为零能力，未改其 logged 存储及认证新鲜度门槛。一次性授权、独立控制任务与状态说明见[0.2.0 工程说明](../firmware/esp32-linx/README.md)。

本轮主机 ASan／UBSan 覆盖固定 5000 ms 上限、非法时长、无授权／过期／旧授权／同 ID 及换 ID 重传、BOOT 停止与松开不恢复、冷却、断线／复位不恢复、停止和回复分配失败位置扫描，通过。ESP-IDF 构建通过；本轮镜像 SHA-256 为 `12ca36bdf4b2e8b4a4aeb3102780298c198adfc745d54d8c9f1235b756d4483c`。仍使用相同分区，仅更新应用。

上板与带载观察见下方；上述主机检查单独记录，不代替实物观察。

### 功率断开检查

- 17:34:03 新固件启动：`0.2.0`、GPIO4 LOW、单次授权、max_ms=5000。写入 1,008,496 bytes（块填充 1,008,640 bytes），哈希检查通过；原绑定与 Wi-Fi 保留。
- 17:35:29 SNTP 在两次超时后同步成功，随后 HTTPS／WSS、hello、初始化和三项工具发现通过；未为等待校时放宽证书校验。
- 17:35:38 本机仅创建一次新意图并发送固定测试文本；17:35:41 收到平台水枪工具调用，回复 `accepted`、启动计数 1。
- 17:35:46 设备记录 `WATER_OFF reason=deadline software_on_ms=5000 outputs=OFF`；17:35:53 平台状态查询返回 `DISARMED`、water=false、local_permit_armed=false、permit_used=true、starts_this_boot=1、completion=deadline_elapsed。
- 用户此前确认 MOS 功率断开。这是实际 ESP32 上的云端调用、软件期限与状态检查，不是本次负载喷水或电气脉宽测量。

### 带载自动停止与 BOOT 提前停止

用户确认接回已核对的 5 V→MOS→3.7 V 降压→水枪支路，水枪静止且供水／喷口方向就绪后，逐次执行：

| 本地时间 | 平台与设备证据 | 用户现场观察 |
|---|---|---|
| 17:36:58–17:37:05 | 单次本机授权；平台调用 water 返回 accepted，starts=2；设备到期关断，`software_on_ms=5001` | 用户确认“自动停止正常” |
| 17:37:31 | 状态回到 DISARMED，water=false，授权已用尽，starts=2，completion=deadline_elapsed | 无新增动作 |
| 17:38:03–17:38:06 | 用户确认 BOOT 测试就绪后仅发起一次新授权；平台调用 accepted，starts=3；`WATER_OFF reason=BOOT software_on_ms=720 outputs=OFF` | 用户确认“BOOT 停止正常，松开不恢复” |
| 17:38:20 | 状态 FAULT／stopped；water=false、boot_held=false、local_permit_armed=false、permit_used=true，starts 仍为 3 | 用户随后确认 MOS 5 V 已断开，USB 保留 |

**本轮受限喷水功能联调通过**：灵矽实际工具调用、单次喷水自动停止、BOOT 提前停止及释放不恢复均有对应软件记录和用户观察。总计 1 次功率断开调用、2 次带载调用，没有循环或自动重试。

5000 ms 是配置的单调时钟期限；5001 ms／720 ms 是控制任务记录的输出区间，受任务调度影响，不是示波器电气脉宽，720 ms 也不是按键到停喷的延迟。精确电气时限、真实断网／复位带载、独立切断、看门狗故障注入、温升／电流和完整安全验收仍未完成。远程停止工具本轮没有在喷水活动中再次带载测试；其软件取消路径有主机测试。语音采集、连续／自主喷水和正式持久化动作链路未开放。

本机原始记录仍为 `build/linx-private/session.log`，烧录日志 `flash-0.2.0-water.log`；证据截图 `platform-water.png`。一次性 permit 只用于当前云端请求，不进入本机日志或仓库；平台会话中可能保留已失效的请求内容。
