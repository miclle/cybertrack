# 头部超声波测距与前进保护

## 距离提示音

普通滴声需要连续 3 个不同采样时刻的有效读数都小于 50 cm 后才允许播放；正常约 100 ms 采样时，从首个近距样本到确认约 200 ms，不是实测扬声器延迟。达到 50 cm、无效、未采样或过期立即撤销普通提示资格；相邻采样时刻倒退或间隔超过 500 ms 时从首个样本重新确认。相同快照的 5 ms 控制循环不重复计数。

确认后沿用 40–50 cm 每 800 ms、小于 40 cm 每 400 ms 的节奏；重新确认不重置已有节拍，不补播。监听与回复期间暂缓普通滴声。避障继续直接使用原始新鲜读数，不等待三个样本；不足 15 cm 停前进、至少 20 cm 解锁不续走，停车三连音保持优先。网页／语音仍报告原始测距。

用户在 ct77 试听后确认偶发滴声明显减少。结束恢复、移远不补播、再次靠近三项仍待现场复核。[部署记录](../firmware/esp32-audio/startup-ct77.json) · [听感记录](validation/ct74-deployment.md)

## 自动避障开关

网页速度滑块下方可切换“自动避障”。每次开机默认关闭，不写入 NVS；浏览器刷新、释放、重连及语音／Wi-Fi 断线不会重置本次开机的设置。停止、BOOT、动作到期和断线停止仍生效。

- 关闭：距离读数不停止或锁定前进；已有距离锁定清除，已停止动作、旧长按和取消的序列不恢复。测距显示和查询保持。
- 开启：严格小于 150 mm 停止并锁定前进，至少 200 mm 解锁；无效／过期样本不解锁。开启时已有新鲜近距离读数，会在同一请求回执前执行保护并撤销前进输出。后退／转向及独立效果保持原规则。
- 状态由设备端统一维护，网页长按、语音 `move`／`move_and_water` 及 `sequence` 共用；不存在独立语音开关。语音仅查询或遵循设置，修改开关在网页完成。
- HTTP `POST /api/action` 使用 `{"operation":"set_auto_avoidance","sequence":1,"window":1,"enabled":true}`，字段恰好四个，`enabled` 必须为 JSON 布尔值；沿用会话认证、一次性序号与状态窗口。回执 `proximity.auto_avoidance_enabled` 表示当前设置，`forward_blocked` 表示实际锁定。`capabilities.forward_protection=true` 表示支持此能力；历史 `capabilities.auto_avoidance=false` 仍表示不支持自动绕行，不是开关值。

## 接线与证据范围

| HC-SR04 端 | 面包板端 | 设计用途 |
|---|---|---|
| VCC | 3V3 | 使用主控侧稳压 3.3 V，不接 5Vin、12 V 或效果 MOS 输出 |
| GND | GND | 主控共地 |
| TRIG | IO1 | 输出，初始化先置低，单次约 12 µs 高脉冲 |
| ECHO | IO2 | 输入，内部下拉；本轮按用户指定直连方案实现 |

这是已选的软件接入方案，不是实物接线或电平验收。GPIO 数字不是排针序号；按实物丝印核对。四根线在头部内连接，不增加头部至底盘信号线。主控侧 3V3 余量、实物针序、TRIG 阈值、ECHO 峰值、失电状态和装壳声学仍待核实；不要保留 ECHO 直连而将模块改成 5 V 供电。现行连接见[原理图](../hardware/schematic/README.md)。图纸和 ERC／网表检查不替代上述实物电平与接线验收。

[商品页](https://item.jd.com/10229075026760.html)选项为单芯片宽电压 3–5.5 V，参数图写 3.3–5 V，背面接线图却为多芯片／5 V；2026-10-28 已重新读取。页面没有明确该版本 ECHO 在 3.3 V 供电下的高电平幅值。供电范围是商家规格，3.3 V 直连为本次实施选择，均不能替代波形或对应版本电路证据。已有[原图归档与冲突记录](../hardware/procurement-web-review.md#p04--h19hc-sr04-单芯片宽电压模块)保持。

机械仍沿用[向上接头与托盘让位候选](assembly.md#头舱与穿线)，实际固定、针座与线束需核对。

## 采集与故障处理

- 独立 FreeRTOS 任务，优先级 2；不持有动作控制锁，不在优先级 10 的 BOOT／停止任务中等待回波。
- ESP-IDF 5.5.1 RMT RX 使用 1 MHz 时基、48 符号缓冲，过滤小于 2 µs 的毛刺；电平持续 25 ms 时结束接收。参考[官方 RMT 接口](https://docs.espressif.com/projects/esp-idf/en/v5.5.1/esp32s3/api-reference/peripherals/rmt.html)。没有新增外部驱动依赖。
- 初始化后等待 100 ms；采集周期目标约 100 ms，相邻触发至少间隔 100 ms，不因调度延迟补发密集脉冲。TRIG 脉冲由 GPIO 和 12 µs 短延时生成，实际脉宽及停止响应仍需设备波形验证。
- 接收完成最多等待 80 ms，覆盖回波及尾部低电平的结束判定。没有回波通常由 RMT 空闲结束报告；驱动没有按时完成则报告 `driver_error` 并进入测距驱动恢复流程，不会重启主控或锁死动作通道。
- 只接受一个连续高脉冲；多脉冲、缓冲填满、超过 10 ms 才到达的回波均判异常。采样前或结束时 ECHO 为高，报告 `echo_high`。未接模块与没有反射物不能仅凭超时区分。
- 使用名义声速 343 m/s：`distance_mm = round(echo_us × 343 / 2000)`。有效范围候选为 20–4000 mm，未做温度补偿或实物标定。毫米是传输单位，不宣称毫米精度或实物完整覆盖 4 m。
- 每次失败立即覆盖上一读数。超过 500 ms 的样本失效；不保留旧距离冒充实时值，不将无回波解释为无障碍。时间戳取 TRIG 脉冲结束的单调时钟。

驱动、解码与状态序列化分别在 [ultrasonic.cc](../firmware/esp32-audio/ultrasonic.cc) 和 [distance_reading.h](../firmware/esp32-audio/distance_reading.h)。

冷上电曾出现测距持续无读数、复位后恢复。现场复测应分别记录供电方式、首个有效样本、驱动错误和恢复情况。[故障采集](../firmware/esp32-audio/cold-start-failure-ct33.json) · [恢复复测](../firmware/esp32-audio/cold-start-ct34.json)

## 网页与语音接口

网页以整数厘米显示距离，无效或过期时显示 `-`。语音通过 `self.tank.get_status` 查询同一份快照。

| `distance.error` | 含义 |
|---|---|
| `none` | 本次回波在候选量程内且样本新鲜 |
| `not_ready` | 尚未得到首次采样 |
| `no_echo` | 没有有效高脉冲，不代表前方畅通 |
| `echo_high` | 触发前或完成后 ECHO 仍为高 |
| `invalid_echo` | 多脉冲、迟到回波或缓冲溢满 |
| `out_of_range` | 回波宽度对应距离不在 20–4000 mm |
| `driver_error` | 任务、GPIO、RMT 初始化／运行或完成等待失败 |
| `stale` | 样本超过 500 ms 或时钟顺序不合法 |

无效时 `valid=false`、`distance_mm=null`；尚无采样时 `sampled_at_ms`、`age_ms` 和 `echo_us` 为 null。`echo_us` 在收到异常宽度时可保留用于诊断，不能当有效距离。`sampled_at_ms` 为本次尝试时间，不是“上一次成功”的时间。
