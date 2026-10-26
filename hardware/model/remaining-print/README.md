# 剩余四件：打印准备

2026-10-26。PP01 水枪底托、PP02 泡泡枪底座、PP03 背包、LC04 顶盖共用新增第 5 盘，合入[五盘项目](../print-ready/CyberTrack-Ready-5plates.3mf)。原四盘的模型、工艺设置和 G-code 保留，不需重打。

| 零件 | 打印方向 | 独立导出 |
|---|---|---|
| PP01 水枪底托 | 取消装配倾角，底板贴床 | [STL](PP01-base.stl)／[STEP](PP01-base.step) |
| PP02 泡泡枪底座 | 取消装配倾角，底板贴床、圆环竖立 | [STL](PP02-base.stl)／[STEP](PP02-base.step) |
| PP03 背包 | 竖放，开口向上 | [STL](PP03-base.stl)／[STEP](PP03-base.step) |
| LC04 顶盖 | 翻面，柱子朝上 | [STL](LC04-flipped.stl)／[STEP](LC04-flipped.step) |

第 5 盘预计 **5 小时 24 分、264.39 g**，为切片估算。P2S／0.4 mm／PLA Basic／纹理 PEI；0.28 mm 层高、3 墙、10% cubic、顶底各 4 层、3 mm 外侧 brim。背包、顶盖、泡泡枪座采用 0.6 mm 墙线与 Arachne；水枪底托保留 0.5 mm 经典墙线，避免薄壁路径覆盖下降。普通贴合支撑，4 mm 底部间距、0.2 mm 顶部接触间隙，允许从模型表面生长。

比较了背包竖放／背放、顶盖正放／翻面／两个倾角、树状／普通支撑及经典／Arachne 墙线。背包背放耗料和时间均增加；树状支撑顶盖明显更慢；倾斜顶盖虽然可省料，但不如翻面快。最终按零件混合墙线参数。统一 0.6 mm 经典墙线、统一 Arachne 等候选未通过部分截面的覆盖保持筛查，不作为交付版本。各候选和失败记录见 [slicing](slicing/)，最终结果见[合并后切片](slicing/merged-validation/result.json)。

## 两处几何修正

- PP02：原 Ø32 偏心孔与枪壳相交 65.11 mm³。在保持 Ø39 × 3 外环、孔位、20 mm 支脚及枪体位置的基础上，加同心 Ø32.8 下缘避让。上半部保留原偏心孔形，下半部为复合孔形；静态枪壳最小间隙 0.65 mm。原缺口底面仍为局部 Z93、宽 7.5 mm；新增避让后，不能再将整个孔口称为单一 Ø32 圆孔或将下缘可见缺口深度统称为 2.3 mm。
- LC04：原两根悬空安装柱通过两根 3 mm 内向筋与顶盖连接，3 个实体变为 1 个。原安装孔不动；连接筋绕开底盘和肩梁并留 0.3 mm 轴向避让预算。

[原生几何审计](geometry-audit.json)核对四件均为有效单实体、当前安装位置无实体／设备包络相交，STL 封闭且单连通、各打印 STEP 回读一致。源档其他 432 个对象及交付模型其他 267 个对象签名保持。整机 STEP 回读有效、847 个实体数量一致，但存在 55.61 mm³ 总体体积差，仍以 FCStd 和本次独立打印导出件为几何依据，见[整机 STEP 记录](assembly-step-readback.json)。

[泡泡枪相对底座的 102 个离散拆装姿态](bubble-service-check.json)无相交；这不等于整机线束、手部空间或实际枪体通过。完整装配、打印收缩、公差和强度仍待实物试装。

[路径检查](path-check.json)通过 33 个截面，包含两根新增筋；普通填充区域按基线覆盖比较，不能把 10% 填充内部误判为缺料。[首层图](plate-5-preview.png)已查看，全部模型、支撑和 brim 路径位于 256 × 256 mm 平台内，切片警告为空且执行了路径碰撞检查。没有发送打印指令。

## 复现与保留

`prepare_remaining_geometry.py` 在 FreeCAD Python 中局部修正、导出并保存回读；`slice_remaining_prints.py` 生成独立候选；`export_remaining_sections.py` 与 `check_remaining_paths.py` 核对原生截面与路径。`preserve_current_prints.py` 验证 Bambu Studio 当前快照并恢复其 Save As 省略的原四盘 G-code；`append_remaining_plate.py` 追加新盘；仅用 CLI `--slice 5` 检查新增盘，最后 `finalize_remaining_project.py` 写入已检查的第 5 盘路径。图像和路径检查脚本需要 Pillow。首轮修改前的 FCStd 保留在 `baseline/`，不覆盖或提交其他任务修改。
