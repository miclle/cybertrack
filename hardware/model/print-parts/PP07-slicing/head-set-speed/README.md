# 头部三件快速打印交付

2026-10-26。接续“规划模型整体打印方案”会话，按用户要求以结构保留和缩短打印时间为目标。使用本机 Bambu Studio 02.08.04.57、P2S 0.4 mm 标准喷嘴、Bambu PLA Basic、纹理 PEI；沿用已确认的耗材，体积流量上限21 mm³/s。以下均为切片估算。

## 直接打印文件

| 盘／独立件 | 已切片文件 | 预计时间 | 耗材 |
|---|---|---:|---:|
| 盘1：PP07头壳 | 头壳快速版（历史中间文件 `PP07-P2S-PLA-Basic-wide-fast.3mf`，已清理） | 4小时9分24秒 | 154.35 g |
| 盘2：PP05冠盖＋面包板托盘 | 两件共盘（历史中间文件 `Head-Crown-Tray-PLA-Basic-FAST.3mf`，已清理） | 3小时23分52秒 | 154.04 g |
| 可选：冠盖单独 | 冠盖快速版（历史中间文件 `PP05-Crown-PLA-Basic-FAST.3mf`，已清理） | 2小时55分8秒 | 122.73 g |
| 可选：托盘单独 | 托盘快速版（历史中间文件 `Head-Tray-PLA-Basic-FAST.3mf`，已清理） | 35分54秒 | 31.31 g |

推荐两盘合计约 **7小时33分、308.39 g**。共盘为同一耗材／颜色，按层打印；如需冠盖与托盘不同颜色，使用两个独立文件。共盘较两件分开约节省7分10秒。不要把独立版与共盘版重复打印。PP06颈架已在此前14件底盘配套盘中，不属于这里的三个件。

相对于原独立件基线，冠盖由7小时9分44秒降至2小时55分8秒，托盘由49分47秒降至35分54秒。托盘保留实心底层与安装耳，快速版比原版多约4.95 g；本轮优先缩短时间，并非所有单件同时最省料。头壳沿用已通过连接截面筛查的4小时9分宽线方案。

## 方向与结构设置

- 头壳：开口朝上，0.28 mm层高，两圈0.60 mm宽墙，8%立方体填充，单墙树状支撑；保留原已检查版本，不采用3小时57分但下颌连接覆盖不足的候选。
- 冠盖：装饰面朝上，0.28 mm、两圈名义0.60 mm宽墙、Arachne可变线宽、8%立方体、3层顶／底面。使用贴合式普通自动支撑、5 mm支撑基底间距；从开放底面清理。
- 冠盖四处螺丝承压座单独设置100%填充、4圈墙。每个修改区域10×10×3.3 mm，整机坐标X±64、Y−52／7、Z215.9–219.2；仅改变内部打印路径，不增加实体或填堵孔。导出后的实际填充类型为cubic，以3MF配置为准。
- 托盘：底面朝下，0.28 mm、3圈0.50 mm墙、5层顶／4层底面，保留2.5 mm底板和四安装耳。共盘通过对象设置保留这些参数，未被冠盖两墙设置覆盖。
- 共盘位置：冠盖中心(128,78)，托盘中心(128,199)，两件模型前后间距14 mm；5 mm brim，按层打印。

## 检查证据与边界

- 比较16组冠盖／托盘参数和朝向，见[comparison.json](comparison.json)。普通支撑显著减少冠盖树支撑耗时。未经局部加密的快速冠盖在部分螺丝座中间截面覆盖不足；倒置加密候选同样未通过，未交付。
- [交付检查](delivery-check.json)：两个正常打印网格与原始独立3MF的全部顶点／三角形逐项一致，STL哈希仍匹配原导出清单，四个额外体均为参数修改体；没有网格修复。实际装配外形与尺寸保持。
- [关键截面检查](delivery-critical-sections.json)：对原生CAD实际材料区按0.2 mm网格采样，排除孔、空腔和支撑，仅核对挤出线宽覆盖；冠盖4座×3高度、托盘4耳×2高度。每截面要求≥85%，且不比原基线低超过5个百分点。选用单件及共盘均通过，最低分别97.49%和98.72%。加密前失败截面见[记录](critical-sections-before-reinforcement.json)；当前交付截面报告单独保存。
- [头壳20处路径抽查](head-path-check.json)通过，原19组比较见[头壳记录](../speed-study/README.md)。
- [共盘切片结果](combined/result.json)：两件、无悬空警告，执行碰撞检查；首层含支撑及brim的挤出边界X44.947–211.053、Y11.308–248.692 mm，位于256×256 mm平台内。已检查[首层路径图](combined/first-layer-paths.png)与[排布预览](combined/plate-preview.png)。
- 截面覆盖是打印路径筛查，不是全层连通证明、标定强度或实物配合验收。螺丝试拧、支撑清理、层间强度和装配仍由首件验证；既有导孔试件说明保留。
- CLI日志里的`Invalid T command (T65535)`来自未改动的官方P2S结束模板；完整日志保留，不将切片成功等同于实机执行验收。本轮未向打印机发送任务。

## 复现

在仓库根目录运行：

```sh
python3 scripts/optimize_head_set.py crown-arachne-seats tray-wide
python3 scripts/compose_head_companions.py crown-arachne-seats tray-wide
/Applications/FreeCAD.app/Contents/Resources/bin/freecadcmd scripts/check_head_companion_paths.py
python3 scripts/check_head_print_paths.py hardware/model/print-parts/PP07-slicing/PP07-P2S-PLA-Basic-wide-fast.3mf hardware/model/print-parts/PP07-slicing/head-set-speed/head-path-check.json
python3 scripts/check_head_set_delivery.py
```

最后一个脚本需要Pillow。FreeCADcmd的退出码不能单独证明执行成功，必须检查输出JSON中各候选`passed`。本轮无需修改整机FCStd、重新导出几何或整体缩放模型。
