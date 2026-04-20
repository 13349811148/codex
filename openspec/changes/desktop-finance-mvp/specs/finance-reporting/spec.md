# Delta for Finance Reporting

## ADDED Requirements

### Requirement: Desktop Batch Import
The system SHALL allow a user to select a local directory and batch-import supported finance files from that directory.

#### Scenario: Scan supported files
- GIVEN a directory contains `CSV`, `XLS`, and `XLSX` files
- WHEN the user runs the report
- THEN the system scans supported files in that directory
- AND unsupported files are ignored

### Requirement: Platform And Store Identification
The system SHALL derive `platform` and `store_name` from the source filename.

#### Scenario: Parse Taobao filename
- GIVEN a filename like `3月淘宝-庄品健大米1号店（下载）.xlsx`
- WHEN the file is processed
- THEN the system identifies `platform` as `淘宝`
- AND identifies `store_name` as `庄品健大米1号店`

#### Scenario: Parse Pinduoduo filename
- GIVEN a filename like `3月拼多多—黄小惠米面旗舰店.csv`
- WHEN the file is processed
- THEN the system identifies `platform` as `拼多多`
- AND identifies `store_name` as `黄小惠米面旗舰店`

#### Scenario: Parse Taobao-like filename
- GIVEN a filename like `3月天猫-庄品健大米1号店.xlsx`
- WHEN the file is processed
- THEN the system identifies `platform` as `天猫`
- AND identifies `store_name` as `庄品健大米1号店`

### Requirement: Source Template Detection
The system SHALL detect supported source templates before parsing file content.

#### Scenario: Detect Pinduoduo CSV
- GIVEN a `CSV` file with the expected 拼多多表头
- WHEN the file is evaluated
- THEN the system selects the `pdd_table` parser

#### Scenario: Detect Pinduoduo workbook
- GIVEN an `XLSX` or `XLS` file with the expected 拼多多表头
- WHEN the file is evaluated
- THEN the system selects the `pdd_table` parser

#### Scenario: Detect Taobao workbook
- GIVEN an `XLSX` or `XLS` file with the expected 淘宝表头
- WHEN the file is evaluated
- THEN the system selects the `tb_table` parser

#### Scenario: Detect Taobao CSV
- GIVEN a `CSV` file with the expected 淘宝系表头
- WHEN the file is evaluated
- THEN the system selects the `tb_table` parser

#### Scenario: Ignore non-bill workbook
- GIVEN a directory also contains a generated result workbook
- WHEN the system scans source files
- THEN unsupported non-template files are ignored
- AND the batch run continues

### Requirement: Time And Amount Normalization
The system SHALL normalize source records into a common structure using a derived month and a signed amount.

#### Scenario: Convert income to positive amount
- GIVEN a record with a populated income column
- WHEN the record is normalized
- THEN the normalized amount is positive

#### Scenario: Convert expense to negative amount
- GIVEN a record with a populated expense column
- WHEN the record is normalized
- THEN the normalized amount is negative

#### Scenario: Skip invalid amount row
- GIVEN a record where income and expense are both empty or zero
- WHEN the record is normalized
- THEN the system records an error
- AND skips that record from aggregation

### Requirement: Taobao Composite Classification
The system SHALL classify Taobao-like records using the normalized remark and business description as a composite key.

#### Scenario: Build Taobao-like classification key
- GIVEN a Taobao-like record with `remark_norm` and `biz_desc`
- WHEN the record is classified
- THEN the system uses `remark_norm —— biz_desc` as the match key

#### Scenario: Ignore empty composite key
- GIVEN a Taobao-like record where remark and business description are both empty
- WHEN the record is classified
- THEN the system marks the record as ignored
- AND excludes it from aggregation

#### Scenario: Share Taobao rules with Tmall
- GIVEN a `天猫` record with a known `remark_norm —— biz_desc`
- WHEN the record is classified
- THEN the system applies the same rule set as `淘宝`

### Requirement: Pinduoduo Business Description Classification
The system SHALL classify Pinduoduo records primarily by `biz_desc`.

#### Scenario: Match known business description
- GIVEN a Pinduoduo record whose `biz_desc` exists in configured rules
- WHEN the record is classified
- THEN the system assigns both `detail_category` and `major_category`

#### Scenario: Pinduoduo after-sale adjustment
- GIVEN a Pinduoduo record whose `biz_desc` is `0040003|售后费用-运费补偿`
- WHEN the record is classified
- THEN the system assigns `detail_category` as `运费补偿`
- AND assigns `major_category` as `售后费用`

