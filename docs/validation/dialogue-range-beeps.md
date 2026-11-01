# 对话期间的普通测距提示

2026-11-01 用户实机报告 ESP32-S3 语音卡顿，同时有测距滴声；关闭控制页、减少滴声后，用户反馈播报已不卡顿，但前方空旷仍偶发滴声。用户随后明确选择：**对话期间暂缓普通滴声，结束后按实时距离恢复；前进停车及其紧急告警保持即时优先。**

## 原因与修正范围

ct73 的普通 Beep 和紧急 Stop 都调用 `PlaySound(..., true)`，后者清空解码／播放队列、重置 Opus 解码器，提示期间拒收云端音频。代码证明存在语音截断机制；现场滴声与卡顿同时出现、减少滴声后改善支持该方向，尚无同步音频／网络包或声学量测证明所有卡顿都来自它。

ct74 候选将普通滴声改成独立 PCM 通知：

- 非 idle 状态（包括连接、监听与播报）禁止普通通知；转入对话撤掉队列中未播放的普通通知，不补播。
- 只有语音解码／播放队列为空且没有正在解码／播放的帧，才允许入队；PCM 在互斥锁外准备，入队前再次核对，覆盖状态切换竞态。
- 收到新的普通语音／声音包时，只移除尚未出队的测距 PCM，语音包原样接受；普通通知不进入云端 Opus 解码器、不设置抢占标志，也不清空语音。
- 普通音色沿用 1400 Hz、80 ms、0.18 振幅、5 ms 淡入淡出，在 codec 输出采样率合成并拆成 20 ms PCM 块。已交给 codec／DMA 的声音无法靠删软件队列收回；分块不是实测切换或停车时延上限。
- 紧急 Stop 保持原抢占解码路径。距离阈值、普通提示节奏、前进保护、BOOT、动作输出、十二项工具及角色源均未改变。

[合同核对](evidence/ct74-dialogue-beeps/contract-check.json)比较 ct73／ct74 的 `action_outputs.h`、`control_sessions.h`、`proximity_guard.h` 摘要一致。用户对普通滴声的最新选择取代此前“不区分对话状态也提示”的默认行为；与行走／避障开关独立的距离规则继续保留。

## 验证与当前状态

[构建记录](../../firmware/esp32-audio/verification-ct74.json)为完整 ESP-IDF 5.5.1 构建，应用 2,721,328 字节，SHA-256 `28606ac3c771ca650faf4297d9353e86c05bd2efdc50e2b285df5817d8522cb5`。候选源码 ct74，最近实际部署 ct73；尚未刷入或完成新版本听感验收。

[最终音频原生检查](evidence/ct74-dialogue-beeps/native-final.txt)执行导出的方法，ASan／UBSan 覆盖五种采样率波形、空闲入队、对话边沿取消、原样保留语音包、活跃帧／关键告警阻止普通通知，以及普通提示暂缓后不补播、仅新事件恢复；关键告警在普通提示被抑制时仍可播放。重跑：

```sh
python3 firmware/esp32-audio/tests/run_audio_tests.py --source build/xiaozhi-ct74-src
python3 scripts/verify_improvements.py --source build/xiaozhi-ct74-src
```

最终十八组统一检查全部通过，含 124 项 Python 测试，见[独立报告](evidence/ct74-dialogue-beeps/software-checks.json)。[初轮失败](evidence/ct74-dialogue-beeps/initial-failure.json)是参考包漏列当前构建记录，三项打包测试报错；[原始失败报告](evidence/ct74-dialogue-beeps/software-checks-initial.json)保留，不隐去失败。

另一次[独立十二秒测距采样](evidence/ct74-dialogue-beeps/range-snapshot-08.json)有 35 条样本、33 条有效，823–1779 mm，没有捕获到低于 500 mm 的值。它未与实际滴声或标尺同步，不能据此判定传感器准确、复现或解决空旷偶发滴声；安装、声学反射与读数稳定性仍待独立采集。

## 部署后的现场退出条件

在执行器功率断开的条件下，仅应用更新与配置保持检查通过后，再由现场确认：监听和播报无普通滴声截断；结束后只有当前有效近距读数才恢复普通提示、没有旧提示补播；远处／无效读数不播旧提示。前进停车与紧急告警的逻辑、真实输出及机械效果分别验证。新听感、假回波及完整停止矩阵没有被构建或原生检查替代。
