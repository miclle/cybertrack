# 普通多 Wi-Fi 配置

ct40 已部署，增加 OLED 待机内网地址显示，换网后更新、断网后清除，手机访问时加上 `http://`；两组 Wi-Fi 及全部既有 NVS 记录在首次启动后回读保持一致，见[屏幕地址规则与验证](lan-control.md#屏幕上的内网地址ct40)。

2026-10-30 Wi-Fi 顺序功能部署基线为 `2.0.3-ct39-wifi-order3`，按配置文件导入的保存顺序尝试网络。修正第一组热点信息后，三次实机启动依次为：第一组成功、第一组认证阶段超时（reason 2）后回退第二组、第一组再次成功；最终连接第一组并进入正常待机。两组配置回读匹配。见[构建验证](../firmware/esp32-audio/verification-ct39-wifi-order3.json)和[部署记录](../firmware/esp32-audio/startup-ct39-wifi-order3.json)。热点重连仍有偶发超时，不能宣称每次均成功。

在仓库根目录的 `secrets/wifi.json` 填写：

```json
{
  "networks": [
    {"ssid": "家里的网络名称", "password": "replace-home-password"},
    {"ssid": "手机热点名称", "password": "replace-hotspot-password"}
  ]
}
```

可复制 `firmware/esp32-audio/wifi.example.json` 建立此文件；已有文件不要覆盖。`secrets/` 已被 Git 忽略。本次建立的本地文件权限为 0600。

- 配置 1～10 组，SSID 不得重复。只支持普通网络，不支持企业账号认证或网页认证。
- 当前锁定组件使用定长缓冲区和 `strcpy`，因此本入口限制 SSID 为 1～31 个 UTF-8 字节；中文通常每字占 3 字节。
- 密码为 8～63 个可打印 ASCII 字符；开放网络填空字符串。不支持 64 位十六进制 PSK 输入。
- JSON 使用英文双引号；密码里的双引号和反斜杠分别写成 `\"` 和 `\\`。程序不会去掉名称或密码两端的空格。
- 列表顺序就是导入后的连接优先级：先尝试第一组，收到连接失败／断连事件后尝试下一组。同一 SSID 有多个接入点时，仅在该组内部按信号选接入点，每组只排一个候选；未扫描到的配置也会定向尝试，以覆盖隐藏名称等情况。所有候选失败后等待 10 秒重新扫描。启动总等待仍为 60 秒，超时进入配网；没有另外增加逐组 DHCP 或互联网连通性超时切换。

在仓库根目录校验，输出仅包含数量，不显示名称或密码，也不访问设备：

```sh
python3 firmware/esp32-audio/wifi_config.py secrets/wifi.json
```

填写文件不会自动生效。准备新的固件导出时显式传入文件：

```sh
python3 firmware/esp32-audio/prepare.py /path/to/original/xiaozhi-esp32 \
  --target build/xiaozhi-wifi-src --wifi secrets/wifi.json
idf.py -C build/xiaozhi-wifi-src -B "$PWD/build/firmware-wifi" build
```

沿用音频工程的 Python、ESP-IDF v5.5.1 和原始源码缓存要求；导出目录必须尚不存在。不传 `--wifi` 时保持原构建行为。带配置的固件版本当前追加 `-wifi-order3`，同时应用顺序连接补丁；不传 `--wifi` 的默认导出仍保留上游连接策略。

获授权刷入带配置的固件后，启动时在读取已保存网络前，将文件中的完整列表写入 NVS 的 `wifi` 命名空间，**替换原有已保存网络列表**；只改网络名称、密码槽位和本功能标记，保留其他配置。全部列表提交成功后才记录配置指纹，中断或失败会在下次启动重试。同一份配置再次启动或重新刷入时不覆盖网页配网的后续修改；更改文件内容并重新构建、刷入后才再次导入。清除 NVS 后会重新导入。实际优先级读取 NVS 中的保存顺序，网页配网的置顶操作也会调整它；连接成功后保持当前网络，不因更高优先级网络出现就主动切走，掉线重新扫描时从第一组开始。

真实凭据会存在于本地 JSON、忽略的导出头文件、构建产物及设备 NVS 中。头文件权限为 0600；生成头文件、固件及其构建产物不能提交或公开发布。配置指纹只用于识别版本，不是凭据加密。

验证：`python3 firmware/esp32-audio/tests/test_wifi_config.py` 覆盖输入校验、导出版本、中文与特殊字符、NVS 列表替换、其他键保留、重启幂等及提交失败后重试。`python3 firmware/esp32-audio/tests/run_wifi_order_tests.py --source build/xiaozhi-ct39-wifi-order3-src` 执行实际导出的连接方法，覆盖第一组弱于第二组、同名多接入点、失败回退、断线重扫、不可见／空扫描的定向连接以及保存顺序变化；order3 的实际导出源码已通过该测试。

修正后的真实配置已通过 ESP-IDF v5.5.1 完整构建。刷写前核对设备、验证并备份旧应用，备份前 128 KiB 配置区；随后只更新应用并校验哈希，首次启动前配置区逐字节保持。启动后 NVS 回读两组名称、密码及配置标记匹配，CRC 正常；NVS 外区域保持，其他 NVS 项仅有既有启动激活流程刷新 WebSocket 令牌。

实机三次均首先尝试第一组。第一、第三次取得第一组热点的 IP 并完成激活进入 idle；第二次第一组返回 AUTH_EXPIRE（reason 2），随即回退第二组并进入 idle。在第二组网络上，11 份状态／停止／释放回执均为逻辑输出关闭、动作启动数 0，网页与仓库一致；在第一组手机热点上，电脑无法访问设备 HTTP 接口，采用串口确认版本、初始化输出低电平、联网与 idle，不将第二组的 HTTP 回执视为第一组的检查。配置修正前，另已记录第一组返回 NO_AP_FOUND（reason 201）后回退第二组的场景，见[此前记录](../firmware/esp32-audio/startup-ct39-wifi-order2.json)。

待验：第一组热点反复重连稳定性、连接建立后的断网切换及停止、物理断电保留、修改网页配网后再重启。私有固件及备份保留在忽略的 `build/` 中，不提交凭据；本轮未修改平台角色或发送执行器启动命令。
