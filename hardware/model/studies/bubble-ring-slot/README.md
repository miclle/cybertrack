# 前圆环独立初稿（已由0.18整体圆环方案替代）

2026-10-24 用户要求用前圆环和后端固定槽取代0.16的前托垫／后压盖。后端底部薄片尺寸为宽6、长25、高6.8 mm，见[原始记录](../../../components/bubble-gun/mounting-tab-dimensions.json)。

当前只完成[前圆环独立候选](FrontRing-candidate.FCStd)及[STEP](FrontRing-candidate.step)。上下两半可分开，让不规则枪身从上方装入；枪口直径31.5为用户输入。圆环内径32.1、外径37.1、轴向厚5、分缝0.3、两处孔径3.2均为设计候选，名义径向间隙0.3 mm，不代表夹持力或实物配合已验证。

[回读记录](front-ring-readback.json)确认两半有效、相互无体积重叠、与名义枪口圆柱无重叠，原生与STEP回读通过。此文件使用独立局部坐标，并未装入整机，未进行整机干涉或拆装验收。

后槽可先以6.4 mm宽作候选，但其位置、长度方向及深度需要核对：薄片是否长25沿枪身前后、宽6沿左右、高6.8向下凸出；是否居中且与尾端齐平；6.8是否包含在总高35.8内。不能从照片比例补定这些关系。槽的防松、防脱和圆环接触材料也未确定。

整机主文件、32张视图及20页图纸仍保持此前完成检查的0.16版本。当前研究文件不覆盖部件原始模型；待定位输入确认后再更新整体几何、拆装路径及文档。

从仓库根目录运行：

```sh
PYTHONPATH=/Applications/FreeCAD.app/Contents/Resources/lib \
/Applications/FreeCAD.app/Contents/Resources/bin/python hardware/model/studies/bubble-ring-slot/build_front_ring.py
```

本研究保留为前环初稿；用户随后明确6.8不是额外下凸，补充4.7支承间距及前10宽槽。当前实现以[整机0.18](../../README.md)和[新部件记录](../../../components/bubble-gun/README.md)为准；本文件此前的待确认状态仅反映初稿当时输入。
