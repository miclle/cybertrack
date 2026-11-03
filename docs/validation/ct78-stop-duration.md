# ct78 停止调用与时长优先级修正

2026-11-01 先将回归工具与首次验证证据分别提交为 `906015b`、`4059b9e`，再修正角色。最终 5999 字符候选的两轮定向集均为 **16/16**，首次回归的 S01（明确一秒）和 T04（停止漏调用）均复测通过；**完整集仍为 33/35，候选不能上线**。剩余失败为“快一点”漏调用，以及 STT 丢失“先别执行”后误启动。

本次只修改角色及其身份记录，11 个工具、ct78 固件、主机二进制和模型参数均保持不变。所有输入是合成普通话，通过真实平台 STT／模型和无输出固件主机；无麦克风拾音、扬声器验收、串口操作、设备重启或刷写。结束后线上恢复原 5991 字符角色，仓库保留修正版候选。

## 角色修改

- 先区分停止对象：只停说话、否定停止、引用和词义询问不调用动作停止。明确停止动作时直接调用一次 stop；即使空闲、先前已停或重复要求停止，每个新输入仍须取得本轮回执。删除容易被直接复用的“动作都停下了”回复示例。
- 单项、组合和序列统一按“明确时长 → 同一步共享时长 → 默认值”处理。明确一秒为 1000 ms、半秒为 500 ms；同时动作共享两秒时转向也为 2000 ms。只有未指定且未共享时，100% 左右转才默认 880 ms。
- 没有改变固件停止优先级、通道上限、失败隔离、同路忙碌拒绝或暂不执行守卫。角色规则不能代替这些限制，也不能保证模型永不偏离规则。

唯一维护源仍是 [role-prompt.txt](../../firmware/esp32-audio/role-prompt.txt)。最终候选 SHA-256 为 `a8ca1285577e` 开头，完整身份见[实验清单](evidence/ct78-stop-duration/experiment.json)和 [firmware/current.json](../../firmware/current.json)。

## 固定对照与迭代

定向语料在采集前固定为 13 场景／16 轮，覆盖空闲及活动中停止、取消序列、同连接连续三次停止后新动作、否定停止、停止词义、只停说话、明确时长、共享时长和默认／明确混用。[语料](evidence/ct78-stop-duration/focus-cases.json) · [首轮计划](evidence/ct78-stop-duration/plan.json)

| 角色与轮次 | 严格工具／参数匹配 | 结果 |
|---|---:|---|
| 原 ct78，5809 字符 | 13/16 | 两次重复停止漏调用；共享两秒的左转错误使用 880 ms |
| 第一版，5976 字符 | 15/16 | “停止说话”误调用 stop，未采纳 |
| 第二版，5995 字符 | 15/16 | 共享两秒的左转再次使用 880 ms，未采纳 |
| 第三版，5999 字符，定向首轮 | 16/16 | 停止对象与时长全部匹配 |
| 第三版，原完整集 | 33/35 | S01／T04 通过；保留 R02／R03 新失败 |
| 第三版，定向复测 | 16/16 | 与定向首轮一致 |

共采集 **115 轮，全部正常结束**；没有补跑替换失败。第二、三版分别先记录调整理由和后续计划，再保存候选并重开逐字核对。[第二版计划](evidence/ct78-stop-duration/v2-plan.json) · [第三版计划](evidence/ct78-stop-duration/v3-plan.json)

每轮完整 STT、RPC、回执、连续输入状态和终态均由同一冻结主机离线复算一致，没有工具先于本轮非空 STT。最终角色定向集两轮转写均为 16/16；完整集转写为 32/35，其中 B04 顿号变逗号、D01“调到”变“掉到”不影响工具参数，R03 丢失否定尾句则改变了执行语义。这些数字不是真人识别准确率。

[原角色评分](evidence/ct78-stop-duration/baseline-focus-review.json) · [第一版](evidence/ct78-stop-duration/candidate-focus-1-review.json) · [第二版](evidence/ct78-stop-duration/candidate-v2-focus-1-review.json) · [第三版首轮](evidence/ct78-stop-duration/candidate-v3-focus-1-review.json) · [完整集](evidence/ct78-stop-duration/candidate-v3-full-review.json) · [第三版复测](evidence/ct78-stop-duration/candidate-v3-focus-2-review.json)

