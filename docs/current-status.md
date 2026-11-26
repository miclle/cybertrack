# CyberTrack 当前状态

| 项目 | 最近可核对的记录 |
|---|---|
| A2 前摄主板 | 工程已接入右前脸 Seeed 114993115、双电源与 DVP 转换。首板电气、同批 FPC 接触及整机预览待验。[主板](../hardware/pcb/README.md) · [摄像头](../hardware/model/studies/front-camera/README.md) |
| A3 运动反馈 | 已有独立 A3 原理图、PCB、计数 MCU 与 S3 首件采样程序、26 芯线束与五个 Ø14.5 mm 通道改件。头下壳已合入 A2 前摄安装座，光路与 Ø14 mm 通规均已做 CAD 检查。编码器电气核实、实物试装和整车闭环待验。[A3 工程](../hardware/pcb/motion-feedback/README.md) · [改件与检查记录](../hardware/model/studies/a3-harness/README.md) |
| 固件候选 | **2.0.3-ct82** 已分别构建 A4、A1 和旧面包板镜像。A4 使用双 DRV8874 硬件停机和 U12 方向回读，恢复许可后须接收新指令。A4 首板待测，A2／A3 专用整机镜像待开发。[构建与回归记录](../firmware/esp32-audio/verification-ct82.json) |
| 旧版样机应用 | **2.0.3-ct78** 于 2026-11-03 仅更新应用。配置保持，两次启动联网、二十条输出全关的状态回读通过。[部署记录](validation/ct78-deployment.md) |
| 语音角色 | 仓库的 ct79 角色为 5002 字符，尚待同步。平台最近一次回读为 2026-11-01 恢复的旧 5991 字符角色。[角色源](../firmware/esp32-audio/role-prompt.txt) · [平台回读](validation/evidence/ct78-stop-duration/platform-restored.json) |
| CAD 与打印 | 整机已装入 A1 STEP、四柱托架及左右各一只常规喇叭。Lean 21 件、Ready 20 件，各六盘。4 Ω 带载表现与闭盖声像待验。清水瓶、泡泡液瓶直接放入背包。CAD 已检查取瓶路径，实际抓握、行走稳定性和密封待验。[模型与切片入口](../hardware/model/README.md) |
| 电源 | A1–A3 的 J8 为 5 V 输入，板上升至 12 V 驱动电机。A4 采用 4S 成品包、三路降压和双 H 桥，布线已完成，原生 DRC 通过，已导出工程样板文件。BTO US1202 已做包络试配，电池定型及双履带带载零复位待首件验证。[A4 主板](../hardware/pcb/power-revision/README.md)。[供电改版](../hardware/architecture/v2-power.md) |

## 现场与语音

- ct73 架空前进 500 ms，60% PWM 时两侧均未转动，100% 时两侧转动并停止。单次 BOOT 提前停止、松开后保持停止，以及一次真人语音左转，均有现场反馈。低占空比原因、地面停止距离和完整故障矩阵待测。[现场记录](validation/ct73-deployment.md)
- ct74 现场确认对话期间普通测距滴声暂缓，回复不卡。结束恢复、移远不补播和再次靠近三项当时跳过。ct77 加入连续三次近距采样确认后，用户反馈偶发滴声明显减少。[ct74 听感](validation/ct74-deployment.md) · [ct77 反馈](ultrasonic-ranging.md#距离提示音)
- ct78 角色用合成普通话经过平台识别和无输出主机复测，两轮定向集各 16/16，完整集 33/35。“快一点”漏调速，另一条识别丢失“先别执行”后主机接受前进。ct79 的本地合成输入回归未覆盖真人拾音、平台工具选择或扬声器听感。[ct78 失败样例](validation/ct78-stop-duration.md) · [当前待办](TODO.md)

## 统一软件检查

在仓库根目录运行 `python3 scripts/check_firmware_current.py`，可核对源码版本、角色哈希与记录中的应用身份。有本地镜像时可同时核对文件字节数与 SHA-256。

```sh
python3 scripts/check_firmware_current.py --board a4 \
  --source-bin build/firmware-ct82-a4/xiaozhi.bin \
  --deployed-bin build/firmware-ct78/xiaozhi.bin
```

当前默认核对 A1。核对旧设备的候选镜像时使用 `--board breadboard --source-bin build/firmware-ct82-breadboard/xiaozhi.bin`。`--deployed-bin` 始终与最近一次实机刷写记录比对。

准备好同版上游源码后，按[固件主机验证](validation/firmware-host.md)运行当前固件的退役请求、停止与恢复检查。

ct79 记录包含 9 个工具、28 个拒绝与停止案例，以及 13 类场景各 5 个触发时刻的停止回放。软件回执、输出关断和机械停止分别验收。[版本清单](../firmware/current.json) · [整机验收](verification-plan.md)
