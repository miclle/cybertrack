# 本地距离提示音

ct35 使用本地合成正弦提示音，不使用语音合成或用户录音。运行 `python3 firmware/esp32-audio/sounds/generate_range_tones.py` 可重新生成；需要带 libopus 的 FFmpeg。

| 文件 | 内容 |
|---|---|
| range-beep.ogg | 1400 Hz、80 ms 一声，末尾 40 ms 静音 |
| range-stop.ogg | 同样的短音三声，间隔 60 ms，末尾 60 ms 静音 |

原始波形为 16 kHz 单声道、幅值 0.18、两端 5 ms 淡入淡出，使用 20 kbit/s、60 ms 帧长的 Ogg Opus 编码；设备音量仍沿用用户设置。编码及现有解码路径会带来帧填充，实际听感待实机验证。

`apply_overlay.py` 只从以上两段资源生成固件只读数组，复用现有 Opus／扬声器路径。`audio_overlay.py` 保持本地优先处理；`tests/run_audio_tests.py` 从导出源码提取实际方法验证云端包隔离、解码重置保护、排空及恢复，并测试提示音工作任务的取消、优先级和过期丢弃。

`proximity-caution.ogg` 和 `proximity-stop.ogg` 是 ct33／ct34 的历史 Tingting 合成语音，保留供旧版本验证记录追溯；ct35 不嵌入或播放。
