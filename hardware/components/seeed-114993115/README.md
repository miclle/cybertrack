# Seeed 114993115 · OV5640 AF

v2 下一版单主板量产设计选定此料号，右前脸使用带长排线的自动对焦版本。产品页列有 7 × 6 × 7 mm 和 14 × 14 × 7 mm 两片散热片。本次使用小片，贴合位置、胶厚与封闭头舱热表现待验。[Seeed 产品与采购](https://www.seeedstudio.com/OV5640-Camera-for-XIAO-ESP32S3-Sense-With-Heat-Sink-p-5739.html) · [Seeed 实例](https://wiki.seeedstudio.com/xiao_esp32s3_camera_usage/)

按 100 台试产核对供货时，DigiKey 将 114993115 列为 Active，公开库存快照超过 100 件；Seeed 原厂页面列价 US$11.99 并提供批量询价。采购按同一 SKU 和承认书版本确认排期、批次可追溯性与变更通知，长期供货承诺待取得。[DigiKey 料号与供货状态](https://www.digikey.com/en/products/detail/seeed-technology-co-ltd/114993115/21277047) · [Seeed 原厂采购](https://www.seeedstudio.com/OV5640-Camera-for-XIAO-ESP32S3-Sense-With-Heat-Sink-p-5739.html)

乐鑫给出的 ESP32-S3 搭配 OV5640 DVP 的 JPEG 采集参考值为 1600 × 1200、25 fps。整机优先用 VGA JPEG 和 PSRAM 双缓冲做按需预览，首板目标为室内手机端 ≥15 fps。在语音、履带与超声波并发时实测帧间隔、近远合焦、弱光画面和闭盖温升。[乐鑫性能表](https://docs.espressif.com/projects/esp-techpedia/en/latest/esp-friends/solution-introduction/camera/dvp-mipi-csi-camera-solution.html)

随附原始资料为 Seeed 产品页链接的 MJY5OAF-F3M-V1 承认书，图纸版本 V1，2023-06-20。第 3 页列模组尺寸、端子视图和针序。模组头部 8.5 × 8.5 mm，两边公差各 ±0.2 mm，总高 5.4 ±0.2 mm。从模组外缘到插端总长 70.5 ±0.2 mm，排线主体宽 6 ±0.1 mm、厚 0.12 ±0.03 mm，插端宽 12.5 ±0.1 mm、带补强总厚 0.30 ±0.03 mm。24 针、节距 0.5 mm。图纸给出的对焦距离为 100 cm–∞，近于 1 m 的对焦效果另以实测确定。镜头视场标称 69°，图纸未说明测量方向。建模用的框体分层、镜头直径、最小弯曲半径、ZIF 外形和接触方向均需用对应批次物料确认。[原始 PDF](Seeed-OV5640-MJY5OAF-F3M-V1.pdf) · [厂商文件](https://files.seeedstudio.com/wiki/OV5640_for_ESP32S3_sense/OV5640_Datasheet.pdf)

原件 SHA-256 为 `f677aba51191314f4629da74713f8177bc09c68e9623528d395f79d623a7d896`。第三方资料权利归原权利人。[结构试装](../../model/studies/front-camera/README.md) · [主板接口核对](../../pcb/camera-dvp.md)
