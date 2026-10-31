# 停止即时回执与调度

ct66 将已校验的 MCP 全停请求在分发路径完成并立即返回回执，不再留下第二次排队回调。当前是源码候选；最近记录部署仍为 ct45，未刷写或触发设备。公开十二项工具的定义、参数和角色源不变。[构建记录](../../firmware/esp32-audio/verification-ct66.json)

## 原问题与修复

旧版在参数校验后已经立即关闭输出，因此不能把本问题描述为“新识别文本阻止了第一次停止”。但它随后还会排队执行 stop 回调：如果先收到新识别文本，回调返回 `voice_input_changed`，与已经发生的停止不一致；如果轮次未变，它会再停止一次，可能取消第一次停止之后才接受的新请求。

新版先检查严格空参数，再同步调用实际停止回调、采集回执并结束 RPC。停止不需要当前识别轮次可用，也不等待主调度队列；动作、调速、改稿和查询仍保持原有参数、代际、失败和票据检查。非法参数或调用者伪造 `_ct_turn` 不会获得停止路径。

实际全停与输出应用发生在回执缓冲分配之前。分配失败时可能无法回复成功，但四路逻辑输出和后续序列已停止。网页仍先验证会话所有权，失效会话不会借此获得远程停止权限。停止完成后，新的显式请求可按原准入规则执行；固件不会恢复旧动作。

## 证据范围

使用真实 MCP 分发、实际回调和控制守卫，显式模拟排队、输入、时间及 IO。八组场景如下。

| 场景 | ct66 结果 |
|---|---|
| 活动序列收到全停，随后到达新识别文本 | 立即返回 `ok`，关闭输出并取消序列；60 秒不恢复 |
| 停止后收到新输入和新动作，再清空旧队列 | 回执顺序为停止、动作；新动作保留，没有旧停止回调 |
| 同一输入内显式发出后续新请求 | 不被二次停止清掉；这是协议调度测试，不是建议模型自动追加动作 |
| 已排队动作之后收到停止 | 先返回停止成功，旧动作票据被撤销，零启动 |
| 带额外字段的停止 | 参数错误，原运动继续 |
| 伪造内部轮次的停止 | 参数错误，原运动继续 |
| 尚无识别输入时停止 | 仍立即成功，取消原活动序列 |
| 旧动作和旧查询遇到新输入 | 仍拒绝为 `voice_input_changed`，不污染新输入的合法动作 |

[旧版回放](evidence/ct66-stop-dispatch/baseline.json.gz)在同一八组检查中有五组未满足即时回执／无二次回调要求。新版八组通过；所有结果保留完整逻辑状态，不作为新模型成绩。[对比摘要](evidence/ct66-stop-dispatch/comparison.json) · [逐例请求与回执](evidence/ct66-stop-dispatch/replay.json)

另外对实际 Reply 注入下一次 C++ 内存分配失败，四路同时运行和两步序列均已停止，60 秒后不恢复；失效网页会话的停止请求被拒绝且原合法运动继续。实际参数／HTTP／音频检查使用 ASan／UBSan；完整统一检查共十三组通过，包含 86 项改进测试。ESP-IDF 5.5.1 构建通过，镜像 2,712,576 字节，SHA-256 见构建记录。[检查摘要](evidence/ct66-stop-dispatch/software-checks.json) · [主机来源](evidence/ct66-stop-dispatch/host-manifest.json)

```sh
python3 scripts/build_firmware_host.py --source build/xiaozhi-ct66-src --output build/ct66-stop-host
python3 scripts/check_stop_dispatch.py --executable build/ct66-stop-host/firmware_host \
  --output output/stop-dispatch-review.json
python3 scripts/verify_improvements.py --source build/xiaozhi-ct66-src
```

`check_stop_dispatch.py` 未通过时返回非零，并保留每组请求、回执与终态。主机源码和完整控制重放需要 checkout 与 prepared 固件；参考包仅附摘要和脚本。检查不接触串口、真实 GPIO 或平台账号。

这次修改不会判断含糊指令，也不会修复模型误调 stop／move 或提前播报规则分析。[ct65 未采纳结果](stop-negation.md)继续保留，七组既有文本成绩及合成语音未完成项不改变。实际设备调度、扬声器、输出关断延迟及机械停止仍需分别验收。
