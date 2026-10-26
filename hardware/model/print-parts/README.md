# 0.51 六组合并打印候选

**当前剩余四件打印包：** PP02 与 LC04 已修复；PP01、PP02、PP03、LC04 组成新增第 5 盘，见[独立 STL／STEP、方向与检查](../remaining-print/README.md)。PP02 本目录 STL／STEP 已同步为底板贴床方向，原 PP02.png 和旧图册保留历史孔形。

## 当前头部打印：0.58

新增 [PP07 头部下壳 STL](PP07-HeadShell.stl)，34 个原特征＋14 处连接整体打印，开口向上；配套更新 [PP05 冠盖 STL](PP05-Crown.stl)。用户现有 Ø2.5、含帽总长8.6、帽Ø3.9×1 mm 螺丝用于冠盖和托盘，共8颗，Ø2.1导孔先试拧。先打印 [导孔试件](Head-ScrewFitCoupon.stl)，详见[头部打印说明](../../../docs/head-shell-print.md)及[切片配置](PP07-slicing/README.md)。底盘未改。下文六件基线的“无朝向”“PP05几何保持”及旧图册均不覆盖本次更新；旧合并报告哈希保留历史状态，当前 PP05／PP07 使用[新报告](../head-shell-print-audit.json)。

**历史 PP02 调整（后续已修复干涉，见上方当前交付）**：Ø32 mm 偏心孔、孔心上移 1.3 mm、底部 7.5 × 2.3 mm 缺口、20 mm 宽支脚，删除近侧前长槽壁和前横挡块。其余打印件保持。最新尺寸与配合限制见[调整说明](../../../docs/print-consolidation.md)及[报告](../pp02-adjustment-audit.json)；此版曾与枪体模型相交，当前孔形由后续打印修正替代。

仅测试电机与履带装配时，可使用独立的 [VF01 省料验证框架](../drive-fit-fixture/README.md)：174 × 80 × 41.6 mm，CAD 实体体积比 PP04 少约 71.7%。它不替代正式底盘，也不验证完整底盘的刚度或承载。

完整说明见[合并设计](../../../docs/print-consolidation.md)，回读与来源映射见[检查报告](../print-consolidation-audit.json)，[图册](print-parts.pdf)展示六件外形。

| 编号 | 打印件 | STL | STEP |
|---|---|---|---|
| PP01 | 水枪底托 | [STL](PP01-WaterCradle.stl) | [STEP](PP01-WaterCradle.step) |
| PP02 | 泡泡枪底座 | [STL](PP02-BubbleCradle.stl) | [STEP](PP02-BubbleCradle.step) |
| PP03 | 双瓶背包及桶座 | [STL](PP03-Backpack.stl) | [STEP](PP03-Backpack.step) |
| PP04 | 底盘及湿舱隔板 | [STL](PP04-LowerTub.stl) | [STEP](PP04-LowerTub.step) |
| PP05 | 冠盖及装甲饰件 | [STL](PP05-Crown.stl) | [STEP](PP05-Crown.step) |
| PP06 | 固定颈架 | [STL](PP06-Neck.stl) | [STEP](PP06-Neck.step) |

每件一个连通实体；STL单位按mm生成，XY居中、最低点Z=0，仍保留整机轴向。没有确定最佳打印朝向、支撑或材料参数。网格线性偏差0.08 mm、角度偏差0.15 rad；导出后检查封闭性、非流形边及与CAD壳数一致的边界分量。PP04含两处原有封闭内腔，具有三个闭合边界分量，但仍为一个连续打印实体。仅供切片和试配准备，不代表制造放行。

FCStd内的六个PP一级零件保存同一几何；主模型只保留履带动力分组。原融合输入及59个隐藏检查空间从主模型清除，保存在独立[设计源档](../source/CyberTrack-design.FCStd)供追溯，不要重复打印。本目录仅覆盖六组合并件，不是全机打印包。STEP可能存在曲面交换差异，以原生FCStd为几何依据。

本次独立STEP回读中，PP03背包体积差约34.687 mm³、PP05冠盖约4.358 mm³，超过0.01 mm³比较阈值，不能视为原生曲面等价。打印使用直接从原生实体生成并验证的STL；精确几何以整机FCStd内对应融合件为准。

0.53电源开关安装座属于六件合并范围之外的折面顶盖，已在整机中更新；本目录PP01–PP06的几何保持，见[安装说明](../../../docs/power-switch.md)。

0.55：PP06中央基座/鞍座随15芯净径10通道更新；PP06 STEP/STL和预览已同步，其他五件保持。见[通道专项](../../../docs/cable-passage.md)。这不关闭PP02既有配合冲突，也不构成制造放行。

## L298N 局部试配件（0.57）

[紧凑支架目录](../l298n-compact/README.md)另行提供 LC01 托架、LC02 上压框、LC03 更新底盖及 LC04 更新顶盖的 STL／STEP。它们不改动本目录六个 PP 合并件；本轮未切片，实物夹持与线束维护待试配。

## PP04 底盘打印配置（2026-10-26）

已切片 3MF（历史中间文件 `PP04-P2S-PLA-0.24.3mf`，已清理） 已设置 P2S／0.4 mm／PLA、0.24 mm 层高和普通自动支撑，预计 5 小时 20 分钟、174.71 g。仅含底盘主体及湿舱隔板，底盖与 L298N 支架需另行打印。配置、检查范围及限制见 [打印说明](PP04-slicing/README.md)。

PP04 当前推荐 时间优化版 3MF（历史中间文件 `PP04-P2S-PLA-FAST.3mf`，已清理）：0.24 mm、3 层墙保持，预计 4 小时 49 分钟、161.07 g；比原版快约 31 分钟。对比 16 组参数，选用贴合式普通支撑及较宽内部填充线，详见[检查与限制](PP04-slicing/README.md)。

## 底盘配套件共盘

14 件共盘打印项目（历史中间文件 `Accessories-14parts-P2S-PLA-FAST.3mf`，已清理） 已排入底盖、L298N 托架与上压框、电池托板、左右侧框、固定颈架、左右肩梁、线束桥及 4 个控制板压框；预计 4 小时 58 分钟、148.42 g。PP06 已包含，**不要重复打印独立 PP06**。清单、朝向及检查见[共盘说明](../l298n-compact/slicing/README.md)。

## 头部三件快速打印包

[头壳＋冠盖＋面包板托盘](PP07-slicing/head-set-speed/README.md)已全部优化：头壳一盘4小时9分，冠盖和托盘共盘3小时24分，合计约7小时33分、308.39 g。冠盖四螺丝座局部实心／4墙、托盘3墙，保持已有装配几何；单件版也保留，避免与共盘版重复打印。

当前统一打印入口：[34件／6盘项目](../print-ready/README.md)，已在Bambu Studio打开；采用PLA Basic重新切片，底盘3小时59分、配套件4小时17分、头壳4小时9分、冠盖与托盘3小时24分。此前独立版保留作为比较，不重复打印。

2026-10-26 全机清单复核所发现的遗漏已补齐；护口按用户要求取消，见[第 6 盘与装配说明](../completion-print/README.md)。
