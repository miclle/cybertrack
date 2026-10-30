# 固件能力与接口手册

当前参数核对于 2026-10-31；版本与部署依据见 [current.json](current.json) 和[当前状态](../docs/current-status.md)。现用工程为 `esp32-audio/`，源码候选为 `2.0.3-ct43`，最近记录部署仍为 `2.0.3-ct42`。历史核心、台架、逐版本接口与证据保留于[历史手册](CAPABILITIES-history.md)，不同工程同名工具不能混用。

<a id="当前面包板-ct21-接口"></a>
<a id="当前面包板-ct22-接口"></a>

## 当前面包板接口

工具名均带 `self.tank.` 前缀，支持上游规范化的 `self_tank_` 名称。`duration_ms` 为整数毫秒。动作参数严格校验，失败不排队补做；固件限制不能由提示词覆盖。

| 工具 | 参数与行为 |
|---|---|
| `get_status` | `{}`，最新逻辑状态、距离及驱动诊断；不启动动作 |
| `stop` | `{}`，立即取消四路、序列和模式，作废旧票据；不关闭语音或屏幕 |
| `move` | `direction` 四方向、`duration_ms` 1–2147483647，可选 `speed_percent` 60–100，默认 100 |
| `water` | `duration_ms` 1–30000，独立定时喷水 |
| `bubbles` | `duration_ms` 1–30000，独立定时泡泡 |
| `ignition` | `duration_ms` 1–5000，仅低压 MOS 控制；不代表高压验收 |
| `move_and_water` | `direction`、`move_duration_ms`、`water_duration_ms`，可选速度；两路均就绪才整体接受，各自截止 |
| `sequence` | `steps_json`，1–16 步 JSON 数组字符串；每步 `direction/move_ms/water_ms/bubbles_ms/ignition_ms`，可选速度；不用通道填 0，无行走填 `none` |
| `frenzy` | `duration_ms` 1–30000；四路均就绪才启动，间歇点火受自身关闭间隔约束 |
| `adjust_speed` | 运行中相对调速，具体字段与来源规则见[速度接口](../docs/speed-control.md)；不启动或续时 |
| `set_speed` | 运行中绝对目标 60–100%，具体字段见[速度接口](../docs/speed-control.md)；不自动换向或续时 |

语音未说时长时：全速左右转 880 ms，其他普通动作 1000 ms，狂暴 5000 ms。显式／同一步共享时长优先；否定、查询、引用和含糊表达不套用默认启动。规则唯一维护源为 [role-prompt.txt](esp32-audio/role-prompt.txt)。

序列整单校验、步骤内多路并发、各路独立截止；全步结束并满足冷却才进入下一步。行走／喷水／泡泡关闭间隔 200 ms，点火至少等本次实际软件 ON 时长。停止、来源失效、Wi-Fi 断开、故障或网页抢占取消待执行步骤，恢复后不补做。详细见[序列契约](../docs/action-sequences.md)。

## 状态与事实边界

- 动作必须检查内部 `result=accepted`；查询／停止为 `result=ok`。工具传输成功不代表动作接受；接受也不代表物理效果。
- `logical_outputs.left/right` 为有符号 PWM 百分比，范围 −100..100（非零最小绝对值 60）；其他三路为布尔值。无轮速、水流、火花、电量或液位反馈，`physical_feedback=false`。
- 序列通过 `sequence_active/step/steps/result` 报告；`waiting` 是步骤间等待，不能说全部完成。故障、忙碌、冷却、取消或过期均不自动重试。
- 距离只在 `distance.valid=true`、`error=none`、`age_ms<=500` 时可用，无效为 null。前向距离不是移动里程或道路畅通证明。
- 距离不足 50 cm 滴声；40–50 cm 每 800 ms，小于 40 cm 每 400 ms，与行走和保护开关独立。
- `proximity.auto_avoidance_enabled` 默认 false，仅网页切换，网页与语音共用。开启时小于 15 cm 停前进／至少 20 cm 解锁，需新指令；无效读数不解除已有锁定。`capabilities.auto_avoidance=false` 表示无自动绕行。

ct43 候选新增 `recent_command`，保留进入动作适配器的最近一次请求结果，查询不覆盖。它不是最后停机原因；字段、未捕获范围与只读解释见[状态解释](../docs/status-explanation.md)。

## 网页与停止

使用 `http://<设备 IP>:8080/`。单网页会话、POST JSON、同源校验及短期窗口；会话令牌不是用户身份认证。行走／喷水／泡泡长按租约 600 ms。状态轮询不能代替续租，断线重连只恢复状态。

同通道网页优先，语音不能覆盖网页动作；不同空闲通道可以并用。关闭网页只取消网页来源动作；云端通道关闭只取消语音来源动作。BOOT、统一停止、Wi-Fi 断开及输出故障关闭四路。详情见[局域网契约](../docs/lan-control.md)。

## 验证

[ct43 候选记录](esp32-audio/verification-ct43.json)覆盖本次软件检查与编译；[部署记录](esp32-audio/startup-ct42.json)记录平台回读与零执行器启动检查。新一次检查须记录自己的源码与结果，不能复用历史记录宣称新候选通过。

新产品计划见[执行计划](../docs/improvement-plan.md)。实机停车距离、定量电气／温升、完整语音与组合负载验收仍未完成。
