# Design: Desktop Finance MVP

## Overview
本设计定义财务统计小工具当前 `V1.2` 版本的实现方案，重点包括：

- 桌面批量导入
- 平台与店铺识别
- 来源模板解析
- 分类映射
- 分类汇总导出
- 贷借法双金额列输出
- 未映射提醒与暂未分类归并
- 后台处理与进度显示
- WPS 在线映射同步
- 单文件安装包升级发布

## Architecture
系统采用四层结构：

1. `UI`
   - 数据目录选择
   - 保存文件对话框
   - 处理状态、进度文本、进度条
   - 处理结果和异常展示
   - 异常复制
   - 在线映射状态卡片
   - `手动同步映射` 按钮

2. `Application Services`
   - 导入、分类、汇总、导出流程编排
   - 运行进度回调
   - 映射运行时缓存加载
   - WPS 在线映射同步

3. `Domain`
   - 文件名解析
   - 来源识别
   - 金额标准化
   - 备注归一化
   - 分类映射
   - 汇总计算

4. `Infrastructure`
   - 文件系统访问
   - CSV/XLS/XLSX 读取
   - SQLite
   - WPS OAuth 与 OpenAPI
   - Excel 导出
   - PyInstaller / Inno Setup 打包

## Runtime Flow
```text
选择数据目录
-> 选择导出文件
-> 后台线程启动任务
-> 扫描支持文件
-> 解析平台与店铺
-> 识别来源模板
-> 调用解析器
-> 标准化记录
-> 分类映射
-> 跳过忽略记录
-> 聚合生成汇总表
-> 导出 Excel
-> 弹出未映射提醒
-> 回到主界面显示结果
```

说明：
- 报表生成在后台线程执行
- UI 主线程只负责交互与进度刷新
- 即使数据量较大，窗口也保持可响应

在线映射同步流程：

```text
点击手动同步映射
-> 检查 WPS 授权配置
-> 优先读取本地 wps_file_id
-> 若未配置则尝试由分享短链解析 file_id
-> 获取工作表列表
-> 读取正式映射工作表有效区域
-> 解析映射规则
-> 替换 SQLite 本地映射缓存
-> 刷新映射版本、状态和来源
-> UI 弹窗提示同步完成
```

## Parsing

### Supported Platforms
- `拼多多`
- `淘宝`
- `天猫`
- `淘工厂`
- `淘农场`

### Template Families
- `拼多多模板`
- `淘宝系模板`

### Pinduoduo
- 文件类型：`CSV/XLS/XLSX`
- 自动定位表头，不依赖固定 `skiprows`

字段：
- `商户订单号`
- `发生时间`
- `收入金额（+元）`
- `支出金额（-元）`
- `账务类型`
- `备注`
- `业务描述`

### Taobao-like
- 文件类型：`CSV/XLS/XLSX`
- 优先读取 `原始数据` sheet
- 自动定位表头，不依赖固定行号

字段：
- `商户订单号`
- `入账时间`
- `收入（+元）`
- `支出（-元）`
- `账务类型`
- `备注`
- `业务描述`

共用淘宝系解析和分类逻辑的平台：
- `淘宝`
- `天猫`
- `淘工厂`
- `淘农场`

## Normalization

### Month
- 拼多多：由 `发生时间` 提取
- 淘宝系：由 `入账时间` 提取

### Amount
- 收入转为正数
- 支出转为负数
- 收入和支出同时为空或为 `0`：记异常并跳过
- 收入和支出同时有值：记异常并跳过

### Taobao Remark
淘宝备注做归一化，保留稳定业务文本，去除编号、订单号、邮箱等动态信息。

该规则同样适用于：
- `天猫`
- `淘工厂`
- `淘农场`

## Classification

### Taobao-like
键：
`remark_norm + " —— " + biz_desc`

`[空] —— [空]`：
- 标记为 ignored
- 不参与汇总

未命中规则时：
- 不再报致命错误
- `detail_category = 暂未分类`
- `major_category = 暂未分类`
- 生成面向用户的提醒文案

### Pinduoduo
键：
- `biz_desc`

重点已确认规则包括：
- `0040003|售后费用-运费补偿` -> `运费补偿 / 售后费用`
- `0040005|售后费用-虚假发货` -> `虚假发货 / 售后费用`

说明：
- 这两条规则已按最新业务口径从原来的 `店铺费用` 调整为 `售后费用`

未命中规则时：
- 不再阻断导出
- 归类为 `暂未分类 / 暂未分类`
- 生成提醒文案

