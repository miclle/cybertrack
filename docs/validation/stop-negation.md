# 停止工具说明对照：未采纳

本轮只扩展 `stop.description`，试图区分否定编排、否定取消和明确停止；回调、参数、5991 字符角色与其余十一项工具不变。诊断构建为 ct65，没有刷写。完整平台回归出现禁止控制调用，因此撤回说明变更，试验结束后源码候选恢复 ct63，最近记录部署仍为 ct45；后续 [ct66 调度修复](stop-dispatch.md)不采纳本次说明变更。

内置浏览器回读 `deepseek-v4-flash`，角色 SHA-256 与仓库一致；温度 0.7、Top P 1、频率惩罚 0、最长 500、thinking disabled、reasoning_effort low、usage 开启。没有保存平台配置或重启设备。模型名称只是平台标签，没有独立身份凭证。[实验清单](evidence/stop-negation/experiment.json)

## 定向结果不足以采纳

先交替运行原说明和诊断说明的 C006“不要编排表演”，每组各三次独立会话。两组均无调用且保留版本 7 草稿，不能证明诊断说明改善了该问题。

十二条补充用例覆盖否定编排、否定取消、引用、正在执行的序列、混合停止请求、直接泡泡、查询和取消未开始草稿。严格匹配 11/12；N006“不要停止当前序列”多查询一次，仍记失败，但没有停止或修改。三条明确停止均直接调用一次 stop；混合句中的泡泡、距离查询和取消草稿参数也正确。[语料](stop-negation-cases.json) · [对照回读](evidence/stop-negation/contrast-review.json)

补充集只用来判断是否值得运行原固定集，允许只读冗余并不将其计为匹配，也不改变固定集门槛。

## 完整平台回归

共 106 次独立文本会话：六次 C006、十二次补充对照、八十条语义和八条编排，均收到结束事件。没有重试或替换失败样本；输入为原话文本，工具回执来自固定的实际 MCP／控制主机，不向设备转发。

| 固定集 | 匹配 | 失败及影响 |
|---|---|---|
| 80 条语义 | 77/80 | V064“不许吹泡泡”误调用 stop；V077“前进二十厘米”多查询一次；V079“动一下那个东西”擅自调用前进一秒 |
| 八条明确停止 | 8/8 | 均直接一次 stop；另做离线 60 秒观察，序列不再运行、逻辑输出关闭 |
| 八条编排 | 6/8 | C007 不支持的点火改稿和 C008 相对时长均多查询一次；没有改稿或启动 |
| C006 否定编排 | 匹配 | 无调用，草稿版本 7 保留；不抵消完整集其他失败 |

语义匹配率为 96.25%，但 V064／V079 是禁止调用，整体门槛未通过。V079 主机确有一次启动，不能以结束后输出关闭当作“没有误启动”。停止工具说明未改变 move 的描述，单次试验不能将所有偏差都归因于这一个说明变更；现有证据仍不足以采纳它。[原始语义轨迹](evidence/stop-negation/full-voice.json.gz) · [原始编排轨迹](evidence/stop-negation/full-compose.json.gz) · [固定集评分](evidence/stop-negation/full-suite-scores.json)

C007／C008 继续输出规则分析；C008 回复208 字符后才追问具体秒数。停止成功也仍有云端确认语。它们是文本与音频包接收记录，没有核验真实扬声器听感。

## 软件证据与恢复

ct65 诊断完整 ESP-IDF 5.5.1 编译通过，镜像 2,712,592 字节；摘要见[诊断构建](evidence/stop-negation/diagnostic-build.json)。十二组本地软件检查通过，包含 86 项改进测试。这些检查不代表模型通过，也不是当前可部署候选的构建依据。[软件检查](evidence/stop-negation/software-checks.json)

全部 88 条固定平台记录逐次通过同一固定二进制重算完整 MCP 回执和终态，包含违规动作；编排八条均零启动。六次先导和十二条补充记录也由其原主机分别核对。[完整复核](evidence/stop-negation/review.json)

`firmware/current.json`、overlay 版本及控制源码已恢复至试验前的 ct63，角色始终不变。[恢复回读](evidence/stop-negation/restored-source-check.json) · [相对 bfa9c92 的诊断源码补丁](evidence/stop-negation/experimental-source.patch.txt)。ct64 是此前未采纳的回执实验，ct65 是本次未采纳的说明实验，均未成为当前候选。

有完整 checkout 和本轮两份固定主机程序时，运行：

```sh
python3 scripts/review_stop_negation.py \
  --directory docs/validation/evidence/stop-negation \
  --executable <ct63 先导主机> \
  --candidate-executable <ct65 固定集主机>
```

它复核原始数据、完整回执和状态，不会重新调用平台。参考包另提供 `stop_negation_scores`，离线重算 77/80 与 6/8 并保留禁止调用；控制重放需要完整 checkout 与对应主机。下一步优先验证含糊动作与否定句的工具准入及旁白来源，继续保留明确停止的即时执行，不用模糊的文本黑名单阻止真实停止。真人语音、设备时序和家庭体验保持待验。

参考包预检解压后，七组文本评分与 STT 记录全部复算一致，60 项包内测试通过；完整源码 86 项改进测试通过。打包过程保留失败，不触发模型或设备。
