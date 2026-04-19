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

### Requirement: Source Template Detection
The system SHALL detect supported source templates before parsing file content.

#### Scenario: Detect Pinduoduo CSV
- GIVEN a `CSV` file with the expected 拼多多表头
- WHEN the file is evaluated
- THEN the system selects the `pdd_csv` parser

#### Scenario: Detect Taobao workbook
- GIVEN an `XLSX` or `XLS` file with the expected 淘宝表头
- WHEN the file is evaluated
- THEN the system selects the `tb_xlsx` parser

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
The system SHALL classify Taobao records using the normalized remark and business description as a composite key.

#### Scenario: Build Taobao classification key
- GIVEN a Taobao record with `remark_norm` and `biz_desc`
- WHEN the record is classified
- THEN the system uses `remark_norm —— biz_desc` as the match key

#### Scenario: Ignore empty composite key
- GIVEN a Taobao record where remark and business description are both empty
- WHEN the record is classified
- THEN the system marks the record as ignored
- AND excludes it from aggregation

### Requirement: Pinduoduo Business Description Classification
The system SHALL classify Pinduoduo records primarily by `biz_desc`.

#### Scenario: Match known business description
- GIVEN a Pinduoduo record whose `biz_desc` exists in configured rules
- WHEN the record is classified
- THEN the system assigns both `detail_category` and `major_category`

#### Scenario: Handle unmatched rule
- GIVEN a Pinduoduo record whose `biz_desc` has no matching rule
- WHEN the record is classified
- THEN the system records a classification error
- AND excludes the record from aggregation

### Requirement: Category Summary Export
The system SHALL export a single-sheet Excel report containing category summary rows.

#### Scenario: Export long-form summary
- GIVEN normalized and classified records
- WHEN aggregation completes
- THEN the system exports one row per `month + store_name + platform + major_category + detail_category`
- AND the sheet contains `月份`、`店铺名`、`平台`、`大类`、`明细分类`、`金额`、`记录数`

### Requirement: User-Selected Export Path
The system SHALL prompt the user to choose the output path before exporting a report.

#### Scenario: Save dialog
- GIVEN the user clicks `一键生成报表`
- WHEN the export process starts
- THEN the system opens a save-file dialog
- AND exports the report to the selected `.xlsx` path
