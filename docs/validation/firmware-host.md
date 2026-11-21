# 固件主机验证

在主机上验证 ct79 的九个工具、请求分发、参数校验、回执和停止逻辑。时钟、测距和 IO 由主机模拟。实际平台选用哪个工具、扬声器是否播报、履带何时停稳，需要分别采集。

准备与候选版本一致的小智源码后，在仓库根目录运行：

```sh
python3 scripts/build_firmware_host.py --source build/xiaozhi-ct79-src --output build/ct79-full-host
python3 scripts/check_no_theatre.py --executable build/ct79-full-host/firmware_host --output output/validation/ct79-refusals.json
python3 scripts/replay_stop_matrix.py --source build/xiaozhi-ct79-src
```

核对源码、角色与本地镜像的身份见[统一软件检查](../current-status.md#统一软件检查)。ct79 构建记录中，退役请求与停止共 28 例，停止矩阵覆盖 13 类场景各 5 个触发时刻。[ct79 构建与回归](../../firmware/esp32-audio/verification-ct79.json)

平台转写与模型工具选择的检查方法见[灵矽隔离联调](lingxi-capture.md)。