#### Scenario: Pinduoduo false-shipment adjustment
- GIVEN a Pinduoduo record whose `biz_desc` is `0040005|售后费用-虚假发货`
- WHEN the record is classified
- THEN the system assigns `detail_category` as `虚假发货`
- AND assigns `major_category` as `售后费用`

### Requirement: Unmapped Records Fallback
The system SHALL keep unmapped business items in the exported summary instead of dropping them.

#### Scenario: Fallback to uncategorized
- GIVEN a record whose classification key does not exist in configured rules
- WHEN the record is classified
- THEN the system assigns `detail_category` as `暂未分类`
- AND assigns `major_category` as `暂未分类`
- AND the record is still included in aggregation

#### Scenario: Warn user about unmapped item
- GIVEN one or more records are classified as `暂未分类`
- WHEN export completes
- THEN the system shows a warning dialog
- AND the warning contains the store name and unmatched business item text

### Requirement: Category Summary Export
The system SHALL export a single-sheet Excel report containing category summary rows.

#### Scenario: Export long-form summary
- GIVEN normalized and classified records
- WHEN aggregation completes
- THEN the system exports one row per `month + store_name + platform + major_category + detail_category`
- AND the sheet contains `月份`、`店铺名`、`平台`、`大类`、`明细分类`

### Requirement: Debit Credit Amount Columns
The system SHALL export separate income and expense amount columns instead of a single net amount column.

#### Scenario: Export debit-credit style amounts
- GIVEN normalized and classified records
- WHEN aggregation completes
- THEN the sheet contains `收入金额` and `支出金额`
- AND positive values are aggregated into `收入金额`
- AND negative values are aggregated by absolute value into `支出金额`

### Requirement: User-Selected Export Path
The system SHALL prompt the user to choose the output path before exporting a report.

#### Scenario: Save dialog
- GIVEN the user clicks `一键生成报表`
- WHEN the export process starts
- THEN the system opens a save-file dialog
- AND exports the report to the selected `.xlsx` path

### Requirement: Responsive Long-Running Processing
The system SHALL remain responsive while processing large batches and SHALL display progress to the user.

#### Scenario: Process in background
- GIVEN the user starts a report run on a large dataset
- WHEN the system is processing files
- THEN the UI remains responsive
- AND the main window does not block on the long-running task

#### Scenario: Show progress
- GIVEN the system is scanning, parsing, aggregating, or exporting
- WHEN the run is in progress
- THEN the UI shows progress text
- AND the UI shows a progress bar

### Requirement: Copyable Error And Warning Messages
The system SHALL allow users to copy exception and warning messages from the UI.

#### Scenario: Copy selected messages
- GIVEN the message list contains one or more items
- WHEN the user clicks `复制选中`
- THEN the system copies the selected items to the clipboard

#### Scenario: Copy all messages
- GIVEN the message list contains one or more items
- WHEN the user clicks `复制全部`
- THEN the system copies the full list to the clipboard

### Requirement: WPS Online Mapping Sync
The system SHALL support manually syncing classification rules from a WPS online worksheet into the local cache.

#### Scenario: Manual sync from online worksheet
- GIVEN the user has configured a reachable WPS online mapping file
- WHEN the user clicks `手动同步映射`
- THEN the system reads the `正式映射` worksheet
- AND replaces the local mapping cache with the synced rules
- AND updates the displayed sync version, status, and source

#### Scenario: Use synced rules in later report runs
- GIVEN a successful WPS online mapping sync has completed
- WHEN the user generates a report afterwards
- THEN the system uses the synced local cache
- AND does not fall back to the built-in mapping rules unless the cache is reset

### Requirement: Manual File Id Fallback
The system SHALL support manually configuring the WPS `file_id` when a private `kdocs.cn` share link cannot be resolved by OpenAPI.

#### Scenario: Short link cannot resolve file id
- GIVEN a `kdocs.cn` private share link does not return file metadata through `openapi.wps.cn`
- WHEN the user attempts online mapping sync
- THEN the system shows an actionable error
- AND the error tells the user to manually provide `wps_file_id`

#### Scenario: Sync with manually configured file id
- GIVEN the user has manually written a valid `wps_file_id`
- WHEN online mapping sync runs
- THEN the system reads the worksheet directly by `file_id`
- AND the sync can succeed without share-link metadata resolution

### Requirement: Effective Range Reading
The system SHALL read only the worksheet's effective active area when pulling online mapping cells from WPS.

#### Scenario: Avoid full-sheet fetch
- GIVEN the worksheet metadata includes `active_area`
- WHEN the system requests `range_data`
- THEN it uses the active row and column bounds instead of the full sheet max bounds
- AND avoids failures caused by requesting excessively large empty regions
