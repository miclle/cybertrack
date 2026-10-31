# 编排原生数组对照：未采纳

本轮比较 ct68 的 `steps_json` 字符串与 ct69 诊断的 `steps` 对象数组。目标是减少模型生成二次编码 JSON 的负担，同时保留设备参数、版本、确认和停止边界。完整固定集两项均退步，因此不采纳数组接口；主线恢复 ct68，最近记录部署仍为 ct45。

## 输入和实现范围

只有 `sequence`、`compose` 两项公开工具定义变化，其余十项逐项一致。角色只替换描述序列参数的一句话，5991 → 5994 字符；网页／内部字符串接口保持。模型配置页显示 `deepseek-v4-flash`，温度 0.7、Top P 1、频率惩罚 0、最长 500、思考关闭，其他参数沿用基线。该名称是页面标签，不是后端模型身份凭证。

[事先计划](evidence/native-step-inputs/plan.json)要求原 80／8 固定集各跑一次，不替换失败；候选匹配数不得低于新基线，畸形步骤参数不得增加。两组均为真实灵矽文本会话，原话在主机中注入为**模拟识别文本**，回执来自实际 MCP 分发器和控制守卫；没有真实 ASR、麦克风、扬声器或设备动作。

基线采集后新增了本地测试传输元数据和 schema 来源校验，采集器源码哈希因此不同，计划分别保留两份摘要。该变化不修改模型收到的内容，也不投影实际捕获的参数；旧基线全部 88 条回执与终态已用当前辅助函数复算一致。评分先检查实际参数是否符合当时公布的字符串／数组格式，再比较步骤语义，不能把旧字段悄悄转换成新接口的成功调用。

## 完整平台结果

| 项目 | ct68 字符串基线 | ct69 数组诊断 |
|---|---|---|
| 直接动作固定集 | 77/80 | 75/80 |
| 禁止控制调用 | V066 | V064、V065、V066、V079 |
| 八条明确停止 | 8/8 | 8/8 |
| 编排固定集 | 5/8 | 4/8 |
| 编排禁止调用 | 无 | C006 |
| 未完成／步骤格式错误 | 0／0 | 0／0 |

四份原始轨迹共 176 次会话全部结束。每个调用的完整回执、输入事件顺序和观察时刻最终状态均经固定主机重放一致，包括错误调用。没有重采失败或用诊断结果替换固定集。[完整复核](evidence/native-step-inputs/review.json) · [文件摘要](evidence/native-step-inputs/experiment.json)

- 候选 V064／V065／V066 把否定启动误当 `stop`。V079 猜测前进一秒，被已有 `action_unspecified` 门禁拒绝，启动计数为零；它仍是模型禁止调用失败。
- 候选 C006“不要编排表演”误调用全停，已有版本 7 草稿被清除。零启动不能抵消误取消的实际影响。
- 候选 C008“第二步短一点”擅自请求 500 ms，被已有 `draft_duration_unspecified` 拒绝，版本 7、第二步 1000 ms 保持。固件保护生效，不等于模型正确理解。
- C005、C007 仍多查询，C005 有规则分析，基线 C008 仍出现英文过程解释。原生数组没有解决过程文字进入回复的问题；本轮没有声称真实扬声器静默通过。

步骤数组格式本身没有出现畸形请求，但两项固定集均未满足预先规定的不退步门槛。这是一次有随机性的对照，不能把其他工具偏差全部归因于数组；现有结果足以拒绝本次推广，不能证明该形式在所有模型上都更差。

## 软件研究与恢复

诊断实现增加 SDK 数组 schema、拥有独立存储的参数值、延迟回调前释放原始 JSON 的所有权验证；序列、草稿沿用共同校验。另观察到 cJSON 将含 `\u0000` 的字符串截成合法前缀，实验中在机器人 MCP 原始消息入口拒绝这类输入。该防护随未采纳实验保存，**尚未进入主线**，应独立验证、提取，不能以撤回数组接口而遗忘。

[十五组原生场景](evidence/native-step-inputs/native-steps.json.gz)在普通及 ASan／UBSan 主机均通过，涵盖参数生命周期、非法格式、步数／通道／版本约束、停止及有效语义与 ct68 的对照。十三组相对改稿、二十六组含糊动作和八组停止也通过。生成／历史语义夹具显式转换为候选公布的数组格式；**真实捕获重放不转换实际参数**。这些是协议与控制证据，不是新的模型成功样本。

诊断完整 ESP-IDF 5.5.1 编译通过，2,718,800 字节；十六组软件检查含 98 项 Python 测试通过。[诊断构建](evidence/native-step-inputs/diagnostic-build.json) · [当时软件记录](evidence/native-step-inputs/software-checks.json)。未刷写设备。

[实验补丁](evidence/native-step-inputs/experimental-source.patch.txt)基于 `c10a11dea86f9238d0a3e21d9a10ea9471036f67`，包含 26 个文件；在独立临时仓库应用后逐文件哈希一致。补丁包含当时的版本与角色候选，供完整 checkout 中隔离复现，不应直接部署。[补丁清单](evidence/native-step-inputs/source-patch-manifest.json)

主线运行时恢复至 ct68，源码／部署两份本地镜像均按字节与哈希回读；原角色 5991 字符已在平台保存、重开逐字核对，模型与全部原参数保持。[源码恢复](evidence/native-step-inputs/restored-source-check.json) · [平台恢复](evidence/native-step-inputs/restored-platform-readback.json)。没有重启或刷写设备，不把配置恢复当作板端生效验收。

有原始 checkout 及两份固定主机时，可离线重放全部记录：

```sh
python3 scripts/review_native_steps.py \
  --directory docs/validation/evidence/native-step-inputs \
  --baseline-executable build/ct68-vague-host/firmware_host \
  --candidate-executable build/ct69-array-capture-host/firmware_host \
  --output output/native-step-inputs/review.json
```

源码／平台恢复后继续保留原 I03／I06／I13 门槛。下一步优先独立修复原始 JSON 截断准入问题，再处理误停和过程播报；真人、设备时序、确认后实际表演及家庭体验继续待验。

参考包包含本轮文本审阅、工具／角色与恢复记录，原始压缩轨迹和二进制重放仍需 checkout。解压预检的 72 项离线测试通过，七组既有模型评分及 STT 未完成样本保持；不把材料完整性当作候选通过。