## 停止与恢复证据

最终角色三轮采集中，19 次预期动作停止均实际调用 stop，其中 12 次调用前主机仍有活动输出或序列。回执均为逻辑全关、序列取消；从各次停止点单独重放后续 60 秒且不注入新指令，旧动作与后续步骤均未恢复。同连接连续三次停止均分别调用，新“左转一秒”仍可接受。

[停止回执与不恢复重放](evidence/ct78-stop-duration/stop-control-review.json)包含全部试验的 39 次实际 stop，含未采纳第一版误停说话的调用；回执执行正确不能把该误调用算成语义通过。另有 [8 项停止调度检查](evidence/ct78-stop-duration/stop-dispatch.json)及 [40 项暂不执行／恢复检查](evidence/ct78-stop-duration/nonexecution.json)通过，均不代表机械停止距离或实机时序验收。

完整集 R01 的调速拒绝后新行走、R04 的序列占用拒绝后停止再喷水均通过。R02 新泡泡动作、R03 新前进动作也能接受，但前轮已有失败，不能把这两组记为完整恢复场景通过。

## 仍然阻塞上线的失败

- **R02 调速分流遗漏。** “快一点”转写正确，却没有调用 adjust_speed，而是追问方向；随后“吹泡泡一秒”调用正常。这不是一次真实工具拒绝，不能计为“拒绝后恢复”通过。
- **R03 否定尾句丢失。** 原话“前进两秒，先别执行”被平台只转写为“前进两秒”，模型调用 move/2000，主机接受，启动计数增加一次。两次试验的输入音频均为 52 帧、7192 字节，payload SHA-256 相同；首次回归识别完整，本次缺少尾句。不能归因于音频文本改动，也不能据此判定服务端内部原因。

对 R03 另做离线反事实诊断：保留实际捕获的 move/2000，只将 STT 输入恢复为完整原话，现有守卫返回 `execution_not_requested`，零启动。该诊断说明守卫仍能处理完整否定句，**不是重新跑通的语音用例，也不能抵消原失败**。[输入同一性与诊断](evidence/ct78-stop-duration/stt-negation-diagnostic.json)

成功确认仍存在；N01／N02 继续说“我先记下了”，R01 朗读规则和工具名。工具正确不等于回复、播放或产品能力表述通过。本次没有重新进行播放端逐包验收，首次回归的播放统计不能移用到新角色。

下一步优先定位否定尾句识别不稳定，再收敛“快一点”的工具分流；保留多余确认与虚构保存的独立问题。原 80 条固定集、真人语音、实机与带载验收均未被本轮替代。

## 平台恢复与复现

平台可见模型为 `deepseek-v4-flash`；温度 0.7、Top P 1、频率惩罚 0、500 token、thinking disabled、reasoning_effort low、usage 开启。各候选保存后均从列表重开逐字核对；最后恢复原 5991 字符角色，再次核对内容和模型参数。没有重启设备，最近记录的设备应用仍为 ct77。[最终候选回读](evidence/ct78-stop-duration/platform-candidate-v3.json) · [恢复记录](evidence/ct78-stop-duration/platform-restored.json)

从仓库根目录运行；需要保留冻结的 ct78 主机二进制，原始压缩轨迹需要完整 checkout，文本参考包不包含 `.gz`：

```sh
python3 scripts/review_voice_scenarios.py \
  --capture docs/validation/evidence/ct78-stop-duration/candidate-v3-focus-2.json.gz \
  --corpus docs/validation/evidence/ct78-stop-duration/focus-cases.json \
  --executable build/ct78-full-host/firmware_host \
  --output output/voice/ct78-stop-duration/review-repeat.json
python3 docs/validation/evidence/ct78-stop-duration/replay_stops.py
```

完整集复算时将 capture 改为 `candidate-v3-full.json.gz`，corpus 改为 `docs/validation/evidence/ct78-voice-regression/cases.json`。主机、工具、语料、角色、采集器与全部证据摘要见[实验清单](evidence/ct78-stop-duration/experiment.json)；认证信息和音频均不提交。
