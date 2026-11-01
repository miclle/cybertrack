# 精简角色对照：首轮改善，复测漏停，未采纳

> 本页为对应旧版本的历史验证；涉及的表演编辑已退役，不代表 ct78 能力。[当前退役说明](theatre-removal.md)


2026-11-01 将 5991 字符角色精简为 4000 字符，按停止、否定／引用、口头开始、含糊／非法改稿、具体草稿编辑、查询和直接动作分流。目标是减少多余查询、猜测改稿与过程播报。**首轮改善没有稳定复现；候选因漏停撤回，平台和仓库已恢复原角色。** 设备没有重启或刷写，源码仍为独立的 ct76 门禁候选，最近部署 ct75。

## 固定对照结果

冻结同一 ct75 无输出主机、十二项工具、模型参数和 36 条原话。第一轮基线与候选各一次，再按先行门槛启动候选复测；模型名称为页面标签 `deepseek-v4-flash`，不是后端身份签名。全部为原话文本诊断，主机注入模拟识别文本，**不是实际 STT、扬声器或实物验收**。

| 检查 | 基线首轮 | 候选首轮 | 候选复测 |
|---|---:|---:|---:|
| 严格工具与参数匹配 | 29/36 | 34/36 | 32/36 |
| 正常结束 | 34/36 | 36/36 | 36/36 |
| 已知禁止写入调用 | 2 | 0 | 0 |
| 明确停止且不先查询 | 11/11 | 11/11 | 9/11 |
| 应静默动作无平台文字／音频 | 0/14 | 0/14 | 0/14 |

基线 V064 连接关闭，未保存该条的局部调用／回复；它记为未完成且调用未知，不能当作“没有禁止调用”。仅继续下一个未执行用例，未重跑覆盖。C005 收到长篇规则分析并超过 60 秒完成时限。共 108 个比较槽位，保留 107 条轨迹，106 条正常结束；107 条已保存轨迹的输入、完整 RPC 回执与终态均用固定主机复算一致。

首轮候选 C005“开始这段表演”不再查状态或长篇分析，直接提示网页确认；C001–C003 保存和改单的说明变短。C008 仍多查询一次，但没有猜半秒；N003 否定取消多查状态。停止确认依然存在，另外出现英文操作说明和 N002／N006 的否定规则分析，不能把总字数减少当作消除多余播报。[首轮控制复核](evidence/concise-role/review.json) · [逐条播报审阅](evidence/concise-role/speech-review.json)

复测暴露了不能采纳的退步：

- **V047“停止行走”没有调用工具，却回复“已停止”。** 隔离主机终态左右驱动仍为 70，原移动没有被停止请求取消。这是模型漏调用与虚假完成，不能用回复文字代替停止证据。
- V051“取消序列”先查询再停止，违反直接停止要求。
- C003 明确删除第一步时只查询、追加不必要确认，未完成删除；N004 否定取消多查状态。

按[预先记录的复测退出条件](evidence/concise-role/followup-plan.json)，保留整轮后撤回候选，不再运行其余条件性轮次或原 80／8 全集。原完整语音成绩保持 77/80、6/8，本次定向成绩不替换它。[复测完整检查](evidence/concise-role/candidate-2-review.json)

## 恢复与复现

内置浏览器的原标签连接不可用、Mac 锁屏后，另开同一内置浏览器标签恢复了访问。原角色全值回读一致；候选保存后从列表重开逐字核对 4000 字符。实验结束已保存原 5991 字符角色，从列表重开逐字核对，模型参数保持温度 0.7、Top P 1、频率惩罚 0、500 token、thinking disabled、reasoning_effort low、usage 开启。恢复后另建一条 V047 会话，直接停止、回执成功和主机输出关闭均复核通过；此单项不覆盖候选失败或代替完整回归。[恢复停止检查](evidence/concise-role/restored-stop-review.json)。没有设备重启或配置加载验收。[恢复回读](evidence/concise-role/restored-readback.json) · [当前角色记录](../../firmware/esp32-audio/role-concise-restored-ct75.json)

正式维护入口仍为 [role-prompt.txt](../../firmware/esp32-audio/role-prompt.txt)，实验快照只用于复核。[原计划](evidence/concise-role/plan.json) · [实际执行与中断说明](evidence/concise-role/execution.json)

```sh
python3 scripts/review_concise_role.py \
  --directory docs/validation/evidence/concise-role \
  --executable build/concise-role-host/firmware_host \
  --output output/concise-role-review.json
python3 scripts/review_firmware_capture.py \
  docs/validation/evidence/concise-role/candidate-2.json.gz \
  --corpus docs/validation/evidence/concise-role/cases.json \
  --executable build/concise-role-host/firmware_host \
  --output output/concise-role-repeat-review.json
```

第一条复核首轮两组及未知中断，第二条复核完整复测。六项评分反例测试防止把未知调用、超时、漏工具或有音频的回复算作通过。需要保留的冻结主机与归档轨迹；参考包只提供文字材料，不冒充可直接运行的整套环境。

下一步应优先解决停止与真实回执约束，以及模型最终回复和过程文本的可靠区分；这次实验不足以证明页面思考参数被如何转发，也不能用删除英文或全面丢弃 TTS 来掩盖错误。独立的 [ct76 分句改稿门禁](history/draft-clause-duration.md)继续保留，但不宣称它修复了本次模型漏停或播报。
