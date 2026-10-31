# 平台模型参数的原话对照

2026-10-31 解锁后，通过新建内置浏览器页面恢复配置访问，重新打开 CyberTrack 角色页与模型参数。此前已有页的连接不可用，不再作为当前阻塞。5991 字符角色逐字回读，含末尾换行的 SHA-256 与仓库一致：`7f286df244df131de1271d1fcb0a82c5374998a2590cba7eb099645a4c4d9127`。

## DeepSeek 温度对照

保存前回读的模型是 `deepseek-v4-flash`，温度 0.7、Top P 1、频率惩罚 0、最长回复 500 token。模型专属字段为 `thinking: {"type":"disabled"}`、`reasoning_effort: low` 和返回 usage。思考已关闭，不能把过程播报归因于“思考没关”。这些是页面配置；WSS 响应没有独立的模型身份或生成参数确认。

只将温度改为 0.2，保存后重新打开回读，再对 C005“开始这段表演”和 C008“第二步短一点”各做三次独立原话会话。工具定义、5991 字符角色、语料、完整 MCP 主机和捕获程序保持不变。没有修改固件或将工具调用转发给设备。[配置与捕获摘要](evidence/model-temperature/experiment.json) · [逐条回复及草稿](evidence/model-temperature/review.json)

| 观察项 | 结果 |
|---|---|
| 正常结束 | 6/6 |
| 严格工具匹配 | 0/6：六次均多查状态，其中一次还提交改稿 |
| 草稿误改 | 一次 C008 将第二步从 1000 ms 改为 500 ms，版本 7→8 |
| 启动与最终逻辑输出 | 全部零启动、输出关闭 |
| 从输入到结束中位数 | 26.7 秒 |
| 过程文字 | 六次均仍有规则分析或操作说明 |

**不保留低温度设置。** 此前原说明、温度 0.7 的[诊断基线](compose-routing.md)为 2/6 匹配、中位数 15.1 秒；两组分时采集，样本少，不能将数值差异确定归因于温度，也不声称设置在所有请求上更差。本轮已足以说明它没有解决这些用例的多余查询、误改和过程播报，不进入完整固定集成绩。

六次捕获均已按原 RPC 编号和时刻通过相同二进制重放，MCP 结果和终态逐项一致。结束后将温度恢复 0.7、保存并重新打开；Top P、惩罚、长度和高级字段均回读与原值一致。原值与实验值的本地截图摘要见实验清单，截图位于 `output/model-parameters/`，不随参考包分发。整个过程没有重启或刷写机器人，真人声音、扬声器和实物表现仍未验收。

完整 checkout 可查看六份原始轨迹，独立核对完成标记、调用与终态：

```sh
python3 - <<'PY'
import gzip, json
from pathlib import Path
root = Path('docs/validation/evidence/model-temperature')
for path in sorted(root.glob('temperature02-*.json.gz')):
    row = json.loads(gzip.decompress(path.read_bytes()))['results'][0]
    state = row['host_final_state']
    print(path.name, row['completed'], row['calls'],
          state['show_draft']['revision'], state['starts_this_boot'])
PY
```

模型对照另行记录：先保持角色、工具、主机及通用参数，再比较明确改稿、含糊追问、开始确认与停止。模型专属参数按实际页面回读，不将 DeepSeek 的参数结构复制到其他模型。定向结果不替代完整固定集或现场验收。

## 通义千问极速版对照

保存并重新打开模型配置，确认平台标签为“通义千问极速版”；通用参数仍为 0.7／1／0／500，联网搜索和 `enable_thinking` 均关闭。角色逐字回读与上文哈希一致。这是页面提供的名称，不推断具体底层模型版本。[六次定向配置与轨迹索引](evidence/model-qwen/targeted-experiment.json)

C005 和 C008 各三次均不调用工具、不改草稿，直接说明网页确认或询问秒数，未出现过程分析。随后完整运行原 80 条语义与八条编排，保留了定向测试没有发现的失败：[完整评分](evidence/model-qwen/full-suite-scores.json) · [逐条失败审阅](evidence/model-qwen/full-review.json) · [语义轨迹](evidence/model-qwen/full-voice.json.gz) · [编排轨迹](evidence/model-qwen/full-compose.json.gz)

| 检查 | 结果 |
|---|---|
| 正常结束 | 88/88 |
| 语义工具、参数与顺序 | 68/80，未达门槛 |
| 明确停止 | 7/8；V049“停止泡泡”没有调用 stop |
| 禁止动作样本 | V079“动一下那个东西”错误调用 move，模拟主机启动前进 |
| 编排工具与顺序 | 7/8；C002 的单步修改误传两步数组，被实际解析器拒绝 |

V049 回复“已停止泡泡”，但没有工具调用；其预置活动序列在结束时仍运行。V002、V013、V025、V039、V040 也有无调用却确认动作／调速的回复；V027、V038 则把伪工具表达式作为语音文字。V053、V058 未查询就回答状态／距离。编排 C006 虽未调用工具，却说“已取消”，原草稿仍在；工具分数不能替代这些回复语义审阅。

**不保留这版模型配置。** 六次定向成功没有覆盖完整指令范围，不能以较短回复抵消漏停、含糊请求启动和虚假确认。88 行完整 MCP 结果与终态已通过同一固定主机逐项重放；其中行走、点火等均为无执行器逻辑，不是实机动作或硬件验收。历史 DeepSeek 成绩保持原样，模型对照不替换原固定集。
