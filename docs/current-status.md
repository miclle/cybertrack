# CyberTrack 当前状态

| 项目 | 最近可核对的记录 |
|---|---|
| v2 硬件 | 单一量产主 PCB，A2 工程接入右前脸 Seeed 114993115、双电源与 DVP 转换。首板电气、同批 FPC 接触及整机预览待验。[主板](../hardware/pcb/README.md) · [摄像头](../hardware/model/studies/front-camera/README.md) |
| 固件候选 | **2.0.3-ct80** 提供 A1 主板和旧面包板两种构建，A2 专用固件待开发。A1 通过硬件锁存处理 SW2 断开，避障保留待处理的后退和转向请求。应用尚待部署。[构建与回归记录](../firmware/esp32-audio/verification-ct80.json) |
| 旧版样机应用 | **2.0.3-ct78** 于 2026-11-03 仅更新应用。配置保持，两次启动联网、二十条输出全关的状态回读通过。[部署记录](validation/ct78-deployment.md) |
| 语音角色 | 仓库的 ct79 角色为 5002 字符，尚待同步。平台最近一次回读为 2026-11-01 恢复的旧 5991 字符角色。[角色源](../firmware/esp32-audio/role-prompt.txt) · [平台回读](validation/evidence/ct78-stop-duration/platform-restored.json) |
| CAD 与打印 | 清水瓶、泡泡液瓶直接放入背包。Lean 24 件、Ready 26 件，各六盘。CAD 已检查取瓶路径，实际抓握、行走稳定性和密封待验。[模型与切片入口](../hardware/model/README.md) |
| 电源 | 辰克 5 V 电池包供电，电机支路升压至 12 V。当前整机的持续负载、电流、温升和续航待测。[电源与预算](../hardware/architecture/README.md) |

## 现场与语音

- ct73 架空前进 500 ms，60% PWM 时两侧均未转动，100% 时两侧转动并停止。单次 BOOT 提前停止、松开后保持停止，以及一次真人语音左转，均有现场反馈。低占空比原因、地面停止距离和完整故障矩阵待测。[现场记录](validation/ct73-deployment.md)
- ct74 现场确认对话期间普通测距滴声暂缓，回复不卡。结束恢复、移远不补播和再次靠近三项当时跳过。ct77 加入连续三次近距采样确认后，用户反馈偶发滴声明显减少。[ct74 听感](validation/ct74-deployment.md) · [ct77 反馈](ultrasonic-ranging.md#距离提示音)
- ct78 角色用合成普通话经过平台识别和无输出主机复测，两轮定向集各 16/16，完整集 33/35。“快一点”漏调速，另一条识别丢失“先别执行”后主机接受前进。ct79 的本地合成输入回归未覆盖真人拾音、平台工具选择或扬声器听感。[ct78 失败样例](validation/ct78-stop-duration.md) · [当前待办](TODO.md)

## 统一软件检查

在仓库根目录运行 `python3 scripts/check_firmware_current.py`，可核对源码版本、角色哈希与记录中的应用身份。有本地镜像时可同时核对文件字节数与 SHA-256。

```sh
python3 scripts/check_firmware_current.py --board a1 \
  --source-bin build/firmware-ct80-a1/xiaozhi.bin \
  --deployed-bin build/firmware-ct78/xiaozhi.bin
```

当前默认核对 A1。核对旧设备的候选镜像时使用 `--board breadboard --source-bin build/firmware-ct80-breadboard/xiaozhi.bin`。`--deployed-bin` 始终与最近一次实机刷写记录比对。

准备好同版上游源码后，按[固件主机验证](validation/firmware-host.md)运行当前固件的退役请求、停止与恢复检查。

ct79 记录包含 9 个工具、28 个拒绝与停止案例，以及 13 类场景各 5 个触发时刻的停止回放。软件回执、输出关断和机械停止分别验收。[版本清单](../firmware/current.json) · [整机验收](verification-plan.md)
