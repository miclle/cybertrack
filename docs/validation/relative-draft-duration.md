# 无量化时长的相对改稿门禁

ct67 将已观察到的“第二步短一点”猜半秒问题补上一层设备约束。它是源码候选，最近记录部署仍为 ct45；没有刷写或触发真实设备。十二项公开工具定义和角色源均不变。[构建记录](../../firmware/esp32-audio/verification-ct67.json)

## 行为

本轮 STT 出现可识别的相对长短表达、涉及步骤／草稿／表演／泡泡等对象，且整句没有量化片段时，设备标记需要澄清。只说“短一点”等简短追述也有覆盖；直接的说话、回答、解释长短表达排除。常见明确时间单位、数值比例及“一半”等量化表达交回原有模型与参数契约，不由此门禁计算或猜测新时长。

请求分发取得识别代际，动作回调在控制锁内检查该标记。首次修改、删除、取消或动作替代请求返回 `draft_duration_unspecified`，附 `clarification_facts` 要求只询问具体秒数；草稿与活动输出不因这次拒绝改变。同轮失败隔离继续阻止模型换工具重试或补做。查询和全停仍可用，新的 STT 重新计算标记，旧回调不能改变新一轮；网页和板内可信控制继续按原权限工作。

这不是完整自然语言理解。检查依赖一组中文表达，未识别的说法仍沿用原路径；它没有判定数值属于当前值还是目标值、引用还是指令、哪一个步骤。例如一句话含“第一步三秒，第二步短一点”，已有数值会使本项不拦截，仍需后续目标归属约束。明确停止保持优先，因此也不能靠本项修复模型误调 stop。首次含糊行走、其他意图错误和过程播报仍未解决。

## 原生控制证据

十三组使用实际 MCP 分发、实际回调与守卫，输入和时钟模拟：

- 三种相对改稿及直接改用取消、行走、序列，均要求澄清，不改稿、不新启动。
- 拒绝后的同轮动作被拦截；新输入明确两秒后，必须重新查询再改稿，保留第一步。
- 新输入取消、仅替换方向的默认 880 ms、明确三周的协议内长时长均保留。
- 旧排队回调不污染新输入；混合句中的全停仍直接生效并观察到 60 秒不恢复。
- 复用此前真实平台 C008 的实际 RPC 参数和时刻，另注入模拟识别文本；原先草稿 7→8 的猜半秒请求现被拒绝，保持版本 7。此项是历史请求回放，不是新的模型成绩。

额外的 ASan／UBSan 测试覆盖量化／非量化表达、说话长短对照，以及语音拒绝不影响可信网页控制和停止。[原生回放](evidence/ct67-relative-draft/native-replay.json) · [旧版对照](evidence/ct67-relative-draft/native-baseline.json)

## 二十条真实 STT 定向会话

预先声明十条原话、两轮独立采集，发送合成普通话 Opus，不发送评测原话文本。按实际收到的 STT 顺序开启主机输入代际，并提供实际 MCP 回执，不向机器人转发。它与原固定八十条和二十条真人语音分开，不能替代家庭或扬声器验收。[十条语料](relative-draft-cases.json) · [采集计划](evidence/ct67-relative-draft/plan.json)

| 项目 | 结果 |
|---|---|
| 正常结束 | 20/20 |
| 归一标点／空白后的逐字转写 | 20/20 |
| 严格工具、参数和顺序 | 14/20；六条相对改稿均多查询一次 |
| 预期草稿／输出／启动计数终态 | 20/20 |
| 六条相对改稿保留原稿 | 6/6 |
| 在线实际拦截猜测修改 | 0 次；六条均未请求修改，不能声称门禁在这些会话中拦截过 |
| 其他十四条明确修改、取消、删除、停止、查询 | 工具与终态符合预期 |

英文操作文字、规则分析和停止确认仍存在。严格工具分数没有因终态正确而改为通过；真正的拦截依据来自上面的原生协议及历史请求回放。[逐条转写、调用和回复](evidence/ct67-relative-draft/platform-review.json)

采集使用固定的初始 ct67 主机，随后补齐“天／周／个星期”等量化单位兼容。原捕获程序和二进制保留；最终候选对全部实际输入分类相同，逐条完整 MCP 回执及终态重放一致。报告分别记录捕获与最终主机、分类器摘要，未修改原始轨迹，也没有重采样替换结果。[主机与文件清单](evidence/ct67-relative-draft/experiment.json)

## 复核与边界

```sh
python3 scripts/check_relative_draft.py --executable /path/to/final/firmware_host \
  --output output/relative-draft-native.json
python3 scripts/review_relative_draft.py \
  --directory docs/validation/evidence/ct67-relative-draft \
  --executable /path/to/final/firmware_host --classifier /path/to/final/draft_duration_probe \
  --capture-executable /path/to/captured/firmware_host \
  --capture-classifier /path/to/captured/draft_duration_probe
```

构建主机见[完整固件主机](firmware-host.md)。分类器探针只用于离线查看同一 C++ 函数，可用 C++17、`-Ifirmware/esp32-audio` 编译 `firmware/esp32-audio/tests/draft_duration_probe.cc`。上述完整控制重放需要 checkout 与对应环境；参考包只含材料及完整性核对。

最终十四组本地检查通过，包含 86 项改进测试、原八十条／八条预期请求、输入隔离、停止、网页和音频回归。ESP-IDF 5.5.1 构建为 2,714,816 字节，摘要见构建记录。设备时序、物理输出与机械停止、真人语音、家庭体验及量化目标归属均继续待验。
