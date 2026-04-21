# 财务统计小工具 V2.1

基于 `Python + PySide6` 的 Windows 单机财务汇总工具。

## 安装依赖

```bash
pip install -r requirements.txt
```

## 启动

```bash
python main.py
```

## WPS 在线映射 CLI

推荐入口：

```bash
python tools/mapping_sync_cli.py status
python tools/mapping_sync_cli.py auth
python tools/mapping_sync_cli.py preview --interactive-auth
python tools/mapping_sync_cli.py sync --interactive-auth
python tools/mapping_sync_cli.py set-file-id <file_id>
```

兼容旧入口：

```bash
python tools/wps_mapping_sync_cli.py status
```

说明：
- `auth` 用于首次执行 `open.wps.cn` / `openapi.wps.cn` 用户授权。
- `preview` 用于预览 `正式映射` 工作表前几行。
- `sync` 会把 WPS 在线映射覆盖到本地缓存。
- `set-file-id` 用于手动写入 `wps_file_id`，绕过 `kdocs.cn` 私有短链无法解析文件元信息的问题。
- 默认本机回调地址为 `http://127.0.0.1:18765/callback`。
- 需要应用已开通 `kso.sheets.read`；如果要通过分享链接解析文件，还需要 `kso.file_link.readwrite`。

## 当前已实现

- 三页主窗口：`账单统计 / 分类映射 / 异常消息`
- 主窗口和目录选择
- 配置持久化
- 文件扫描
- 文件名解析
- 来源识别
- 淘宝系 / 天猫 / 淘工厂 / 淘农场 / 拼多多 支持 `CSV` 与 `XLSX/XLS`
- 金额标准化
- 自动过滤收入和支出同时为空或为 `0` 的空记录
- 分类映射
- 未匹配映射自动归类为 `暂未分类` 并弹窗提醒
- 大数据量后台处理与进度显示
- 异常信息支持复制选中 / 复制全部
- WPS 在线映射手动同步入口
- WPS 云端映射版本检查
- 软件内可直接填写 WPS 分享链接 / `file_id` / 工作表名
- 分类映射本地编辑、保存并上传云端
- 按月份 / 店铺 / 平台 汇总
- 导出 `总汇总表`

## 注意

- 当前版本主路径使用 `open.wps.cn` / `openapi.wps.cn`。
- 若在线文档是 `kdocs.cn` 私有短链，WPS OpenAPI 可能无法直接从分享链接返回 `file_id`，此时需要手动写入 `wps_file_id`。
- 未命中分类规则的记录会进入汇总表，分类显示为 `暂未分类`。
