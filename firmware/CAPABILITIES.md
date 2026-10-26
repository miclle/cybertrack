# 固件能力与接口手册

核对日期：2026-10-27。本文描述仓库当前实现，作为“有哪些能力、模块、接口，怎样传参和读取结果”的统一入口。板上实际版本须以启动日志为准；本文不表示所有工程已经合并为一个整机固件。源代码及各工程的验证记录是行为与验收依据。

## 阅读导航

- 看当前能做什么：[工程与能力](#工程与能力)。
- 配置语音工具或读取回执：[当前面包板 ct21 接口](#当前面包板-ct21-接口)。
- 对接另一块联网板：[联网水枪台架接口](#联网水枪台架接口)。
- 开发正式控制固件：[正式控制核心的-mcp-接口](#正式控制核心的-mcp-接口)、[模块与数据流](#模块与数据流)、[内部-c-api](#内部-c-api)。
- 做本地调试：[串口与板级接口](#串口与板级接口)。
- 看证据和缺口：[验证与维护](#验证与维护)。

## 工程与能力

| 工程／版本 | 已实现能力 | 当前边界与证据 |
|---|---|---|
| [当前面包板](esp32-audio/README.md) `2.0.3-ct21` | 八个 CyberTrack MCP 工具、网页与语音并用、四路独立控制、三路长按与狂暴模式；约 80% PWM，B／左、A／右 | 已完成软件检查、仅应用部署及启动联网；用户确认前后左右正常。已有样机行走／转向／泡泡影像；停止距离、电流、温升、完整故障与四路组合负载仍未验收 |
| 通用 C11 核心 `src/` | 行走／喷水／泡泡逻辑目标、限时互斥、停止锁定、MCP、运行层、输入滤波、队列、连接模拟、防重放及维护恢复 | [主机记录](tests/README.md)报告 23/23 CTest；没有完整生产板级后端，正式核心的真实网络动作未开放 |
| [无负载工程](esp32/README.md) `0.2.0-boot-stop-check` | 启动、PSRAM 检查、周期控制核心、BOOT 停止输入 | 已有无负载实测；不驱动执行器，无网络／音频 |
| [L298N 电机台架](esp32-motor-bench/README.md) `0.3.2-l298n-dual-10s` | A／B／AB 选择、本地使能、约 60% PWM／10 秒单次动作、BOOT 同停 | A=GPIO4／5／6，B=GPIO7／8／9；双路软件回归／编译通过，B 路接线及六脚静态关闭已获用户确认，此前 0.3.1 的 3 秒版 8 组空载组合已获用户确认：单路互不干扰、方向符合预期、正常停止且无异响或异常发热；随后一次双路 BOOT 提前停止及松开不恢复也获用户确认；用户已确认 40% 反转方向、约 10 秒停止及运行母线约 12 V；60%／10 秒反转获用户正常停止反馈，母线约 12 V，较 40% 更快、更顺畅且无异常；用户已确认双路 60%／10 秒空载正转正常启停，启动、运行中及临近停止母线均约 12 V，电机和 L298N 无明显发热、无异响或其他异常；这是万用表读数与主观发热观察，电流和定量温升仍未测；电流／温升和带载验收待完成；不是整机行走接口 |
| [MOS 台架](esp32-mos-bench/README.md) `0.1.1` | 本地串口单次 5 秒 GPIO4 输出、自动结束、BOOT／串口停止 | 已有一次正常喷水／到期停止及 BOOT 带载提前停止观察；完整供电与故障验收未完成 |
| [联网板](esp32-linx/README.md) `0.2.0-linx-water-bench` | Wi-Fi、绑定、WSS、MCP 状态／停止、本机单次授权的 5 秒喷水 | 已有真实平台调用、喷水及 BOOT 功能检查；无音频，正式核心动作仍关闭 |
| [面包板 ct9 历史版](../docs/lan-control.md) `2.0.3-ct9` | 按住持续行走、松开停止、600 ms 续租截止，保留定时喷水和语音 | 当时已部署，无负载 HTTP／桌面网页通过；后续 ct10 已有功率断开的手机／语音有限联调，完整带载仍未验收 |
| [面包板 ct8 历史候选](../docs/lan-control.md) `2.0.3-ct8` | 同一 ESP32 提供局域网页面、定时动作、状态刷新、全停、独占网页会话，保留语音 | 当时主机测试与交叉编译通过，未烧录；独占网页规则已被 ct10 替代，历史缺口不等同于当前状态 |
| [面包板 ct7 历史版](../docs/concurrent-actions.md) `2.0.3-ct7` | 行走与喷水独立计时、可同时运行，新增组合启动工具，统一停止 | 主机测试、编译、应用刷写与平台同步已通过，核心并发台架已完成；完整供电及整机验收待完成，见 ct7 记录；历史 ct6 互斥测试不作为并发验收 |
| [面包板历史版](esp32-audio/README.md) `2.0.3-ct6` | 保留语音／唤醒／OLED／音量／说话按键；状态、统一停止、双路电机与 GPIO18 喷水互斥 | ct6 部署、平台同步、迁线及基本台架联调完成；断网、剩余语音回归和整机带载待验；行走 1–3000 ms、约 60%，喷水 1–30000 ms。ct4 带载／ct5 功率断开历史结果不转移为 ct6 验收 |

当前面包板已部署泡泡与点火低压 MOS 控制，ct7 两路并发台架、ct21 四方向现场反馈及[样机影像](../artifact/README.md)分别记录。影像没有绑定完整固件／电源配置，不能作为当前四路整机验收。超声波测距／避障、编码器闭环、舵机动作、液位／水流／电量遥测及双板协同控制均未在这些项目接口中实现。高压接线、安全、绝缘、液体共存及 EMC 仍未验收，见[效果控制](../docs/effects-control.md)。上游音频工程可能还发布其自带工具，本文只定义 CyberTrack 增加的 `self.tank.*`。

以下三套同名工具不能混用：

| 差异 | 当前面包板 ct21 | 联网板 0.2.0 | 正式核心 |
|---|---|---|---|
| `water` 参数 | `duration_ms` | `duration_ms` + `permit` | `duration_ms`，另须可信元数据 |
| 定时请求时长 | 水枪／泡泡／狂暴 1–30000 ms；行走 1–3000 ms；点火 1–5000 ms；网页长按另有租约 | 必须 5000 ms | 受 `ct_limits` 限制；默认禁用 |
| 启动门槛 | 新的明确指令、在线、非忙碌、按键释放且冷却结束 | 本机串口先签发一次性许可 | 本地使能、会话、时效、认证证据及存储门槛 |
| 停止后再次启动 | 满足条件的新指令；不需逐次按键授权 | 新的本机许可 | 本地重新使能 |
| 状态输出字段 | `logical_outputs.left/right` | `logical_output.left_level/right_level` | `logical_output.left_level/right_level` |
| 防重放范围 | 当前音频会话内动作共用最多 128 个 RPC ID，不提供跨启动持久化保证 | 单次许可，RAM 中保存 | RPC／意图过滤器，另有持久化抽象；真实后端待接入 |

`accepted` 表示软件接受了本次请求，`water=true` 表示逻辑目标；二者均不证明已经有水流。三个接口均声明 `physical_feedback=false`。

## 当前面包板 ct21 接口

源码版本与最新有记录的部署均为 `2.0.3-ct21`，见[软件验证](esp32-audio/verification-ct21.json)及[部署与四方向反馈](esp32-audio/startup-ct21.json)。实现入口为 [工具注册与回执](esp32-audio/cybertrack_tools.cc)、[MCP 参数校验](esp32-audio/apply_overlay.py)、[动作策略](esp32-audio/action_guard.h)、[来源与租约](esp32-audio/control_sessions.h)和[输出驱动](esp32-audio/action_outputs.h)。以下为当前接口，后文 ct6／ct7 及版本演进保留历史语义。

### 当前工具入参

表中名称均带 `self.tank.` 前缀。动作参数必须显式提供，拒绝额外字段、非法方向、非整数及越界值；`_ct_ticket` 为内部票据，不能由调用者传入。

| 工具 | `arguments` | 行为 |
|---|---|---|
| `get_status` | `{}` | 查询本板逻辑状态与能力 |
| `stop` | `{}` | 取消模式、四路输出与待执行票据，保留语音和屏幕 |
| `move` | `direction` 为 `forward/backward/left/right`；`duration_ms` 整数 1–3000 | 固定约 80% PWM，不支持距离／角度闭环 |
| `water` | `duration_ms` 整数 1–30000 | 单次定时喷水控制 |
| `bubbles` | `duration_ms` 整数 1–30000 | 单次定时泡泡控制 |
| `ignition` | `duration_ms` 整数 1–5000 | 一个低压 MOS 通道控制两只点火模块，不代表高压硬件验收 |
| `move_and_water` | `direction` 四选一；`move_duration_ms` 整数 1–3000；`water_duration_ms` 整数 1–30000 | 两路均就绪才整体接受，独立到期关闭 |
| `frenzy` | `duration_ms` 整数 1–30000 | 四路均就绪才启动：左转、喷水、泡泡持续，点火每次最多 1000 ms，关闭后至少等实际软件 ON 时长再启动下一脉冲；到期全停 |

角色源 [role-prompt.txt](esp32-audio/role-prompt.txt)负责将明确请求换算为参数：普通动作未说时长为 1000 ms，狂暴模式为 5000 ms，组合未说时长各为 1000 ms；超限只请求上限并说明，不循环补足。固件不自行补缺参或截断越界值。2026-10-27 的别名、纠错与成功静默规则已保存到平台，真人语音回归仍待完成，见[角色维护](../docs/agent-role.md)。

### 当前状态与控制边界

工具结果为 MCP 文本中的 JSON；动作须检查内部 `result="accepted"`，外层成功不证明动作接受，更不证明实物执行。参数／领票失败走 `ReplyError`；回调还可能返回 `not_ready_or_busy`、`stale_request`、`cancelled_or_duplicate`、`cancelled_before_output` 或 `output_fault` 等。未知结果不作为接受，不自动重试。

| 字段／规则 | 当前含义 |
|---|---|
| `logical_outputs` | `left/right` 为 −80/0/80，表示方向与标称占空比；`water/bubbles/ignition` 为布尔值，可同时活动 |
| `capabilities` | `move/water/move_and_water/bubbles/ignition/frenzy/water_hold/bubbles_hold` 均为 true，能力存在不代表此刻可启动 |
| `actuator_backend`、`physical_feedback` | `concurrent_motor_effects_bench`、false；无轮速、水流或停止传感反馈 |
| 各路计时与来源 | `move/water/bubbles/ignition` 各有 `_last_duration_ms`、`_remaining_ms`、`_cooldown_ms`、`_source`；来源为 web/voice/none |
| 汇总与模式 | `remaining_ms` 取四路剩余时长最大值；模式另读 `frenzy_remaining_ms/frenzy_last_duration_ms/frenzy_source`；`starts_this_boot` 是软件启动计数，不是实物检测次数 |
| 时限与间隔 | 定时上限见入参表；行走／喷水／泡泡停止后间隔 200 ms；`ignition_cooldown_policy=equal_elapsed_on_time`，点火按本次实际软件 ON 时长计算间隔 |
| 网页长按 | 行走／喷水／泡泡支持 start/renew/stop，各路租期 600 ms，松开仅停本路，续租凭据一次使用；普通定时语音请求不续时，点火没有长按持续接口 |
| 网页与语音 | 页面自动连接，不再使用 ct8 配对码或独占规则；同通道冲突网页优先，停止冲突语音并保留冷却。`control_owner=shared` 只代表双入口连接 |
| 停止与断线 | BOOT／全部停止／Wi-Fi 断开全停；来源会话关闭取消该来源动作，模式按来源取消；松开／重连不恢复，需新的有效请求 |
| 重放与排队 | 会话内最多 128 个动作 RPC ID，重复拒绝、表满不淘汰；内部票据 5 秒过期，停止／断线取消；无跨启动持久化防重放保证 |

完整 HTTP 路由、租约字段与来源切换见[局域网控制](../docs/lan-control.md)，源码 JSON 字段以工具实现为准。ct21 的 B／左、A／右为根据现场方向反馈修正的映射，桥身份未独立逐线核对；四方向反馈不扩展为定量停止、电流或温升验收。

<a id="音频板-ct5-接口"></a>

## 面包板 ct7 接口

**历史版本。** ct7 新增并发动作，完整语义与部署状态见[ct7 说明](../docs/concurrent-actions.md)。单项 `move`／`water` 原参数和上限保持，允许同时活动，分别截止和冷却；停止仍全停。

新增 `self.tank.move_and_water({"direction":"forward","move_duration_ms":1000,"water_duration_ms":3000})`：仅接受上述三个字段，方向四选一，行走整数 1–3000 ms、喷水整数 1–30000 ms。两路全部就绪才接受；忙碌时整体拒绝不部分执行。共享票据绑定目标通道，类型不符返回 `ticket_target_mismatch`；内部非法移动参数返回 `invalid_move`。单路启动只取消与自己重叠的排队票据。参数错误走 ReplyError。

状态增加 `capabilities.move_and_water=true`、`move_last_duration_ms`、`water_last_duration_ms`、`move_remaining_ms`、`water_remaining_ms`、`log_events_dropped`。两路输出可同时活动，汇总 remaining_ms 取最大剩余时间，last_duration_ms 为最近请求时长（组合取最大），starts_this_boot 按启动的通道数累计，组合加 2。actuator_backend 改为 concurrent_motor_water_bench。细分日志为 ACTION_OFF channel=move/water；软件策略、输出驱动和平台角色须一并更新，ct6 设备不支持新工具。

下节保留 ct6 旧接口及历史语义，ct7 历史接口以上述差异为准，ct21 见上文；通用核心、独立联网板与台架不随此次改动变为并发。

<a id="面包板-ct6-接口"></a>

## 面包板 ct6 历史接口

以下描述 ct6，已完成本面包板刷写及平台同步，迁线及该阶段基本语音台架验证已完成，完整验收仍未完成。接线、刷写与平台同步状态见[集成记录](../docs/breadboard-integration.md)。ct5 仅有水枪；兼容保留旧锚点便于已有链接访问。

当前实现入口（已演进，不能用于重现 ct6 历史源码）：[工具注册与回执](esp32-audio/cybertrack_tools.cc)、[MCP 校验补丁](esp32-audio/apply_overlay.py)、[共享动作策略](esp32-audio/action_guard.h)、[输出驱动](esp32-audio/action_outputs.h)。传输和 MCP 基础服务由固定版本的小智上游工程承载，不使用下文正式核心的 `ct_protocol_handle`。

### 工具入参

| 工具 | 用途 | `arguments` | 输出 |
|---|---|---|---|
| `self.tank.get_status` | 查询本板当前策略与逻辑输出 | `{}`，也可省略；不接受额外参数 | 下表 JSON 状态，`operation=get_status`、`result=ok` |
| `self.tank.stop` | 同时关闭两路电机和水枪，取消全部待执行票据；不关闭语音／屏幕 | `{}`，也可省略 | 相同结构，`operation=stop`、`result=ok`；正常停止为 `STOPPED` |
| `self.tank.water` | 接受一次定时喷水请求 | 必填 `duration_ms`：JSON number，整数值，1–30000，单位毫秒；对象只能含这一项 | 相同结构，`operation=water`，检查内部 `result` 判断是否接受 |
| `self.tank.move` | 接受一次四方向定时动作 | 必填 `direction`：`forward/backward/left/right`；`duration_ms`：整数值 1–3000；只含这两项 | 相同结构，`operation=move`；固定约 60% PWM，不支持距离／角度闭环 |

建议始终发送普通整数，例如 `7000`。ct6 使用 cJSON 数值和整数值相等性校验，没有正式核心“必须十进制整数 token”的词法限制；不要假定两者对 `1000.0`／指数写法的处理相同。`_ct_ticket` 是固件插入的内部票据，不是云端参数，不能自行传入。

平台角色负责秒数转毫秒；明确喷水但未指定时长的 ct6 角色规则为 `1000` ms，超过 30 秒则请求 `30000` 并说明，不拆成循环。固件本身没有缺参默认值，也不会将越界值自动截断。ct6 工具描述已与角色统一；行走也默认 1000 ms，超过三秒请求 3000 并说明。指定时长等基本端到端行为已验证，默认时长和上限等剩余用例仍待按[集成步骤](../docs/breadboard-integration.md)验证。

### 工具出参

工具结果文本是 JSON 字符串。先解析 MCP 响应，再解析 `content` 中 `type=text` 的 `text`。下表为该 JSON 的全部字段，四项工具共用。

| 字段 | 类型 | 含义 |
|---|---|---|
| `device_id` | string | 本板 MAC 标识，不代表另一块主控 |
| `boot_id` | string | 本次启动生成的 16 位十六进制标识；重启变化 |
| `request_sequence` | number | 本次启动的回执计数，非 RPC ID、非持久化动作序号 |
| `operation` | string | `get_status`／`stop`／`water`／`move` |
| `result` | string | 查询／停止无故障时为 `ok`；动作为 `accepted` 或拒绝原因；输出错误为 `output_fault` |
| `state` | string | `DISARMED`（空闲）、`ACTIVE`、`STOPPED` 或 `FAULT`；空闲不保证已过冷却 |
| `fault` | string | `none`／`stopped`／`clock_fault`／`output_fault`；`stopped` 是主动停止状态 |
| `uptime_ms` | number | 本地单调运行时间，毫秒 |
| `logical_outputs` | object | `left/right:-60/0/60`（逻辑方向与标称占空比）、`water:boolean`、`bubbles:false`；电机与水枪互斥 |
| `capabilities` | object | `move:true`、`water:true`、`bubbles:false`；能力存在不代表此刻可启动 |
| `local_authorization_required` | boolean | 固定 `false`，无逐次按键授权门槛 |
| `starts_this_boot` | number | 本次启动已接受的两类动作总数，非实体动作检测次数 |
| `max_duration_ms` | number | 水枪上限，固定 `30000` |
| `move_max_duration_ms` | number | 电机上限，固定 `3000` |
| `move_direction` | string | 活动行走的 `forward/backward/left/right`，否则 `none` |
| `last_duration_ms` | number | 最近一次接受的时长；尚无动作时为 `0` |
| `remaining_ms` | number | 活动目标的剩余毫秒数；非活动为 `0` |
| `actuator_backend` | string | 固定 `bounded_motor_water_bench` |
| `physical_feedback` | boolean | 固定 `false` |
| `source` | string | 固定 `cybertrack_audio_board` |

动作不能仅凭外层 MCP 请求成功就判定成功：到达回调后的业务拒绝也会作为 JSON 文本返回，必须检查内部 `result == "accepted"`。参数校验或领取票据失败则走上游 `ReplyError`，没有上述完整状态对象。

| 阶段／结果 | 含义 |
|---|---|
| `ReplyError`：`Water requires exactly integer duration_ms in 1..30000` | 缺参、额外字段、类型或范围错误 |
| `ReplyError`：`Action request duplicate, busy, offline or queue full` | 接收时就无法领取票据；重复 RPC、忙碌、离线、按键／冷却／时钟条件不满足、128 项耗尽等 |
| `ReplyError`：`Move requires direction forward/backward/left/right and integer duration_ms in 1..3000` | 行走方向、时长、字段或类型错误 |
| `cancelled_before_output` | 目标接受后、输出应用前被 BOOT／断线／时限取消 |
| `output_fault` | GPIO／PWM API 出错，锁定并尝试全停 |
| `cancelled_or_duplicate` | 票据不存在、已使用，或被停止／断线取消 |
| `stale_request` | 从领取票据至执行已达 5000 ms，或时间回退 |
| `duration_out_of_range` | 内部二次检查时长不合法 |
| `not_ready_or_busy` | 执行时无法原子创建本次内部许可 |
| `accepted` | 本次目标已接受并尝试应用 GPIO／PWM；不证明物理动作 |

共用策略还定义 `clock_fault`、`not_ready`、`invalid_permit`、`permit_used`、`permit_expired_or_revoked`、`busy` 等拒绝值；正常音频路径由票据与原子授权挡住其中多种情况。未知结果一律不当作接受，不自动重试。

### 调用示例与时序

以下仅展示 MCP JSON-RPC payload，不是设备执行指令；外层封装由平台传输负责：

```json
{"jsonrpc":"2.0","id":101,"method":"tools/call","params":{"name":"self.tank.water","arguments":{"duration_ms":1000}}}
```

接收线程校验参数并领取内部票据 → 主任务执行回调，在共用锁内复核条件并应用 GPIO／PWM → 返回 JSON 文本（接受时 `result=accepted`）→ 独立控制任务检查本地期限并关闭。随后使用新的请求 ID 查询：

```json
{"jsonrpc":"2.0","id":102,"method":"tools/call","params":{"name":"self.tank.get_status","arguments":{}}}
```

提前停止：

```json
{"jsonrpc":"2.0","id":103,"method":"tools/call","params":{"name":"self.tank.stop","arguments":{}}}
```

控制任务每 5 ms 检查期限、BOOT 和连接；BOOT 释放需稳定 30 ms，喷水结束后冷却 1000 ms，电机结束后冷却 3000 ms。活动期间不续时／换向，两类动作互斥，同一音频会话重复动作 ID 拒绝，128 项满后不淘汰旧记录；一个请求被接受后取消其余已排队票据。停止、已检测的断线会取消排队票据；释放按键／恢复网络不会自行喷水。新指令仍需满足执行条件。不存在跨启动持久化防重放保证，也没有“水流停止完成”事件。

## 联网水枪台架接口

实现：[water_mcp.c](esp32-linx/main/water_mcp.c)、[water_policy.c](esp32-linx/main/water_policy.c)。0.2.0 在能力全零的正式协议实例外增加独立水枪策略。

| 工具 | 入参 | 出参／语义 |
|---|---|---|
| `self.tank.get_status` | 空参数 | MCP 文本内的 JSON；字段见下表 |
| `self.tank.stop` | 空参数 | 正式协议的文本 `logical_outputs_cleared; local_reenable_required`；适配器同时撤销水枪许可并关断。这里再次喷水需新的本机许可，不能把该文本解释为存在云端使能接口 |
| `self.tank.water` | `duration_ms`：整数，必须 `5000`；`permit`：32 个字符的字符串，使用本机签发的原始小写十六进制令牌 | `result.isError=false` + 文本 `accepted`；策略拒绝时 `isError=true` + 原因字符串 |

喷水仅接收有 ID 的请求；此分支 ID 为非负安全整数或 1–64 UTF-8 字节非空字符串。必须已初始化且会话匹配；通知不启动。许可由本机串口 `water` 创建，30 秒有效、使用一次即消耗；更换 RPC ID 不能重用许可。非法参数回落正式解析器拒绝，不会启用正式核心动作。许可不是对外提供的获取／刷新接口。

| 状态字段 | 类型／值 | 含义 |
|---|---|---|
| `state` | string：`ACTIVE`／`READY`／`FAULT`／`DISARMED` | 依次按活动、已授权、已停止、空闲选择 |
| `fault` | string：`clock_fault`／`stopped`／`none` | 水枪策略故障或停止原因 |
| `logical_output` | object | `left_level:0`、`right_level:0`、`water:boolean`、`bubbles:false` |
| `capabilities` | object | `move:false`、`water:true`、`bubbles:false` |
| `physical_feedback` | boolean：`false` | 无实体反馈 |
| `water_bench.local_permit_armed` | boolean | 当前有待执行授权 |
| `water_bench.permit_used` | boolean | 当前／最近许可已消耗 |
| `water_bench.boot_held` | boolean | BOOT 按下或尚未稳定释放 |
| `water_bench.max_duration_ms` | number：`5000` | 固定执行时长 |
| `water_bench.starts_this_boot` | number | 本次启动接受次数 |
| `water_bench.authorization` | string | 固定 `local_single_use_intent; no_autonomous_actions` |
| `water_bench.completion` | string | `running`／`stopped_or_disconnected`／`deadline_elapsed`／`idle`，均为软件状态 |

策略拒绝文本：`clock_fault`、`not_ready`、`invalid_permit`、`permit_used`、`permit_expired_or_revoked`、`duration_must_match_5000ms_intent`、`busy`。到期自动关闭、1 秒冷却及按键释放规则见[工程说明](esp32-linx/README.md)。

## 正式控制核心的 MCP 接口

实现：[protocol.c](src/protocol.c)；完整封装、去重、错误及资源契约见 [PROTOCOL.md](PROTOCOL.md)。这些动作已经过离线逻辑测试，但不代表目前设备能通过它们行走或吹泡泡。

### 方法与工具

外层为 `{"type":"mcp","payload":{...}}`，payload 使用 JSON-RPC `2.0`。ID 支持最长 64 UTF-8 字节字符串或绝对值不超过 `9007199254740991` 的十进制整数；数字与字符串 ID 不同。合法通知无响应；动作通知不执行，合法停止通知执行。

| 方法 | 入参 `params` | 出参 |
|---|---|---|
| `initialize` | `protocolVersion:"2024-11-05"`、对象 `capabilities`、`clientInfo:{name:string,version:string}` | `protocolVersion`、`capabilities.tools:{}`、`serverInfo:{name:"CyberTrack offline adapter",version:"0.1.0"}` |
| `ping` | 省略或 `{}` | `result:{}` |
| `tools/list` | 省略或 `{}`；不接受分页 | `result.tools` 数组；每项含 `name`、`description`、`inputSchema`；无 `nextCursor` |
| `tools/call` | `name:string`、工具规定的 `arguments` | `result:{isError:boolean,content:[{type:"text",text:string}]}`，或 JSON-RPC `error` |
| `notifications/initialized` | 通知 | 忽略，无响应 |

| 工具 | 入参 `arguments` | 正常出参文本 |
|---|---|---|
| `self.tank.get_status` | 省略或 `{}` | JSON 状态对象，见下表 |
| `self.tank.stop` | 省略或 `{}` | `logical_outputs_cleared; local_reenable_required` |
| `self.tank.move` | `direction`：`forward`／`backward`／`left`／`right`；`speed_level`：1–255 整数；`duration_ms`：1–4294967295 整数 | `accepted` |
| `self.tank.water` | `duration_ms`：同上 | `accepted` |
| `self.tank.bubbles` | `duration_ms`：同上 | `accepted` |

动作时长与速度还须不超过 `ct_limits`，类型范围不是操作建议值。所有参数拒绝额外字段；`null` 不能代替空对象；数值必须普通十进制整数 token。`max_queue_ms=0` 时仅发现状态与停止；其他动作按非零能力配置发布。没有远程使能、任意 GPIO、高压或维护恢复工具。

| 状态字段 | 类型／值 | 含义 |
|---|---|---|
| `state` | string：`BOOT`／`DISARMED`／`READY`／`ACTIVE`／`FAULT` | 控制状态；正常到期回 READY，停止锁定至本地重新使能 |
| `fault` | string：`none`／`stopped`／`external_fault`／`session_lost`／`clock_fault` | 故障或停止原因 |
| `logical_output` | object | `left_level`、`right_level` 为有符号档位；`water`、`bubbles` 为 boolean |
| `capabilities` | object | `move`、`water`、`bubbles` 为 boolean，来自配置，不是实时就绪保证 |
| `physical_feedback` | boolean：`false` | 仅逻辑状态 |
| `replay_guard.scope` | string：`boot`／`persistent` | 当前防重放历史范围 |
| `replay_guard.storage` | string：`volatile`／`ready`／`fault` | 存储绑定／故障状态，不是物理 Flash 验收结论 |
| `replay_guard.bits_set`、`bits_total` | number | 过滤器已置位数／总位数（262144）；不是命令数，可能误拒绝新动作 |

错误分三层：API 返回 `CT_RPC_*`（是否生成响应）、JSON-RPC `error.code/message`（协议错误）、工具 `result.isError/text`（业务拒绝）。常见业务拒绝为 `not_ready`、`unavailable`、`invalid`、`busy`、`session_mismatch`、`replay`、`expired`、`clock_error`、`stale_local_enable`、`invalid_receive_time`、`freshness_unverified`、`sequence_exhausted`。完整数值错误表见 [PROTOCOL.md](PROTOCOL.md#错误映射与资源边界)。

单帧上限 2048 字节，响应缓冲至少 4096 字节，16 槽 FIFO 保存原响应。相同 ID／相同内容可能返回旧状态快照，读取当前状态要用新 ID。停止优先于动作时效及缓存检查。动作还须通过本地使能、原始会话／使能代次、设备预签发窗口、稳定意图与防重放门槛；这些可信证据不是可加入 JSON 的参数。

## 模块与数据流

| 模块 | 实现入口 | 职责 |
|---|---|---|
| 控制核心 | [control.h](include/cybertrack/control.h)／`src/control.c` | 状态机、动作互斥、限时及逻辑目标，不直接写 GPIO |
| MCP | [protocol.h](include/cybertrack/protocol.h)／`src/protocol.c` | 封装、工具发现、参数校验、缓存、防重放及动作分派 |
| 新鲜度 | [freshness.h](include/cybertrack/freshness.h)／`src/freshness.c` | 设备窗口与意图作用域检查；不执行认证 |
| 运行层 | [runtime.h](include/cybertrack/runtime.h)／`src/runtime.c` | 本地事件优先、周期预算、输出回调、喂狗与故障锁定 |
| 输入 | [inputs.h](include/cybertrack/inputs.h)／`src/inputs.c` | 停止／故障立即断言、释放去抖、已观察脉冲锁存 |
| 收件队列 | [inbox.h](include/cybertrack/inbox.h)／`src/inbox.c` | 4 槽完整帧副本、元数据保持、断线优先、溢出关闭 |
| 连接模拟 | [link.h](include/cybertrack/link.h)／`src/link.c` | WebSocket 分片组装、握手门槛、超时、发送完成与重连状态机；没有实际网络 I/O |
| 防重放存储 | [replay_store.h](include/cybertrack/replay_store.h)／`src/replay_store.c` | 双槽历史、独立锚点、迁移、选择及维护恢复 |
| 恢复日志 | [replay_log.h](include/cybertrack/replay_log.h)／`src/replay_log.c` | 独立完整证据、两槽或四槽冗余，支持缺失主快照的维护恢复 |
| 联网工程 | [linx_main.c](esp32-linx/main/linx_main.c)、[linx_wire.h](esp32-linx/main/linx_wire.h) | 实际 Wi-Fi／网关／WSS、hello 与分片处理，独立台架入口 |
| 水枪策略／适配 | [water_policy.h](esp32-linx/main/water_policy.h)、[water_mcp.h](esp32-linx/main/water_mcp.h) | 单次许可、截止、冷却及台架 MCP；面包板复用策略 |
| 面包板适配 | [cybertrack_tools.h](esp32-audio/cybertrack_tools.h)、[action_guard.h](esp32-audio/action_guard.h)、[action_outputs.h](esp32-audio/action_outputs.h) | 上游工具注册、共享票据／独立并发策略、六路电机与 GPIO18／17／21 输出、网页来源／租约和狂暴模式、统一停止和状态 |

通用库的数据流是 SDK 事件 → `link` → `inbox` → `runtime` → `protocol` → `control` → 板级输出回调；本地停止／故障由运行层先处理。现有联网台架和音频适配各自实现板级循环，不能把这条通用库组合路线视为已经完整部署到它们。

## 内部 C API

本节列出公开头文件的接口、参数职责与返回结果；精确声明及生命周期约束见各表链接。`c/p/r/q/f` 等分别表示对应控制器、协议、运行层、队列或过滤器的指针，均由调用方提供；除明确标出的输出指针外，状态通过 API 原地更新。所有 `now`／`now_ms` 都是 `uint64_t` 本地单调毫秒，不是墙上日期。通用模块由单一任务串行拥有，无内部线程或锁；不得从 ISR 与网络任务并发调用。

### 控制数据与入口

| 类型 | 字段及用途 |
|---|---|
| `ct_limits` | `uint32_t move_max_ms/water_max_ms/bubbles_max_ms`：各动作最大毫秒数；`uint8_t max_speed_level`：最大档位；零表示不可用 |
| `ct_request` | `uint64_t session/sequence/expires_at_ms`：会话、严格递增序号、最晚开始期限；`ct_action action`：MOVE/WATER/BUBBLES；`ct_direction direction`；`uint8_t speed_level`；`uint32_t duration_ms` |
| `ct_output` | `int16_t left_level/right_level`、`bool water/bubbles`；左右正值均为车体向前，档位不是 PWM 百分比 |
| `ct_action_proof` | 四个 `uint64_t`：`session/enable_generation/window/intent`；认证来源绑定命令，意图非零并跨重试稳定 |
| `ct_rpc_delivery` | `uint64_t session/received_at_ms/enable_generation` + `ct_action_proof proof`；首次入队的可信元数据，出队或重试不得刷新 |

[control.h](include/cybertrack/control.h)：

| API | 入参 | 返回／副作用 |
|---|---|---|
| `ct_init` | `c, limits, now_ms` | `void`；清零控制器，进入 BOOT |
| `ct_boot_complete` | `c` | `ct_result`；完成启动门槛，正常进 DISARMED；已有停止／故障进 FAULT |
| `ct_tick` | `c, now_ms` | `ct_result`；推进时限，到期撤销目标；时钟回退锁定 |
| `ct_set_session` | `c, uint64_t session, now_ms` | `ct_result`；0 表示断线，新会话撤销使能，活动中改变会话锁定 |
| `ct_set_stop`／`ct_set_fault` | `c, bool held/present` | `void`；断言时撤销目标，解除输入不自动恢复 |
| `ct_stop` | `c` | `void`；幂等停止，锁定为 STOPPED 原因 |
| `ct_local_enable` | `c, now_ms` | `ct_result`；仅本地事件使用；满足条件进入 READY、增加使能代次 |
| `ct_submit` | `c, const ct_request *request, now_ms` | `ct_result`；成功设置目标和结束期限；空请求拒绝，同会话有效新序号即使请求被拒也会消耗 |

`ct_result`：`CT_OK`、`CT_NOT_READY`、`CT_UNAVAILABLE`、`CT_INVALID`、`CT_BUSY`、`CT_SESSION_MISMATCH`、`CT_REPLAY`、`CT_EXPIRED`、`CT_CLOCK_ERROR`。`CT_OK` 是本次 API 操作成功，不必然是接受动作；仅 `ct_submit` 的成功表示新目标接受。单独使用控制核心也必须周期 tick 并应用输出。

### 协议与新鲜度

[protocol.h](include/cybertrack/protocol.h)、[freshness.h](include/cybertrack/freshness.h)：

| API | 入参 | 返回／出参 |
|---|---|---|
| `ct_protocol_init` | `p, ct_controller *control, uint32_t max_queue_ms` | `void`；每次启动初始化一次，零时效预算禁用动作 |
| `ct_protocol_set_allocator` | `p, ct_rpc_allocator allocator` | `bool`；首次 open 前配置；allocator 含 `allocate(context,size)`、`resize(context,ptr,old_size,size)`、`release(context,ptr)` 及上下文 |
| `ct_protocol_attach_store` | `p, ct_replay_store *store` | `bool`；绑定普通持久化抽象，用于兼容／离线 |
| `ct_protocol_attach_guarded_store` | 同上 | `bool`；另要求已绑定独立锚点 |
| `ct_protocol_attach_logged_store` | 同上 | `bool`；另要求独立恢复日志；真实动作集成必须走此入口并接入认证来源 |
| `ct_protocol_issue_window` | `p, now_ms, ct_action_proof *challenge`（输出） | `bool`；签发窗口，不使能，challenge 的 intent 留零；必须在生产者创建意图之前调用 |
| `ct_protocol_open` | `p, now_ms` | `uint64_t` 新会话代次；失败为 0；撤销原使能 |
| `ct_protocol_close` | `p, now_ms` | `void`；关闭会话、取消动作 |
| `ct_protocol_handle` | `p, const char *frame, size_t length, ct_rpc_delivery delivery, now_ms, char *reply, size_t reply_cap` | `ct_rpc_result`；只有 RESPONSE 时读取 reply；reply_cap 至少 4096 |
| `ct_freshness_issue` | `ct_freshness *f, uint64_t session, uint64_t enable_generation, now_ms, uint32_t budget_ms, ct_action_proof *challenge`（输出） | `bool`；替换旧窗口，预算／计数／时间无效则失败 |
| `ct_freshness_check` | `const ct_freshness *f, ct_action_proof proof, uint64_t session, uint64_t enable_generation, uint64_t received_at_ms, now_ms` | `CT_FRESH`／`CT_FRESH_MISSING`／`CT_FRESH_STALE`／`CT_FRESH_EXPIRED` |

`ct_rpc_result` 为 `CT_RPC_RESPONSE`（有响应）、`CT_RPC_NO_RESPONSE`（通知）、`CT_RPC_STALE_SESSION`（旧连接，无响应）、`CT_RPC_BAD_ARGUMENT`（API 参数无效）。绑定必须在首次 open 前完成，失败锁定存储故障，不允许悄悄退回易失动作。认证证据不由 `issue_window` 或 `freshness_check` 自动产生，详见 [FRESHNESS.md](FRESHNESS.md)。

### 运行层、输入与队列

[runtime.h](include/cybertrack/runtime.h)、[inputs.h](include/cybertrack/inputs.h)、[inbox.h](include/cybertrack/inbox.h)：

| API | 入参 | 返回／出参 |
|---|---|---|
| `ct_runtime_init` | `r, ct_protocol *protocol, ct_board_io io, ct_limits limits, uint32_t queue_ms, uint32_t max_cycle_ms` | `bool`；先 force_off 后自检；周期预算必须非零 |
| `ct_runtime_step` | `r, const ct_runtime_event *event, ct_runtime_response *response` | `bool`；空 event 表示空闲 tick；MESSAGE 必须提供 response。true 表示运行基础健康，不代表动作接受；有效运行实例失败时尽力关断、锁定并抑制响应，不保证关断回调成功 |
| `ct_inputs_init` | `ct_input_filter *f, uint32_t release_ms, uint32_t enable_ms, ct_local_inputs initial, now_ms` | `bool`；两个去抖时间须非零，上电按住使能不会使能 |
| `ct_inputs_observe` | `f, ct_local_inputs raw, now_ms` | `bool`；锁存已观察的停止／故障，时钟回退使过滤器失效 |
| `ct_inputs_read` | `f, ct_local_inputs *inputs`（输出） | `bool`；消费锁存事件，保留持续按下／去抖中的状态 |
| `ct_inbox_init` | `ct_inbox *q` | `void`；启动时一次初始化 |
| `ct_inbox_bind` | `q, uint64_t session` | `bool`；绑定严格递增的新会话，前一断线必须先应用 |
| `ct_inbox_push` | `q, const char *frame, size_t length, ct_rpc_delivery delivery` | `CT_INBOX_OK`／`STALE`／`OVERFLOW`／`OVERSIZE`／`INVALID`（均有 `CT_INBOX_` 前缀）；复制完整帧 |
| `ct_inbox_disconnect` | `q, uint64_t session` | `void`；标记断线并清除该会话排队消息 |
| `ct_inbox_take` | `q, ct_inbox_item *item`（输出） | `ct_event_kind`；断线优先，空队列返回 IDLE |

`ct_local_inputs` 含三个归一化布尔量 `stop/fault/enable_button`，true 表示有效。`ct_runtime_event` 含 `kind`（`CT_EVENT_IDLE/CONNECT/DISCONNECT/MESSAGE`）、`frame`、`length`、`delivery`；响应包含 `ct_rpc_result result` 和 `reply[4096]`。队列 item 拥有帧副本；普通远程停止仍在消息 FIFO 中，本地停止不经该 FIFO。

板级 `ct_board_io` 的全部回调返回 bool；false 必须按运行层契约处理，回调成功不是物理反馈：

| 回调 | 入参／出参 | 职责 |
|---|---|---|
| `force_off` | `void *context` | 请求所有执行器关闭；启动最先调用 |
| `self_test` | `context` | 不启用执行器的自检 |
| `now_ms` | `context, uint64_t *now`（输出） | 提供单调毫秒时钟 |
| `read_inputs` | `context, ct_local_inputs *inputs`（输出） | 返回去抖与锁存后的本地输入 |
| `write_outputs` | `context, const ct_output *output` | 映射逻辑目标至板级驱动 |
| `watchdog_kick` | `context` | 本轮检查与输出成功后喂狗 |

`r->faults` 为锁定故障位图：`CT_RUNTIME_CONFIG/SELF_TEST/CLOCK/SCHEDULING/INPUT/OUTPUT/OFF_FAILED/WATCHDOG/FRESHNESS`（每项均带 `CT_RUNTIME_` 前缀）。详情见 [RUNTIME.md](RUNTIME.md)，不能从网络清除这些故障。

### 通用连接层

[link.h](include/cybertrack/link.h)：所有操作携带原连接 attempt，禁止把旧 SDK 回调重新标成新连接。状态为 `DOWN/CONNECTING/HANDSHAKE/ONLINE/BACKOFF/HALTED`（`CT_LINK_` 前缀）。

| API | 入参 | 返回／出参 |
|---|---|---|
| `ct_link_init` | `ct_link *link, ct_runtime *runtime, ct_link_limits limits` | `bool`；limits 的 `connect_ms/handshake_ms/fragment_ms/send_ms/retry_ms` 均为非零 uint32 毫秒 |
| `ct_link_begin` | `link, now_ms` | `uint64_t attempt`，不满足启动条件返回 0 |
| `ct_link_connected`／`ct_link_ready` | `link, uint64_t attempt, now_ms` | `bool`；ready 是可信适配器完成 TLS／认证／hello 后的信号，库本身不验证它们 |
| `ct_link_receive` | `link, attempt, ct_ws_chunk chunk, ct_action_proof proof, now_ms` | `bool`；处理 SDK 给出的 WebSocket 分片，不接收原始 TCP；proof 来自首次分片的认证来源 |
| `ct_link_closed` | `link, attempt, now_ms` | `void`；登记关闭 |
| `ct_link_service` | `link, now_ms` | `bool`；周期处理本地输入、断线、消息与超时；false 表示已停止服务 |
| `ct_link_take_tx` | `link, ct_link_tx *tx`（输出）, `now_ms` | `bool`；一次性复制待发响应至发送任务存储 |
| `ct_link_sent` | `link, uint64_t attempt, uint64_t id, bool success, size_t bytes, now_ms` | `bool`；报告该响应的发送结果，不自动重发 |

`ct_ws_chunk` 字段：`opcode`（CONT/TEXT/BINARY/CLOSE/PING/PONG）、`bool fin`、`size_t offset/total/length`、`const char *data`；offset/total 针对单个 WebSocket 帧，跨帧 continuation 另行组装。`ct_link_tx` 含 `attempt/id/length/frame`，id 是本地发送标识，不是 RPC ID。通用层目前只接 MCP 文本路径，二进制音频不能从这里处理。错误枚举覆盖连接／握手／分片／发送超时、格式／容量／队列／时钟／运行层等，详见头文件与 [TRANSPORT.md](TRANSPORT.md)。

### 防重放存储与恢复

这些是本地内部接口，不是远程工具。下列操作要求同一串行所有者；登记、迁移、切换与恢复必须关闭输出，恢复时退役协议所有者。所有 bool 失败都必须按专题契约处理，不能直接擦除历史重试。

| API | 入参 | 返回／出参 |
|---|---|---|
| `ct_replay_store_load` | `ct_replay_store *s, ct_replay_io io` | `CT_STORE_FAULT/EMPTY/READY`；启动只读加载，双槽严格核验 |
| `ct_replay_store_provision` | `s` | `bool`；明确的首次空白介质初始化，不是修复／重置 |
| `ct_replay_store_save` | `s, const unsigned char *filter, uint64_t session` | `bool`；保存完整 32768 字节过滤器的单调超集及会话高水位，先持久化后接受动作 |
| `ct_replay_store_bind`／`ct_replay_store_enroll` | `s, ct_replay_anchor_io anchor, uint64_t backend_id` | `bool`；前者绑定已登记锚点，后者仅首次登记；不可混用作故障恢复 |
| `ct_replay_store_check` | `s` | `bool`；重读锚点，防止旧所有者继续写入 |
| `ct_replay_store_migrate` | `const ct_replay_store *source, ct_replay_store *destination` | `bool`；向独立空白目标复制历史，不负责持久后端选择 |
| `ct_replay_store_switch` | `source, destination, uint64_t destination_id` | `bool`；复制后原子选择新后端，成功退役源对象 |
| `ct_replay_store_recover` | `source, anchor, uint64_t source_id, destination, destination_id` | `ct_replay_recovery_result`；从精确匹配当前锚点的完整主快照恢复至空白目标 |
| `ct_replay_log_init` | `ct_replay_log *log, ct_replay_io io` | `bool`；配置两槽独立日志，不擦除／登记 |
| `ct_replay_log_init_redundant` | `log, io, ct_replay_log_redundancy *workspace` | `bool`；显式四槽双副本模式，workspace 生命周期覆盖日志使用期 |
| `ct_replay_store_attach_log` | `s, log` | `bool`；核验／补齐当前精确历史后绑定日志 |
| `ct_replay_store_enroll_logged` | `s, log, anchor, backend_id` | `bool`；先准备日志，再首次登记锚点 |
| `ct_replay_store_recover_log` | `source, log, anchor, source_id, destination, destination_id` | `ct_replay_recovery_result`；从独立日志恢复当前精确历史，可不依赖主快照 |

后端回调来自 [replay_store.h](include/cybertrack/replay_store.h)：

| 回调 | 入参／出参 | 契约 |
|---|---|---|
| `ct_replay_io.read` | `context, unsigned slot, size_t offset, void *data, size_t size` | bool；精确长度读入 data |
| `ct_replay_io.erase` | `context, unsigned slot` | bool；仅擦除指定槽 |
| `ct_replay_io.write` | `context, slot, offset, const void *data, size` | bool；精确长度写入；false 可能已经部分完成 |
| `ct_replay_io.sync` | `context` | bool；成功必须保证前序变更持久且有序，不能只保证缓存可读 |
| `ct_replay_anchor_io.read` | `context, ct_replay_anchor_record *record`（输出） | bool；读取独立、防回滚的持久记录 |
| `ct_replay_anchor_io.replace` | `context, const record *expected, const record *next` | bool；全字段比较后原子持久替换，失败可能已经提交，需重新检查 |

锚点 record 的四个字段均为 uint64：`epoch/backend_id/revision/session`；全零只能表示从未登记，不能把丢失或损坏当作全零。主存储槽大小为 32800 字节，日志槽大小为 32816 字节。恢复结果为 `CT_RECOVERY_OK` 或 `BAD_ARGUMENT/ANCHOR_UNAVAILABLE/WRONG_BACKEND/HISTORY_UNAVAILABLE/HISTORY_CONFLICT/DESTINATION_UNAVAILABLE/SELECTION_UNCERTAIN/EXHAUSTED/LOG_UNAVAILABLE`（各带 `CT_RECOVERY_` 前缀）。

详细顺序与失败语义：[持久化](PERSISTENCE.md)、[容量与迁移](CAPACITY.md)、[原子切换](ATOMIC-SWITCH.md)、[恢复](RECOVERY.md)、[独立日志](RECOVERY-LOG.md)、[冗余](REDUNDANCY.md)。这些是经过假介质测试的抽象契约，尚无满足契约的真实 Flash／NVS／独立锚点实现。

### 工程适配接口

| API／模块 | 入参 | 返回／出参 |
|---|---|---|
| `water_tick` | `water_policy *s, now, bool online, bool boot_held` | void；处理期限、释放稳定期、断线和时钟异常 |
| `water_stop` | `s, now` | void；取消活动及许可，活动被停止时进入冷却 |
| `water_arm` | `s, now, const char token[33]` | bool；校验并登记调用方提供的 32 个小写十六进制字符，建立一次性许可；不生成随机令牌 |
| `water_request`／`water_request_timed` | `s, now, const char *token, uint32_t duration` | `const char *`；分别要求 5000 或 1–30000 ms，返回 accepted 或拒绝文本 |
| `water_mcp_handle` | `ct_protocol *p, frame, size, delivery, now, reply, cap, water_callbacks cb` | `ct_rpc_result`；cb 含 `snapshot()->water_policy`、`stop()->void`、`request(token,duration)->const char *`，回调须有界、串行 |
| `linx_parse_gateway` | `const char *json, size_t size, linx_gateway *out` | bool；成功取得六位绑定 `code` 或 `token/url`，失败清零；令牌不得记录 |
| `linx_parse_hello` | `json, size, char session[128]`（输出） | bool；校验 hello／websocket，提取可选会话字符串 |
| `linx_text_feed` | `linx_text *s, int opcode, bool fin, size_t offset, total, const char *data, size_t size` | int：1 完整文本（读取 `s->text/used`）、0 未完成或控制／二进制帧、-1 非法 |
| `InitializeCyberTrackTools` | 无 | void；面包板初始化 GPIO、控制任务、事件监听并注册工具 |
| `CyberTrackActionLink` | `bool online` | void；音频连接状态变化，离线取消票据并关断 |
| `CyberTrackActionStop` | 无 | void；即时取消／关断，不等待主任务回复 |
| `CyberTrackActionClaim` | `int rpc_id, const char* operation` | int；正数为内部票据，0 为拒绝 |
| `AudioWaterGuard::Tick/Stop/Claim/Request`（ct5 历史适配／测试对象） | 分别 `(now,online,pressed)`／`(now)`／`(now,rpc_id)`／`(now,ticket,duration)` | 前两者 void；Claim 返回票据或 0；Request 返回结果字符串。必须在适配器锁内执行 |
| 两套台架的 `bench_tick/bench_stop/bench_receive` | 分别 `(bench_policy *state,now,bool stop_held)`／`(state,now)`／`(state,now,stop_held,const unsigned char *bytes,size_t count)` | void；原地更新 armed/active/deadline 等状态，由各自主循环写 GPIO／PWM |

`cybertrack_state.h` 中的 `CyberTrackAudioState::Call(stop,now,device_id,boot_id)` 返回 ct2 只读 JSON，是保留的历史适配及测试对象；ct6 起实际使用 `cybertrack_tools.cc` 的共享动作状态，不能用 ct2 结构解析当前回执。

## 串口与板级接口

以下是已实现的入口清单，不是自动执行脚本。各工程独立烧录，同一 GPIO 编号在不同板／镜像上的用途不同。

| 工程 | 输入 | 输出／动作 |
|---|---|---|
| 无负载检查 | BOOT 按下／释放 | 逻辑 FAULT/stopped 与串口检查结果；释放不恢复，无执行器输出 |
| L298N 电机台架 `0.3.2` | 单独 `1`／`2`／`3` 选 A／B／AB，另发 `a` 后单独 `f`／`r`；AB 可用 `x`／`y` 请求两种反向组合；`s` 同停 | 默认 NONE；选择撤销使能，窗口 3000 ms，单次 10000 ms，冷却 3000 ms 且轴停稳；A=GPIO4／5／6，B=GPIO7／8／9，两路 PWM 共用 1 kHz、8 bit duty=154；关闭时六脚为低，状态包含 target |
| MOS 台架 | 串口单字符 `a`，随后单独 `g`；`s` 停止 | 使能窗口 3000 ms；GPIO4 单次高电平 5000 ms；`MOS` 文本状态 |
| 联网板 | 私有串口配网；`status`／`stop`／`water`／`s` | 前三者向平台发送固定联调文本，water 同时创建本地许可；s 直接本地停止；`LINX RPC`／`WATER_OFF` 等诊断 |
| 当前面包板 ct21 | 原唤醒／说话／音量按键、八个 MCP 工具、网页、BOOT | GPIO8–13 双路 L298N、GPIO18 水枪、GPIO17 泡泡与 GPIO21 点火低压控制；串口 `CT_AUDIO` 结果与关闭记录，不提供上述 a/g/f/r 调试命令 |

电机台架六路 GPIO 只适用于原 N16R8 台架板，不套用面包板接线；ENA／ENB 跳帽及两路控制按[接线说明](esp32-motor-bench/README.md)连接，空闲时两路保持禁用。

两套单字符台架均忽略 CR/LF，批量多键、未知键、运行中收到键会停止／撤销使能；不能把多字符连发当作一次可靠动作请求。BOOT 是 GPIO0 软件停止输入，不等于独立断电开关。面包板 GPIO4 已用于麦克风，不能套用其他板的 GPIO4 水枪接线。

## 验证与维护

本文依据当前源码、公开头文件、工程 README 与已有实测记录整理，没有在本次文档更新中连接设备、烧录或触发动作，也没有重新执行历史测试。

| 需要核对的内容 | 证据入口 |
|---|---|
| 通用核心／协议／运行层／存储模拟 | [主机测试记录](tests/README.md)及 `tests/verification.json` |
| 无负载启动／PSRAM／BOOT | [实物检查](../hardware/components/ESP32-S3-N16R8/physical-verification.md)、[停止检查](../hardware/components/ESP32-S3-N16R8/boot-stop-verification.md) |
| 电机与 MOS 台架 | [电机记录](../docs/motor-bench.md)、[MOS 记录](../docs/mos-bench.md) |
| 联网绑定、工具与单次授权喷水 | [灵矽实测](../docs/linx-validation.md) |
| 音频、屏幕、状态／停止 | [面包板实测](../docs/audio-board-validation.md) |
| ct4 带载与 ct5 功率断开的时长验证 | [面包板喷水记录](../docs/audio-water-validation.md)；两类证据不得互相替代 |
| ct7 并发与 ct10 手机／语音分项 | [ct7 台架](../docs/concurrent-actions.md)、[ct10 无负载联调](../docs/lan-control.md#ct10-首轮手机与语音联调) |
| ct21 软件、部署与四方向反馈 | [软件报告](esp32-audio/verification-ct21.json)、[部署记录](esp32-audio/startup-ct21.json)；部署检查与后续用户实测分开记录 |
| 当前样机与剩余整机验收 | [制作及运行影像](../artifact/README.md)、[验证计划](../docs/verification-plan.md)；旧电源、60% PWM 及影像不作为当前辰克电池和 80% PWM 的完整验收 |

通用核心完整板级运行层、真实动作认证源、持久化与锚点后端、尚未实现的传感器集成，以及整机独立切断、失电／欠压／看门狗故障注入、定量停止距离、电流／温升与完整组合负载验收仍按 [TODO](../TODO.md) 和[固件计划](PLAN.md)推进；不在本文另建一份完成清单。

新增／修改工具、字段、范围、错误值、引脚或版本时，同步本文对应工程、该工程 README 及必要专题契约；新增实测只更新对应证据范围。部署版本与源码不一致时，先核对设备版本，不以本文推断设备已更新。


ct6 软件验证及部署边界见[集成记录](../docs/breadboard-integration.md)和[软件报告](esp32-audio/verification-ct6.json)。

## 面包板 ct11 长按计时

**历史记录。** 在 ct10 双入口规则上增加网页长按秒数，每 0.1 秒刷新，松开后保留本次时长，取消／后台／失联结束计时。仅为浏览器输入时长，不是输出或机械移动测量；后端规则保持。见[当前说明](../docs/lan-control.md)。

## 面包板 ct10 独立操作与双入口

**历史版本 `2.0.3-ct10`** 页面自动连接、取消组合开关，行走和喷水可独立开始并同时运行。网页连接本身不阻止语音；同通道网页动作优先，先取消冲突语音动作并保留冷却，不补做旧请求。网页关闭／超时只停止网页来源通道，语音关闭只停止语音来源通道；全部停止／BOOT／Wi-Fi 断开仍停止两路。状态增加 `move_source`、`water_source` 和 `control_owner=shared`；后者只表示入口连接。契约与部署见[局域网控制](../docs/lan-control.md)。以下 ct9／ct8 描述为历史版本。

## 面包板 ct9 按住行走

历史源码 `2.0.3-ct9` 按用户要求取消配对码，打开网页可直接连接接管；将网页方向键改为按下开始、同方向持续续租、松开仅停行走；喷水仍定时，组合请求只在按下时启动一次喷水。设备 600 ms 行走截止，浏览器约每 150 ms 用单次回执凭据续租；状态心跳不能维持行走，停止／超时后旧续租不能恢复。后台、Wi-Fi 断开及全停关闭两路。语音原三秒上限与冷却保持。新操作 `drive_start/drive_renew/drive_stop`、字段及验证见[当前局域网契约](../docs/lan-control.md)。已烧录并同步平台，实机无负载 HTTP／桌面长按通过；手机、语音和带载验收以部署记录为准。下方 ct8 定时方向键为历史软件候选。

## 面包板 ct8 局域网接口

历史候选 `2.0.3-ct8` 在 ct7 基础上提供 `http://<设备 IP>:8080/`。网页单控制者，8 位启动配对码换取内存令牌，500 ms 状态刷新兼心跳，设备端 2000 ms 租约及 1500 ms 一次动作窗口。完整 HTTP 路由、参数、错误与来源切换见[局域网接口契约](../docs/lan-control.md)。ct8 当时没有烧录或平台同步，后续已迭代部署至 ct21。

原五个语音工具与参数保留；网页接管时拒绝语音动作，语音状态／全停和正常对话保留。关闭语音会话只撤销语音动作，Wi-Fi 断开／BOOT／全停关闭全部动作。新增状态字段 `control_owner`（web/voice/none）、`window`、`move_cooldown_ms`、`water_cooldown_ms`、`boot_held`；配对码和令牌不会出现在语音回执。这里的控制权不代表传感反馈。原 ct7 行走／喷水时限、独立截止和冷却不变。

### ct12 操作间隔（2026-10-25）

历史变更，200 ms 规则在当前面包板继续沿用。

面包板行走和喷水自然截止或停止后，分别等待 200 ms；重复停止不延长间隔。API 字段不变，网页短间隔自适应查询，语音描述同步。独立水枪固件策略不变。测试与部署见 `esp32-audio/verification-ct12.json`、`esp32-audio/startup-ct12.json`。

<a id="ct13-泡泡与点火候选未部署"></a>

## ct13 泡泡与点火历史部署

ct13 当时新增 `self.tank.bubbles`、`self.tank.ignition` 以及对应 HTTP 操作，整数 `duration_ms` 1–5000。四路独立并行与全停，泡泡 GPIO17、双点火共用 GPIO21 为候选。状态能力与每路计时／来源／间隔均已扩展，详见[效果控制](../docs/effects-control.md)。ct13 已完成仅应用刷写与平台同步，见[部署记录](esp32-audio/startup-ct13.json)；当时无负载检查不证明泡泡或点火带载通过。泡泡上限随后由 ct14 改为 30 秒，点火间隔由 ct17 改为等实际软件 ON 时长；高压接线与安全验收仍未完成。

## ct14 持续喷水／泡泡

历史版本变更，已部署并取得无负载 HTTP 长按／失租检查；见[ct14 部署](esp32-audio/startup-ct14.json)。以下固定三秒点火间隔是当时规则，已被 ct17 替代。

新增网页 `water_start/renew/stop` 与 `bubbles_start/renew/stop`，每路独立 600 ms 租期、一次一回执续租，松开本路停止，可与行走长按及定时点火并行。页面每路 1／3／5／10／30 秒和按住持续共六个按钮。泡泡 MCP／HTTP 定时范围扩大为 1–30000 ms；点火上限 5000 ms、间隔 3000 ms 不变，无点火持续接口。新能力与状态字段见[接口说明](../docs/lan-control.md#ct14-喷水泡泡六按钮与长按)。

### ct17 网页狂暴模式

历史版本变更，已部署；当时未启动执行器，见[ct17 记录](esp32-audio/startup-ct17.json)。

`ControlSessions::FrenzyStart` 接收一次有序窗口请求，`AudioActionGuard::Frenzy` 检查四路后原子启动有界组合；总时长 1–30000 ms，网页预设 5／10／30 秒，左转／喷水／泡泡持续，点火脉冲最多 1000 ms、关闭后等长间隔。模式状态和停止由原会话及故障路径管理；ct17 当时不新增 MCP 启动工具，ct18 随后增加语音入口。普通点火也改为等实际软件 ON 时长间隔；原固定 3000 ms 为历史。协议与证据见[局域网控制](../docs/lan-control.md#ct17-狂暴模式)。

### ct18 语音狂暴模式

历史版本变更，已部署；该次检查启动次数为零，真人口述狂暴及完整带载验证仍未完成，见[ct18 记录](esp32-audio/startup-ct18.json)。

新增 MCP `self.tank.frenzy`：仅 `duration_ms` 整数 1–30000，描述规定未指定时长为 5000。`AudioActionGuard::VoiceFrenzy` 消费绑定模式的内部票据；`ControlSessions::VoiceFrenzy` 建立语音来源和固定截止，复用与网页相同的脉冲调度。回执新增 `frenzy_source`、`frenzy_last_duration_ms`。状态和停止工具覆盖模式，普通动作不隐式升级为狂暴模式。
