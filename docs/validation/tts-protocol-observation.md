# 播报阶段字段观测与 none 参数对照

本轮先完成八条定向合成普通话实际 STT，再仅将 `reasoning_effort` 从 `low` 临时改为 `none` 重复同组八条。最后恢复原值，并另采一次停止检查。每条只采一次，不重试、不替换原失败；这 17 条会话不是完整 80／8 成绩，也没有向机器人转发动作。

## 观测什么

采集器新增可选 `--protocol-events`，保留实际收到 JSON 的字段名、类型、有限阶段枚举及到达时刻，不保留额外任意字段值、会话编号、令牌或音频。原 TTS 文字、STT、工具、回执与时序按原方式保存。它观测设备边界，不能直接看到模型供应商的原始请求或返回。

八条覆盖：喷水超限 V020、组合 V033、停止 V045、模式状态 V057、否定 V064、明确改稿 C002、口头开始 C005、含糊改稿 C008。[事先计划](evidence/tts-protocol-observation/plan.json) · [单参数对照计划](evidence/tts-protocol-observation/candidate-plan.json)

在这两组收到的 TTS／LLM 消息中，没有观察到 `phase`、`stage`、`channel` 或独立的 `reasoning_content` 字段。这只描述本轮消息，不断言整个平台都不提供这些字段。

LLM 情感消息里的 `action=thinking` 同时伴随正常的“喷水单次最多三十秒”、成功确认、状态回复、否定回复和候选异常提示。它不能直接当作内部推理或中间轮的标志。[官方 WebSocket 文档](https://linx.qiniu.com/docs/xrobot/platform/websocket)也将此消息定义为表情／动作反馈。因此没有实现按该值丢弃音频的策略。

基线 C005／C008 的首个音频早于第一条工具调用；C005 又在查询之后请求 sequence，实际主机返回 `action_unspecified`，没有启动。这说明单靠等待成功保存回执不能覆盖这些过程播报。C005 到 55 秒时未正常结束，原样保留。

## 参数对照结果

[DeepSeek 当前 Chat Completions 文档](https://api-docs.deepseek.com/api/create-chat-completion/)列出 `reasoning_effort=none`，并说明 `thinking` 指定值的优先级。灵矽页面仍显示 `deepseek-v4-flash`，实际供应商身份及请求字段没有独立凭据；不能将官方模型的行为直接等同于该标签。

| 项目 | 原 low | 临时 none |
|---|---:|---:|
| 正常收到结束 | 7/8 | 8/8 |
| 严格工具匹配 | 6/8 | 3/8 |
| 统一异常回复 | 0/8 | 8/8 |
| 明确停止 V045 | 直接 stop | 没有工具调用 |

`none` 已经过保存、返回列表和重开回读确认。八条却全部回复“抱歉，我有点迷糊了，稍后再聊哦。”，包括应调用动作、查询及停止的用例。候选 C005／C008 没有工具，形式上匹配“无需工具”，但回复并未完成网页确认指引或时长澄清，不能算体验改善。候选不采纳，没有进入完整固定集或部署。

目前无法由统一异常文字确定是模型参数兼容、实际模型差异还是平台转发问题；没有服务端错误码或上游请求记录，不推断具体 HTTP 错误。

## 恢复与证据

已恢复 DeepSeek、温度 0.7、Top P 1、频率惩罚 0、最长回复 500、`thinking.type=disabled`、`reasoning_effort=low` 和 usage；5991 字符角色逐字与仓库一致。保存成功后重开回读，并新建连接复核 V045：一次 stop、`result=ok`、全部逻辑输出关闭，没有增加启动。该夹具初态已有一次合成启动，不能将结束计数 1 误报成新启动。

[原参数](evidence/tts-protocol-observation/platform-before.json) · [候选回读](evidence/tts-protocol-observation/platform-candidate.json) · [恢复回读](evidence/tts-protocol-observation/platform-restored.json) · [两组完整审阅](evidence/tts-protocol-observation/review.json) · [恢复停止](evidence/tts-protocol-observation/restored-stop-review.json) · [摘要](evidence/tts-protocol-observation/summary.json) · [文件校验](evidence/tts-protocol-observation/experiment.json)

所有实际 STT 输入、完整 RPC 回执和终态重放一致，17 条原始轨迹按五份 gzip 保留。读取完整 checkout 后可运行：

```sh
python3 scripts/review_tts_protocol.py \
  --directory docs/validation/evidence/tts-protocol-observation \
  --executable /path/to/frozen/tts-protocol-host/firmware_host \
  --output output/tts-protocol-review.json
```

新增字段观测的隐私边界回归通过，完整源码现有 107 项 Python 测试。固件源码仍 ct72、最近记录部署仍 ct45；本轮没有重新编译或刷写，也没有重启设备。总目标的语义、过程播报、设备及家庭门槛继续未完成。

下一修复点应在模型返回与 TTS 合成之间：核对实际转发参数，区分结构化推理、带工具的中间轮普通内容和最终回复。[官方自定义 LLM 接入](https://linx.qiniu.com/docs/xrobot/guide/third-app)提供可插入这一处理的接口，但本轮没有创建、部署或绑定新模型服务；工具后最终回复中的分析文字仍须另行约束，不能仅靠丢弃工具轮内容宣称解决。
