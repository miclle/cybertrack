# 技术资料索引

更新日期：2026-10-25。公开技术链接用于器件与平台核实，不代表已完成接入或实物验收。厂商资料保留其原始权利与版本。

## 官方在线资料

| 编号 | 来源 | 本次用途与限制 |
|---|---|---|
| S01 | [灵矽设备接入](https://linx.qiniu.com/docs/xrobot/platform/) | 官方协议导航；已查阅 |
| S02 | [OTA 网关](https://linx.qiniu.com/docs/xrobot/platform/OTA) | 上报、激活及获取连接参数；已查阅，未调用 |
| S03 | [WebSocket 协议](https://linx.qiniu.com/docs/xrobot/platform/websocket) | WSS、握手、音频与消息；已查阅，未联调 |
| S04 | [端侧 MCP](https://linx.qiniu.com/docs/xrobot/mcp/hardware-mcp) | 设备工具发现与调用；已查阅，不是已注册能力 |
| S05 | [DFRobot DRI0002](https://wiki.dfrobot.com/dri0002) | 已退出选型的 DF-MD 历史资料；不用于当前 L298N 整板接线 |
| S06 | [ST L298 数据手册](https://www.st.com/resource/en/datasheet/l298.pdf) | 芯片电气与热边界；已查阅，不代替整板额定能力 |
| S07 | [ESP32-S3 官方产品资料](https://www.espressif.com/en/products/socs/esp32-s3) | 芯片与开发资料入口；已检索，采购指定 N16R8 Type-C 焊针版，实物修订和对应走线未核实 |
| S08 | [ESP32-S3 硬件设计指南](https://documentation.espressif.com/esp-hardware-design-guidelines/en/latest/esp32s3/index.html) | 后续板卡、电源和引脚核对入口；已检索，未完成板级设计 |

供应商页面可能更新。实现时重新核对相关协议／版本并记录变化，不全文镜像在线文档。商品“1000KV”没有可靠输出规格支撑，本项目不把它作为已核实的电压额定值。

## 本地资料

| 入口 | 内容 | 证据级别 |
|---|---|---|
| [硬件采购清单](../hardware/procurement.md) | P01–P13 商品名称、链接及待补采购信息；P13 为新驱动板 | 2026-10-23 已读十项页面，2026-10-25 补读 P13；P07 实物／ROM 核对另列，商家参数与实物验证分开；P08 淘宝详情被站点策略拦截 |
| [ESP32-S3 N16R8](../hardware/components/ESP32-S3-N16R8/README.md) | 原理图、44 针表、图纸尺寸与[实物核对](../hardware/components/ESP32-S3-N16R8/physical-verification.md)：照片、实测外形、双 USB、ROM 识别及无负载启动／PSRAM 读写 | 区分供应商标称、用户测量、照片观察与设备读回；完整电气／安装验收未完成 |
| [37R-520](../hardware/components/37R-520/README.md) | 参数、尺寸、编码器、联轴器与支架图片 | 商家图片标称；未重新实测 |
| [何健弓 L298N](../hardware/components/L298N/README.md) | H03／P13 当前选型、商品页核对及接口迁移边界 | 用户指定，已核对商品选项；详情混有 TB6612，整板规格和实物待核 |
| [DF-MD 台架历史](../firmware/esp32-motor-bench/df-md-history.md) | 已退出选型，保留旧板故障及试验记录；原始 PDF／图片从当前工作树移除，可从 Git 提交 `163fa48` 查阅 | 旧板记录不作为当前 L298N 规格或通过证据 |
| [track-mount](../hardware/components/track-mount/README.md) | FCStd、STEP、图片和尺寸 JSON | 已有测量记录与形状假设；本次未重新测量 |
| [泡泡枪主体](../hardware/components/bubble-gun/README.md) | 2026-10-24 用户提供枪口最外端 Ø31.5 mm、总高 35.8 mm、总长 67 mm；4 张原图、结构化尺寸及图片 SHA-256 | 用户提供尺寸与实物照片；未从图片推算接口；已建独立模型及0.18整体圆环与阶梯槽、两枪上仰5°候选；新增6×25×6.8后薄片、枪口底离平面4.7及前10宽槽记录，高度差0.4未消解，实物适配未验收 |
| [资产校验清单](../hardware/reference/assets.json) | 部件资料文件的 SHA-256 | 可检查文件完整性，不证明参数正确 |

2026-10-23 的[采购网页核对记录](../hardware/procurement-web-review.md)汇总选项、参数、来源冲突和设计影响；[原图／说明书来源清单](../hardware/reference/procurement-2026-10-23/sources.json)记录 18 个新保存文件及 SHA-256，独立于既有部件校验清单，不覆盖只读资产。P07 页面 PDF 已核对为芯片规格书 v2.2；P11 商品页说明书的单路／多端额定输出已读取，实物仍未验收。

[初始化检查快照](https://github.com/miclle/cybertrack/blob/c25b0af729bd216b69779db2bba75f32f9475cdd/docs/initialization-check.json)为 2026-10-23 的历史快照，文件内标明对应 Git 提交；其中路径、哈希和检查结果不代表当前工作树状态。

原始图片中的厂家名称与器件型号按原资料保留。
