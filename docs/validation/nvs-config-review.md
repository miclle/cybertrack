# 离线核对部署前后的配置

[review_nvs_config.py](../../scripts/review_nvs_config.py)将 ct75 的配置复核整理为可重复执行的工具，服务 I10 的部署交付。它只读取已有文件，不连接串口、网络或设备，也不写 Flash。输入可以是完整 NVS 分区，或包含 NVS 的等长快照；范围必须来自该设备的已核实分区表，工具不会猜测布局。

## 使用

依赖本机 ESP-IDF checkout 中的官方 `nvs_parser.py`，本次验证版本为 5.5.1。未内置 SDK，也不自动下载依赖；其他 SDK 版本须另行验证。配置快照含凭据，应保存在受限的本地忽略目录，不能加入 Git 或参考包。

```sh
python3 scripts/review_nvs_config.py \
  --idf-path /path/to/esp-idf \
  --before /private/path/before.bin \
  --after /private/path/after.bin
```

以上默认整个文件是 NVS。对于 ct75 部署保留的 128 KiB 前应用快照，已核实 NVS 位于 `0x9000`、长度 `0x4000`，追加 `--nvs-offset 0x9000 --nvs-size 0x4000`。这不是所有设备的通用偏移；范围外字节变化也会导致比较不通过。

默认不忽略任何逻辑值差异。人工审阅变化后，可分别追加 `--allow-runtime-change websocket/token` 或 `--allow-runtime-change phy/cal_data`；仅允许这两个既有字段的同类型值变化，新增、删除和其他用户设置变化仍不通过。不能为了得到成功返回码而自动加入例外，也不能仅因字段由 SDK 管理就推断变化正常。

| 返回码 | 含义 |
|---|---|
| 0 | 本次快照符合明确选择的比较策略；仍须查看 `changed_keys` |
| 1 | 发现策略未允许的变化，包括 NVS 范围外字节变化 |
| 2 | 输入、范围、解析器或数据完整性无法支持比较；不推断配置保持 |

报告包含字段名、计数、比较范围和解析器代码摘要，不输出配置值、配置值摘要或原始数据。解析器异常也不会原样回显。发布报告前仍须审阅字段名等元数据；工具不替代信息审阅。

## 比较规则与边界

- 校验页、条目及变长数据 CRC，拒绝截断、未知类型、重复有效记录和不完整的 blob。它是保守比较器，不模拟 NVS 启动恢复；中断写入、待擦除或歧义状态返回错误，需要另外调查。
- 按 blob index 指定的大小、块数和起始编号重组当前值。分块方式改变但内容相同，不记为逻辑值改变；校准内容变化则保留差异。物理条目数量与逻辑键数量分别报告。
- 仅支持未加密、可由已验证 SDK 解析的 NVS 页版本。文件相同、CRC 正确或策略匹配都不证明应用身份、启动成功、无线性能、物理输出或用户体验。
- `all_logical_values_unchanged` 和 `matches_policy` 分开。允许运行时变化后，后者可能为真而前者仍为假；不能把这两者都写成“配置全部未变”。

## 本次验证

[11 项测试](../../tests/improvements/test_nvs_config.py)用合成二进制调用真实 SDK 解析器，覆盖分块布局变化、校准内容变化、Wi-Fi 值变化、运行时键新增／删除、范围外修改、CRC 损坏、截断、未知命名空间、重复记录、缺失 blob 块，以及 CLI 返回码与值脱敏。

```sh
IDF_PATH=/path/to/esp-idf python3 -m unittest discover \
  -s tests/improvements -p 'test_nvs_config.py'
```

未设置 `IDF_PATH` 时，这组 SDK 测试会明确跳过，不能记为通过。本次在 ESP-IDF 5.5.1 上实际运行全部 11 项，未跳过。

原 ct75 前后快照离线重跑得到[默认严格报告](evidence/nvs-config-review/strict.json)与[显式例外报告](evidence/nvs-config-review/reviewed.json)：前后各 59 个逻辑项，变化仍为 `phy/cal_data` 和 `websocket/token`；范围外字节保持。严格返回 1、明确指定两项例外后返回 0，两个报告均保留 `all_logical_values_unchanged=false`。原始快照不公开，公开合成夹具用于复现比较规则，不能冒充复算原始设备数据。

这是对[ct75 部署](ct75-deployment.md)同一份快照的离线复核，不是新部署或新采样；不覆盖原首次失败，也不改变无线校准更新原因未知的结论。记录见[验证摘要](evidence/nvs-config-review/verification.json)。
