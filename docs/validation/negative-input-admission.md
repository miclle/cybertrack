# ct71：否定输入保留未开演的草稿

ct71 在已识别文本上增加有限的完整否定句检查：空闲时说“不要编排表演”，不会因模型误调 `stop` 清掉已有草稿；受支持否定句的首次启动、调速、改稿和取消也返回 `input_negated`。它是源码候选，最近记录部署仍为 ct45，未修改平台角色、模型参数或十二项公开工具定义。[构建与检查](../../firmware/esp32-audio/verification-ct71.json)

## 控制边界

分类按完整分句匹配，支持有限的礼貌／时间前缀、否定词和动作／草稿表达；全句各分句必须属于同一受支持类别。引用、问句、未知词、不同类别或正负混合请求交回原路径，不能只因含“不要”就拒绝整句。例如“先不要编排，直接吹泡泡两秒”保留直接泡泡；“先别编排了，马上停下”保留全停。

标记来自本轮实际 STT，不是模型可提交的工具参数。受支持的否定句可以查询，写操作拒绝后不改稿、不新启动，并通过原失败隔离阻止同轮换工具补做。新输入重新计算标记，旧回调不污染新输入；可信网页和本地控制不受这层语言检查约束。

**只在完全空闲时拒绝否定句的误停。** 任一通道活动、序列运行／等待或狂暴模式活动时，合法全停始终执行；未识别到否定类别时同样沿用原全停。BOOT 和可信本地／网页停止保留。语音“不要停止当前序列”被模型误选为 stop 的问题，在活动状态下仍须由模型／平台解决，不能声称本项已经修好。

检查与停止在原控制锁内完成。远端停止回调使用内部来源常量区分可信停止，不为它分配额外参数容器；真正的停止仍先关闭输出，再分配回执。原 SDK 参数检查拒绝外部注入内部字段。

## 迟到停止反例与撤回的初版

初版试图同时拒绝活动状态下“不要停止”的误调用。追加回放发现：STT“停止” → 新 STT“不要编排表演” → 前一句的合法 stop 晚到，会被当前文本标记挡住，输出继续。当前 MCP 入口只有请求编号、工具名和参数，没有原始语句编号，不能据最新文本判定这个 stop 一定属于新一句。

因此不采纳活动停止拒绝。最终候选保留一切活动／等待状态下的全停；[初版在最终 46 案例中的五项失败](evidence/ct71-negative-input/rejected-prototype.json)保留，包括迟到请求、步骤等待和负面表述。初版只用于无设备主机研究，没有部署或物理输出。[初版控制源码快照](evidence/ct71-negative-input/rejected-prototype-tools.cc.txt)

这不是通过缩小测试让同一行为过关：原模型语义与停止要求保持，新增反例永久进入检查；当前设备只完成空闲草稿保护和否定新写入，活动否定句仍列为未完成。后续需要平台提供可信的原始输入关联，不能让模型自己填写编号来授权动作或拒绝停止。

## 软件与平台证据

| 验证 | 结果与限制 |
|---|---|
| 最终实际 MCP 矩阵 | [46/46](evidence/ct71-negative-input/native.json)，[ASan／UBSan 同矩阵](evidence/ct71-negative-input/native-asan.json)也通过；输入与时钟模拟 |
| 旧 ct70 同矩阵 | [23 项不满足新约束](evidence/ct71-negative-input/baseline.json)，主要为否定写入和空闲误取消 |
| 真正停止、分配失败、BOOT | 扩展实际 Reply 测试与原八组调度通过；所有否定类别下活动停止先关输出，回执分配失败不恢复；不等于机械停止测量 |
| 原 80／8 预期语义夹具 | 合法请求与并发版本门槛通过，不是新模型成绩 |
| 两轮十二条合成普通话 | 24/24 结束、转写 24/24、严格工具 23/24、同观察时刻控制状态 24/24 |
| 在线实际拒绝 | 第一轮 G002“不要饭店。”误调 stop，返回 `input_negated`；模型仍记失败，没有新启动或清稿 |
| 真实 STT 中的明确停止 | 没有被本项拒绝；与上述迟到／等待原生反例分别报告 |

两轮按[预先计划](evidence/ct71-negative-input/plan.json)各采一次，不替换失败。输入为合成 Opus，经灵矽真实 STT 驱动固定实际 MCP 主机；没有真人拾音或设备动作。[十二条语料](negative-input-cases.json) · [逐条转写、回执与回复审阅](evidence/ct71-negative-input/platform-review.json)

采集使用初版固定主机，随后因迟到反例修正活动停止逻辑。捕获二进制与最终二进制独立记录；最终候选对这 24 条**实际收到的**输入、完整 RPC 回执和终态重放一致，不能把它说成重新采集过最终版。最终停止边界由 46 案例及分配失败测试证明。原始记录和捕获身份未改写，也没有补采替换。[主机与契约摘要](evidence/ct71-negative-input/contract-check.json)

本批仍有停止确认；G010 仍输出英文操作文字和规则分析。23/24 的定向工具分数不替代原八十条／八条固定集、成功静默或家庭指标。平台只读回读为原 5991 字符角色、DeepSeek 和原参数，未保存配置。[平台核对](evidence/ct71-negative-input/platform-readback.json)

最终[十七组软件检查](evidence/ct71-negative-input/software-checks.json)含 98 项 Python 测试通过。完整 ESP-IDF 5.5.1 编译为 2,717,664 字节；ct71 与最近记录 ct45 的本地镜像分别回读哈希，见[版本检查](evidence/ct71-negative-input/version-check.json)。没有设备刷写。

## 复现

```sh
python3 scripts/check_negative_input.py --executable /path/to/final/firmware_host --output output/negative-native.json
python3 scripts/review_negative_input.py \
  --directory docs/validation/evidence/ct71-negative-input \
  --executable /path/to/capture/firmware_host \
  --classifier /path/to/negative_input_probe \
  --final-executable /path/to/final/firmware_host \
  --output output/negative-platform-review.json
```

探针由 `negative_input_probe.cc` 按 C++17、`-Ifirmware/esp32-audio` 编译。完整重放需相同摘要的主机与 checkout；原始语音内容不入库，只保留转写、事件和编码摘要。下一步继续处理未知表达、活动否定与原句关联、过程播报及原固定集，设备时序、真实扬声器、物理停止和家庭体验另验。
