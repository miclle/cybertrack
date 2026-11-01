# 固件能力与接口手册

当前参数核对于 2026-11-01；版本与部署依据见 [current.json](current.json) 和[当前状态](../docs/current-status.md)。现用工程为 `esp32-audio/`，源码及最近记录部署均为 [ct77](esp32-audio/verification-ct77.json)；仅应用写入、配置保持、两次启动与二十条零输出回读见 [startup-ct77.json](esp32-audio/startup-ct77.json)，用户已确认偶发滴声明显减少、效果可以。历史核心、台架、逐版本接口与证据保留于[历史手册](CAPABILITIES-history.md)，不同工程同名工具不能混用。

ct76 [分句改稿门禁](../docs/validation/draft-clause-duration.md)不再借用其他分句的量化值解除相对改稿澄清；明确的紧邻时长补充保留，停止入口与工具参数不变。未部署，不作为完整自然语言归属验证。

ct75 在 HTTP JSON 解析前拒绝原始零字节与实际 Unicode 零转义，避免非法操作名、方向或键名被截断为合法前缀；合法查询／停止保留。[证据与边界](../docs/validation/http-zero-admission.md)，已完成[部署及无动作 HTTP 检查](../docs/validation/ct75-deployment.md)，物理及未测分支独立验收。

ct62 候选新增[单次识别失败隔离](../docs/validation/voice-input-guard.md)：同轮失败后拒绝动作、调速与改稿，查询和全停保留，新输入恢复。内部代际不可由调用者传入，公开工具参数不变；已随 ct73 部署，现场时序与停止另验。

ct63 候选扩展[组合／序列及目标速度的播放匹配](../docs/validation/plan-feedback.md)，只有完整原话、参数和成功回执匹配才抑制确认；动作控制协议与角色源不变，已随 ct73 部署，扬声器听感另验。

ct74 [对话提示](../docs/validation/dialogue-range-beeps.md)只在空闲播放普通测距提示，监听／播报暂缓，结束只按实时读数恢复；普通 PCM 不截断云端语音，紧急停车告警仍优先。已完成仅应用部署与无动作检查，首轮用户确认对话中提示暂缓且回复不卡；结束恢复、移远不补播及再次靠近三项由用户选择跳过，未验收。

<a id="当前面包板-ct21-接口"></a>
<a id="当前面包板-ct22-接口"></a>

## 当前面包板接口

工具名均带 `self.tank.` 前缀，支持上游规范化的 `self_tank_` 名称。`duration_ms` 为整数毫秒。动作参数严格校验，失败不排队补做；固件限制不能由提示词覆盖。

