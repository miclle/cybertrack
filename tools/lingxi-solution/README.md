# 灵矽离线参考包

在仓库根目录运行 `python3 scripts/package_lingxi_solution.py`，生成的 ZIP 位于 `output/lingxi-solution/`。文件由[打包清单](files.json)选取，包含角色、设备契约、采集模板以及历史评分所需的语料和回放。

解压后从 `START_HERE.md` 进入，在解压目录执行 `python3 scripts/review_lingxi_reference.py`。程序先核对文件摘要，再按各轮原始输入复算成绩；返回码 0 表示与原记录一致。报告保留超时、漏停、禁止调用和转写偏差。旧编排用例仅用于复算当时的固件。

v2 的工具、角色、样机版本与待补实测见[当前状态](../../docs/current-status.md)和[验收矩阵](../../docs/verification-plan.md)。
