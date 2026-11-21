# 灵矽离线参考包

在仓库根目录运行 `python3 scripts/package_lingxi_solution.py`，生成的 ZIP 位于 `output/lingxi-solution/`。文件由[打包清单](files.json)选取，包含角色、设备契约、采集模板以及历史评分所需的语料和回放。

解压后在包根目录执行 `python3 scripts/review_lingxi_reference.py`。程序核对文件摘要，复算历史 80／8 固定集和合成语音成绩。返回码 0 表示复算结果与原记录一致，报告仍会列出当时的超时、漏停、禁止调用和转写偏差。旧编排用例仅用于复核对应版本。

五组文本回放分别覆盖原角色基线、ct57、ct61 固件主机、精简回执和停止否定句。合成语音另有 ct62 的 20 条口述用例和 ct71 的完整固定集。已退役的模型参数与角色对照可在[清理前的证据目录](https://github.com/miclle/cybertrack/tree/a83b000b3f24f48fcd89a3bdc58b370b2c6e0e2e/docs/validation/evidence)查阅。

v2 的工具、角色、样机版本与待补实测见[当前状态](../../docs/current-status.md)和[验收矩阵](../../docs/verification-plan.md)。