| 工具 | 参数与行为 |
|---|---|
| `get_status` | `{}`，最新逻辑状态、距离及驱动诊断；不启动动作 |
| `compose` | ct44 引入，只保存／修改／取消版本化表演草稿；不执行，详见[编排契约](../docs/show-composer.md) |
| `stop` | `{}`，立即取消四路、序列和模式，作废旧票据；不关闭语音或屏幕 |
| `move` | `direction` 四方向、`duration_ms` 1–2147483647，可选 `speed_percent` 60–100，默认 100 |
| `water` | `duration_ms` 1–30000，独立定时喷水 |
| `bubbles` | `duration_ms` 1–30000，独立定时泡泡 |
| `ignition` | `duration_ms` 1–5000，仅低压 MOS 控制；不代表高压验收 |
| `move_and_water` | `direction`、`move_duration_ms`、`water_duration_ms`，可选速度；两路均就绪才整体接受，各自截止 |
| `sequence` | `steps_json`，1–16 步 JSON 数组字符串；每步 `direction/move_ms/water_ms/bubbles_ms/ignition_ms`，可选速度；不用通道填 0，无行走填 `none` |
| `frenzy` | `duration_ms` 1–30000；四路均就绪才启动，间歇点火受自身关闭间隔约束 |
| `adjust_speed` | 运行中相对调速，具体字段与来源规则见[速度接口](../docs/action-sequences.md#速度与时长)；不启动或续时 |
| `set_speed` | 运行中绝对目标 60–100%，具体字段见[速度接口](../docs/action-sequences.md#速度与时长)；不自动换向或续时 |

语音未说时长时：全速左右转 880 ms，其他普通动作 1000 ms，狂暴 5000 ms。显式／同一步共享时长优先；否定、查询、引用和含糊表达不套用默认启动。规则唯一维护源为 [role-prompt.txt](esp32-audio/role-prompt.txt)。

序列整单校验、步骤内多路并发、各路独立截止；全步结束并满足冷却才进入下一步。行走／喷水／泡泡关闭间隔 200 ms，点火至少等本次实际软件 ON 时长。停止、来源失效、Wi-Fi 断开、故障或网页抢占取消待执行步骤，恢复后不补做。详细见[序列契约](../docs/action-sequences.md)。

## 状态与事实边界

- 动作必须检查内部 `result=accepted`；查询／停止为 `result=ok`。工具传输成功不代表动作接受；接受也不代表物理效果。
- `logical_outputs.left/right` 为有符号 PWM 百分比，范围 −100..100（非零最小绝对值 60）；其他三路为布尔值。无轮速、水流、火花、电量或液位反馈，`physical_feedback=false`。
- 序列通过 `sequence_active/step/steps/result` 报告；`waiting` 是步骤间等待，不能说全部完成。故障、忙碌、冷却、取消或过期均不自动重试。
- 距离只在 `distance.valid=true`、`error=none`、`age_ms<=500` 时可用，无效为 null。前向距离不是移动里程或道路畅通证明。
- 距离不足 50 cm 滴声；ct77 须连续 3 个不同有效近距样本才提示，远距／无效／过期或超过 500 ms 的采样间隔后重新确认。确认后 40–50 cm 每 800 ms，小于 40 cm 每 400 ms，与行走和保护开关独立，对话期间暂缓；避障停车不等待声音确认。[验证与部署边界](../docs/validation/range-beep-confirmation.md)
- `proximity.auto_avoidance_enabled` 默认 false，仅网页切换，网页与语音共用。开启时小于 15 cm 停前进／至少 20 cm 解锁，需新指令；无效读数不解除已有锁定。`capabilities.auto_avoidance=false` 表示无自动绕行。

ct43 引入 `recent_command`，保留进入动作适配器的最近一次请求结果，查询不覆盖。它不是最后停机原因；字段、未捕获范围与只读解释见[状态解释](../docs/status-explanation.md)。

## 网页与停止

ct45 已部署网页提供“小D 泡泡剧场”，本地模板和编辑不启动；保存后显示设备版本，再勾选核对并明确开始。并发修改、草稿过期、停止／断线及迟到回执使确认失效。三个模板只包含行走和泡泡，台词为亲子提示；细节与证据见[编排说明](../docs/show-composer.md)。

使用 `http://<设备 IP>:8080/`。单网页会话、POST JSON、同源校验及短期窗口；会话令牌不是用户身份认证。行走／喷水／泡泡长按租约 600 ms。状态轮询不能代替续租，断线重连只恢复状态。

同通道网页优先，语音不能覆盖网页动作；不同空闲通道可以并用。关闭网页只取消网页来源动作；云端通道关闭只取消语音来源动作。BOOT、统一停止、Wi-Fi 断开及输出故障关闭四路。详情见[局域网契约](../docs/lan-control.md)。

## 验证

[ct45 软件记录](esp32-audio/verification-ct45.json)与[部署记录](esp32-audio/startup-ct45.json)分别记录构建和设备检查；后续角色调整及隔离评测见[联调记录](../docs/validation/lingxi-ct45-role-feedback-20261031.md)。新一次检查须记录自己的源码与结果，不能复用历史记录宣称新候选通过。

新产品计划见[执行计划](../docs/improvement-plan.md)。实机停车距离、定量电气／温升、完整语音与组合负载验收仍未完成。

ct66 的[即时全停回执](../docs/validation/stop-dispatch.md)在严格校验后同步完成，不再二次排队；回执分配失败也先关闭输出。网页会话权限及旧动作／查询的输入代际隔离保留。未改变公开工具定义和角色，未部署。

ct67 增加[无量化相对改稿门禁](../docs/validation/relative-draft-duration.md)：可识别的相对长短请求没有量化片段时，拒绝本轮猜测修改和动作替代，返回澄清事实；新输入重新判断，查询／全停与可信网页保留。它不验证量化数值归属或任意自然语言，公开工具与角色未改，未部署。

ct68 增加[含糊动作门禁](../docs/validation/vague-action-admission.md)：本轮 STT 命中有限的泛化动作表达且未识别动作／方向词时，首次执行器或调速请求返回 `action_unspecified`，同轮补做隔离。仅编辑草稿的 compose 保留既有读版本与网页确认门槛；查询、全停和可信网页保留。不是完整意图、否定或引用解析；未部署。

ct70 在 WebSocket／MQTT／SDK 原始字符串入口拒绝会被 cJSON 截成合法前缀的机器人零字符请求；锁定本轮失败，保留合法停止与新输入恢复。十二项工具、字符串步骤和角色不变，未部署；[验证及范围](../docs/validation/mcp-raw-json.md)。

ct71 的[有限否定输入门禁](../docs/validation/negative-input-admission.md)返回 `input_negated` 与 `negation_facts`，拒绝受支持完整否定句的新写入，仅在完全空闲时保护草稿免受误调 stop 清除。活动／等待的全停、BOOT 与可信网页保留；真实停止先关输出再分配回执。未知表达和活动否定语义仍按原模型要求验收，未部署。

ct72 的[效果成功确认播放](../docs/validation/effect-alias-feedback.md)匹配既有别名与狂暴模式，核对本轮参数及通道独立时长；超限、拒绝、问句与未知表达保留音频。只影响播放，工具、执行器约束及最近部署 ct45 不变。

ct73 [四路组合播放](../docs/validation/four-lane-feedback.md)复用既有别名，核对每步四路参数及首步回执；未知、重复通道、含糊或超限保留音频，不改工具或动作守卫。新定向语音的两条模型／识别失败保留，候选未部署。
