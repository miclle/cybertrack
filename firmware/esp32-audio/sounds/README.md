# 本地距离提醒

这两段为固定文本的语音合成资源，不是用户录音。2026-10-29 使用本机 macOS `say` 的 Tingting 音色、速率 210 生成，再用 FFmpeg 编码为单声道 16 kHz、20 kbit/s、60 ms 帧长的 Ogg Opus。云端角色音色保持原设置。

| 文件 | 文本 |
|---|---|
| proximity-caution.ogg | 前方不足五十厘米，请注意。 |
| proximity-stop.ogg | 前方太近，停止前进。 |

`apply_overlay.py` 从这些资源生成只读数组，使用现有 Opus 解码／扬声器路径。`audio_overlay.py` 加入本地声音优先处理；`tests/run_audio_tests.py` 从导出源码提取实际方法验证云端包隔离、解码重置保护、完整排空及恢复。