## Mapping Source Management

### Runtime Sources
系统当前支持两级映射来源：

1. 内置默认映射
   - 首次启动时写入 SQLite
   - 作为离线保底规则

2. WPS 在线映射
   - 用户手动触发同步
   - 同步成功后覆盖本地 `mapping_rules`
   - 后续报表运行优先使用在线同步后的缓存

### Persisted Metadata
SQLite 除保存规则外，还保存同步元数据：

- `mapping_version`
- `mapping_last_sync_status`
- `mapping_last_sync_message`
- `mapping_source_url`

UI 与 CLI 会同时展示这些字段，便于确认当前正在使用哪一版映射。

## WPS Online Mapping

### Current Route
当前在线映射采用：

- 控制台：`open.wps.cn`
- 授权与接口：`openapi.wps.cn`

使用现有企业自建应用进行用户授权，所需权限为：

- `kso.sheets.read`
- `kso.file_link.readwrite`（仅在需要由短链解析 `file_id` 时使用）

### File Identification Strategy
由于 `kdocs.cn` 私有短链在 `open.wps.cn` 链路下不一定能稳定返回文件元信息，当前实现采用双路径：

1. 优先使用本地配置的 `wps_file_id`
2. 若未配置，再尝试通过分享短链解析 `file_id`

为此新增 CLI 兜底命令：

```bash
python tools/mapping_sync_cli.py set-file-id <file_id>
```

### Worksheet Read Strategy
WPS 工作表列表接口会返回 `active_area`。当前实现不再按整张表的最大行列读取，而是：

- 使用 `active_area.row_from ~ row_to`
- 使用 `active_area.col_from ~ col_to`

这样可以避免对超大空白区域发起 `range_data` 调用，减少 `CoreExecutionFailed` 风险。

### Validated Online File
当前已用真实在线表格完成验证：

- `file_id = 513431252713`
- 工作表：`正式映射`
- 实际同步规则数：`124`

## Aggregation
当前导出使用分类汇总长表，每行对应：

- `month`
- `store_name`
- `platform`
- `major_category`
- `detail_category`

导出列为：

- `月份`
- `店铺名`
- `平台`
- `大类`
- `明细分类`
- `收入金额`
- `支出金额`
- `记录数`

未命中映射但成功归类为 `暂未分类` 的记录：
- 仍然参与汇总
- 会出现在最终导出表中

## Debit/Credit Output
内部仍使用单一 signed amount 进行计算，但导出时采用双金额列：

- `收入金额`
  - 只汇总大于 0 的金额
- `支出金额`
  - 只汇总小于 0 的金额，导出时取绝对值

这样既保留业务分类，又满足财务按借贷式双列查看金额的需求。

## Export
- 单个 Excel 文件
- 单个 sheet：`总汇总表`
- 导出前弹出保存文件对话框
- 导出后如存在未映射项，弹出提醒窗口

## UI Interaction
- 主界面提供 `状态`、`进度文本`、`进度条`
- 异常列表支持多选
- 提供 `复制选中` 和 `复制全部`
- 处理期间禁用目录选择和启动按钮，避免重复触发
- 未映射提醒同时显示在列表和弹窗中
- 在线映射区域显示当前 `映射版本 / 同步状态 / 映射来源`
- 提供 `手动同步映射` 按钮

## Persistence
SQLite 保存：
- 默认输入目录
- 最近导出目录
- 运行日志
- 在线映射规则缓存
- 在线映射同步元数据
- `wps_file_id`、`wps_sheet_id`、`wps_sheet_name`

## Packaging
- `PyInstaller` 生成无控制台桌面程序
- `Inno Setup` 生成单文件安装包
- 安装包版本已升级为 `V1.2`
- 安装器复用同一个 `AppId`
- 新版本安装时会识别并替换旧版本

## Verification
当前版本验证目标：
- 能读取真实淘宝和拼多多样本
- 能导出包含 `大类` 和 `明细分类` 的汇总表
- 能导出 `收入金额` 和 `支出金额`
- 拼多多 `虚假发货` 与 `运费补偿` 显示为 `售后费用`
- 淘宝系和拼多多均支持 `CSV/XLS/XLSX`
- 未映射项进入 `暂未分类` 并弹窗提醒
- 大数据量处理时界面保持可响应并显示进度
- 能通过真实 WPS 在线表格同步 `正式映射`
- `kdocs` 私有短链无法解析时，可通过手动 `file_id` 成功同步
