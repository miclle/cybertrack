# 效果别名与模式的成功确认播放

ct72 补齐已有喷水、泡泡、点火别名与狂暴模式的成功确认匹配。它只控制远端音频是否进入播放，不创建动作、修改参数或放宽执行器限制。原十二项工具、5991 字符角色及平台参数未改，最近记录的部署仍为 ct45。

## 匹配范围

完整独立短句支持喷水／发射／开枪／射击、吹泡泡／开炮、点火／放电／闪电／护盾／打火／电击，以及角色已明确限定的“饭店”纠错短句；狂暴模式单独处理。允许一个“开启”前缀，省略时长或“一下”使用既定默认值：普通效果 1000 ms、狂暴模式 5000 ms。明确时长按原解析器转换，点火最多 5000 ms，其他上述效果最多 30000 ms。

“饭店吃饭”“去饭店”“附近饭店”、疑问、引用、否定、超限和未完整识别的表达不进入白名单。点火与其他动作的组合不在本次扩展范围。“停止点火／放电／射击／饭店”“关闭护盾”补入已有全停的播放匹配。

必须在本轮唯一工具及参数匹配后，收到操作相同、`result=accepted`、`fault=none` 的回执。各效果核对自己的 `water_last_duration_ms`、`bubbles_last_duration_ms`、`ignition_last_duration_ms` 或 `frenzy_last_duration_ms`，不能用其他并发通道可能支配的通用 `last_duration_ms` 代替。缺字段、拒绝、时长不符、先播报后回执、额外工具、新输入和迟到回执都保留音频。全停继续要求其已有的成功回执。

## 原始事件回放结果

复用 [ct71 完整语音回归](full-stt-ct71.md) 的全部 88 条实际 STT、工具回执与音频包事件，没有新增模型会话、录音或设备输出。

| 包级策略 | ct71 | ct72 |
|---|---:|---:|
| 抑制确认包 | 1021 | 1085 |
| 允许播放包 | 4659 | 4595 |
| 普通点火 V025–V027 允许播放 | 64 | 0 |
| 超限喷水 V020 允许播放 | 31 | 31 |
| 超限泡泡 V024 允许播放 | 34 | 34 |
| 超限点火 V028 允许播放 | 91 | 91 |

只有三条普通点火的 64 包发生改变，另外 85 条逐例计数完全保持。C005 的 482 个规则分析／回复包仍允许播放；不把此次修复写成全部过程播报已解决，也不把允许播放当作实际听到。

九条喷水／泡泡／点火轨迹各注入九种不一致，共 81 条合成变体，所有音频均保留。普通／ASan／UBSan 原生夹具覆盖 145 次成功匹配、106 次保留提示，包括并发通道时长、别名、模式、疑问、餐饮背景、超限、错误参数与回执代际；这些夹具不是新增模型成绩或实物测试。旧 ct71 头文件运行新增夹具会失败，反例保留。

[逐例回放与 81 条变体](evidence/ct72-effect-playback/playback-review.json) · [旧策略反例](evidence/ct72-effect-playback/old-policy-counterexample.json) · [软件检查](evidence/ct72-effect-playback/software-checks.json) · [构建记录](../../firmware/esp32-audio/verification-ct72.json)

## 复现

```sh
python3 scripts/verify_improvements.py --source build/xiaozhi-ct72-src
python3 scripts/check_effect_alias_feedback.py \
  --executable build/audio-host/feedback_replay \
  --output output/ct72-playback/review.json
```

统一检查编译仓库实际头文件与回放器，并保留旧二十条轨迹和三十条组合／目标速度变体的回归。ESP-IDF 构建及版本记录独立核对。候选未部署，真人拾音、实际扬声器、设备时序和实物验收继续待完成；原 77/80、6/8 模型成绩不变。
