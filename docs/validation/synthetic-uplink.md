# 让灵矽听一遍固定的 20 条指令

2026-10-31，在 CyberTrack 的灵矽会话里播放同一合成音色的 20 条普通话原话，逐条比对平台识别文字和实际请求的工具。配置页显示小D、5991 字符角色、模型 `deepseek-v4-flash`。角色全文与[平台保存记录](../../firmware/esp32-audio/role-cancel-hold-ct45.json)的摘要一致。会话使用 ct45 的 12 个工具定义，各工具由隔离夹具应答。

| 观察项 | 本轮结果 |
|---|---|
| 正常结束 | 20/20，合计发出 704 个 Opus 帧 |
| 转写文字与原话匹配 | 19/20，忽略空白、句末中文标点及引号，保留数值、单位和正负号 |
| 工具、参数与调用顺序全部匹配 | 19/20 |
| 明确停止 | “停止”“取消序列”均直接请求一次全停，参数为空 |
| 否定、引用、餐饮问题、距离澄清 | 4/4 均未请求动作 |
| 云端回复音频 | 20/20 收到音频字节。扬声器听感与现场静默尚待观察 |

“调到百分之六十”被转写成“掉到百分之六十”，灵矽仍请求将速度设为 60%。这次转写差异没有改变工具参数。“全速”转写正确，平台却在设为 100% 前额外查询了一次状态，还返回英文操作旁白。角色规定，单说“全速”应直接调速，由设备回执区分移动中和空闲。这条失败计入调用顺序，调速目标值正确。

这轮通过二进制发送合成音频，没有向识别器发送原话或场景提示。夹具在模型请求工具时才提供模拟状态。文本固定集会提供前置场景，两组成绩应分别解读。音色、语速和输入链路均固定，本轮未采集真人、环境噪声、设备麦克风或扬声器数据。所有动作请求都停在夹具。

## 复核

[逐条评分及回复](evidence/synthetic-uplink/review.json)保留两层结果。[原始脱敏轨迹](evidence/synthetic-uplink/fixed20.json.gz)还包括工具回执、事件顺序与编码载荷摘要。包大小、帧数和摘要可用于核对一次合成，无需保存音频。完整仓库可直接复算：

```sh
python3 scripts/review_spoken_cases.py --capture docs/validation/evidence/synthetic-uplink/fixed20.json.gz
```

重新采集需要已配置的灵矽测试连接、macOS Tingting 音色和支持 libopus 的 FFmpeg。准备步骤见[隔离采集](lingxi-capture.md)。以下命令在仓库根目录执行，三个环境变量分别指定私有连接 JSON、由 ct45 导出的工具定义和一个新的输出文件。

```sh
ids=$(python3 -c 'import json; print(",".join(json.load(open("docs/validation/spoken-cases.json"))["case_ids"]))')
python3 scripts/capture_lingxi.py --synthetic-speech --ids "$ids" --timeout 55 \
  --connection "$CONNECTION_FILE" --tools "$TOOL_SCHEMAS" \
  --role firmware/esp32-audio/role-prompt.txt --model deepseek-v4-flash \
  --corpus docs/validation/voice-cases.json --output "$NEW_CAPTURE"
```

下一轮可使用同一句“全速”复测调用顺序和英文旁白。真人观察单及三种现场条件见[语音工具选择](README.md#语音工具选择)。
