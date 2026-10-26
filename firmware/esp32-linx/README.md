# 灵矽受限控制联调固件

当前版本 **`0.2.0-linx-water-bench`**，ESP-IDF **v5.5.1**，ESP32-S3 N16R8。单次授权喷水见文末 0.2.0 小节；以下原状态／停止说明保留为 `0.1.0-linx-readonly` 阶段基线。此工程用于真实 Wi-Fi、设备绑定、WSS 和端侧 MCP 联调，复用现有控制核心／协议解析器。

核对日期：2026-10-27。本工程版本号属于独立 COREBOARD 联网台架，应继续保留；当前样机采用[面包板 ct21](../esp32-audio/README.md)，不能套用本页 GPIO4、0x10000 应用偏移或单次 permit。独立 0.2.0 有状态、停止和喷水三项工具，真实绑定、5 秒喷水及 BOOT 提前停止有[分项实测](../../docs/linx-validation.md)；完整故障、供电与整机验收未完成。

## 范围

**以下能力清单为 0.1.0 历史基线。** 0.2.0 新增喷水、GPIO4 受限输出及一次性授权，见文末；现用面包板音频和八工具能力不属于本工程。

- 仅声明 `self.tank.get_status` 和 `self.tank.stop`。能力及动作时效预算全零，没有本地使能入口，也没有把 GPIO4 置高的代码。
- GPIO4 为已核对 MOS 台架的临时控制引脚，应用开始时拉低，运行期间持续保持低；BOOT 对应 GPIO0 本地停止。停止回执证明逻辑锁定及软件撤销，不证明 MOS 实物关断或独立供能切断。
- 状态明确返回 `physical_feedback=false`，没有虚构液位、电量或实物反馈。
- 首次串口配网后，SSID、密码及软件 UUID 保存在独立 `linx` NVS namespace；不自动擦除 NVS。Wi-Fi 密码不嵌入编译产物。原型 NVS 未加密，不作凭据防提取承诺。
- HTTPS 网关验证 HTTP 和业务结果，绑定码仅在串口临时显示。令牌仅保留 RAM，不记录响应体。只接受官方 `xrobo-io.qiniuapi.com/v1/ws/`，将网关返回的该明确 WS 地址升级为官方支持的 WSS；其他地址拒绝，不降级。
- 联网后先等待 SNTP 同步；未同步时不访问网关。HTTPS／WSS 使用官方常用根证书集、主机名和证书有效期验证；连接／hello 超时、超长／乱序分片、接收队列溢出和发送失败关闭会话。重连重新获取令牌，清空旧队列并撤销逻辑使能。
- 无音频采集／播放、动作工具或 OTA 下载实现。`hello.audio_params={}` 申请仅工具联调，已取得服务端 hello、initialize 和 tools/list。二进制音频不播放。
- 未绑定时每 10 秒重新上报；没有自动执行任何动作或测试提示词。

## 构建和主机检查

在仓库根目录运行：

```sh
. ~/esp/esp-idf/export.sh
idf.py -C firmware/esp32-linx -B build/firmware-linx build
sh firmware/esp32-linx/tests/run.sh
```

组件 `espressif/esp_websocket_client` 固定为 1.8.0，依赖锁文件随工程保存。尺寸优化和常用 CA 集使镜像保持在既有 1 MiB factory 分区内；后续扩展应重新核对容量，不直接沿用此分区。

烧录前先断开 MOS／水枪功率供电并确认 USB 保留，释放现有串口。只有与当前设备分区一致时，才按 0x10000 更新应用。不要直接执行全量 `flash` 覆盖已有引导程序／分区，不擦除 Flash 或修改 eFuse。原水枪台架镜像保留用于恢复。

## 私有配网与串口

创建已被 Git 忽略的 `secrets/linx-wifi.json`：

```json
{"ssid":"本机填写 2.4 GHz 网络名称","password":"本机填写密码"}
```

启动持久连接（使用已安装 pyserial 的 ESP-IDF Python）：

```sh
python firmware/esp32-linx/serial_session.py \
  --port /dev/cu.usbmodem5CF91090631 --wifi secrets/linx-wifi.json
```

脚本不通过 DTR／RTS 主动复位。收到配网提示后提交配置，其他通信仅记录固件的受控诊断；绑定码写到权限 0600 的 `secrets/linx-activation.txt`，日志只写已生成提示。设备报告绑定后删除该临时码。禁止用原始 miniterm 全量日志记录绑定过程。

平台已初始化工具后，可从另一终端明确发送以下联调命令：

