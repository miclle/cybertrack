# 文本联调的模拟识别输入

此前原话文本联调运行实际 MCP 主机，但主机只收到固定占位文本，不能触发基于原话的 ct67／ct68 局部意图标记。[角色对照](intent-routing-role.md)保留该边界。新的文本采集把用例原话作为模拟识别事件注入，仍不声称经过 ASR。

## 三种来源分别保留

| `host_input_mode` | 主机输入 | 回放方式 |
|---|---|---|
| `simulated_initial_input` | 历史固定占位文本 | 保持旧版初始化，不回填原话 |
| `simulated_recognized_text` | 新文本诊断的用例原话 | 主机先等待输入，再按 `simulated_input` 事件开启输入代际 |
| `platform_stt_events` | 合成语音经过平台后实际收到的 STT | 主机先等待输入，再按接收顺序注入 STT |

新运行 `--firmware-host --raw-text` 默认使用第二种模式。原话在最后一页工具声明后、工具调用前注入一次，并在 `timeline` 和 `host_calls` 保存相同的文本及相对时刻。工具 RPC 与末尾状态均使用等待输入的主机模式。文本回显只记录，不再次开启输入代际；空白／未知输入仍由固件原有逻辑处理，不增加授权。

采集器不会读取预期调用或预期回复。模拟识别不能同时开启音频上行或 STT 注入。既有真实 STT 入口与旧原始记录不变，没有为旧会话补造输入、重写回执或重算为门禁已参与。

## 复核

```sh
python3 scripts/review_firmware_capture.py /path/to/capture.json.gz \
  --corpus /path/to/corpus.json --executable /path/to/frozen/firmware_host \
  --output output/capture-input-review.json
```

复核器核对语料与二进制哈希、输入来源、事件顺序、时刻、原始 RPC 参数，以及每一条完整回执和最终状态。模拟文本必须与原话一致且只出现一次；真实 STT 缺失时不会代填原话，提前工具请求另行列出。保留未完成与工具语义偏差；成功复算不代表模型正确、真实收音或实物验收。

完整控制重放需要 checkout 中的原始压缩轨迹与对应固定主机。参考包仅提供所选文字材料及完整性检查，不含二进制或完整捕获。

## 定向结果

预先声明十二条原话、两轮各采一次，涵盖未量化改稿、明确两秒／半秒、方向替换、取消、含糊行走、默认动作、查询与全停。角色及十二项工具不变，固定 ct68 主机和原 DeepSeek 配置，没有设备 IO。

- **24/24** 正常结束，原话输入、每条完整 RPC 回执与终态均复算一致；同观测时刻的预期终态 **24/24**。
- 严格工具调用 **20/24**。两轮 D001 都多查一次状态；两轮 A004 都把“动一下三秒”猜为前进，返回 `action_unspecified`，零启动。设备拒绝有效不使模型错误通过。
- 本批相对改稿只查询，没有尝试修改，因此不声称实际拦截了相对改稿。明确时长、方向与取消按预期保存；动作与查询／全停保留。
- 新复核器另对十二条历史占位输入和十条原始真实 STT 记录复算，完整回执和终态一致，没有回填旧输入。

[逐条结果](evidence/capture-recognized-input/summary.json) · [来源、检查与清单](evidence/capture-recognized-input/experiment.json)。十五组统一软件检查通过，含 93 项改进测试；这些结果不替代原固定集、真人语音或实物验收。

```sh
python3 scripts/review_capture_inputs.py \
  --directory docs/validation/evidence/capture-recognized-input \
  --executable /path/to/ct68/firmware_host --output output/capture-input-summary.json
```

## 后续工具结构

当前固定小智 SDK 的 `PropertyType` 只有布尔、整数和字符串；sequence／compose 的步骤通过 `steps_json` 编码，模型需要拼接 JSON 字符串。MCP 的参数由 [JSON Schema 描述](https://modelcontextprotocol.io/specification/2024-11-05/server/tools)，下一阶段应同时验证嵌套步骤 schema、SDK 解析、内存所有权和实际设备参数校验，不能只改工具说明就声称已支持结构化数组。现有草稿版本、允许通道和网页确认门槛继续保留；本轮未改变这两项工具或任何固件。