```sh
python firmware/esp32-linx/serial_session.py --command status
python firmware/esp32-linx/serial_session.py --command stop
python firmware/esp32-linx/serial_session.py --command s
```

`status`／`stop` 通过官方 `listen.detect.text` 向平台提交固定测试文本，由平台实际调用工具；`s` 是本地串口停止。只有 `LINX RPC ... sent=1` 与对应结果、平台记录共同确认后，才能记为真实工具联调通过。单纯发送测试文本不是成功证据。

## 验证状态

2026-10-24 的 0.1.0 历史检查：ASan／UBSan 主机检查通过：网关业务错误与令牌缺失、非受信任地址及 CR/LF 拒绝、hello、所有双段切分及 WebSocket continuation、乱序／超长拒绝、仅两项工具、动作拒绝、重复停止、状态和重连保持未使能。ESP-IDF 编译通过；真实绑定、WSS、状态、停止及停止后状态查询已通过，见[实测记录](../../docs/linx-validation.md)。

官方协议：[OTA 网关](https://linx.qiniu.com/docs/xrobot/platform/OTA)、[WebSocket](https://linx.qiniu.com/docs/xrobot/platform/websocket)、[端侧 MCP](https://linx.qiniu.com/docs/xrobot/mcp/hardware-mcp)。

## 0.2.0：单次授权喷水台架

2026-10-24 在用户授权下扩展为 `0.2.0-linx-water-bench`；以上 0.1.0 记录保留作为状态／停止阶段基线。新增 `self.tank.water`，仍不开放行走、泡泡、通用 GPIO 或云端使能。

本轮是**本机先创建一个明确的喷水意图，由灵矽返回工具调用**的台架流程。它不启用正式控制核心的动作通道：原 `ct_protocol` 的能力与新鲜度预算保持全零，生产级 logged 存储／锚点／恢复日志契约没有改动，也不将此台架称为其验收。

- 本机串口 `water` 为本次固定 5000 ms 意图生成 128 位随机一次性 permit，30 秒内有效，并通过已有认证 WSS 发送固定文本给平台。没有云端获取／续发授权的工具。
- 平台调用 `self.tank.water` 必须包含原样 permit 和整数 `duration_ms=5000`；无参、非法值、超时、旧授权、通知及重复调用不能启动。授权先消耗，之后才请求 GPIO 高电平。RPC ID 更换不能复用同一授权；重复调用不延长当前期限。
- 断线、停止、BOOT、复位均撤销待执行授权。复位后不会恢复动作或授权；重新测试必须在本机明确创建新意图。基于 RAM 和随机新授权避免旧许可跨启动复用，不声称实现历史 Flash 防回滚或生产级持久化验收。
- GPIO4 由独立、优先级 10 的控制任务驱动；FreeRTOS tick 1 ms，每 5 ms 检查单调时钟截止、BOOT 与连接状态。网络发送、JSON 解析和日志不持有控制锁；活动时控制任务不打印。停止或到期先拉低，再记录结果。BOOT 释放至少 30 ms 后才允许新的本机授权，释放本身不恢复动作。
- 任务注册看门狗，配置 2 秒／panic；这只是配置与运行证据，不是故障注入或物理独立切断验收。GPIO 启动／复位电气状态和真实停止延迟另测。
- `self.tank.get_status` 由台架适配层返回喷水策略状态、逻辑输出、当前授权状态及 `starts_this_boot`；`physical_feedback=false`。`accepted` 仅表示受理；`deadline_elapsed` 是软件到期，不能直接替代现场观察。
- 喷水结束后至少冷却 1 秒；没有自动重试或连续喷水。执行后默认不保留下一次授权。

联调命令（每执行一次 `water` 都是新的一次本地授权，只在现场准备完成后调用）：

```sh
python firmware/esp32-linx/serial_session.py --command water
```

本地 `s` 和平台 `stop` 都会撤销授权并关断。BOOT 提前停止在设备上按键完成。上板后先在 MOS 功率断开时检查真实工具调用／到期关闭，再接回已核对的 5 V→MOS→3.7 V 降压→水枪支路，逐次验证正常停止和 BOOT 停止。不要使用循环、自动重试或连续测试脚本。

新增 `water_policy`／`water_mcp` 的 ASan／UBSan 检查通过，覆盖 5 秒边界、授权过期／重复／换 ID／复位、BOOT 释放、冷却、断线、停止、非法时长和逐点回复分配失败。主机检查不代替带载观察。实际结果见[平台实测记录](../../docs/linx-validation.md)。
