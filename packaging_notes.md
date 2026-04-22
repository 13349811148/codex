# 安装包说明

## 目标
生成一个可分发的 Windows 安装包，分发时只需要发送一个 `.exe` 文件。

同事使用方式：
1. 双击安装包
2. 选择安装位置
3. 点击安装
4. 安装完成后可直接启动软件

## 打包方案
- `PyInstaller`：生成桌面程序
- `Inno Setup`：生成单文件安装包

## 构建命令

```powershell
.\build_installer.ps1
```

## 输出文件

```text
%USERPROFILE%\Desktop\财务统计小工具安装包_V2.6.exe
```

## 最新构建

- 最近一次构建日期：`2026-04-22`
- 安装包路径：`%USERPROFILE%\Desktop\财务统计小工具安装包_V2.6.exe`
- 本次构建已重新执行 `build_installer.ps1`

## 运行时数据目录
软件安装后，配置和数据库写入：

```text
%LOCALAPPDATA%\FinanceTool
```

这样不会因为安装在 `Program Files` 而缺少写权限。

## 升级行为
- 安装器沿用同一个 `AppId`
- 版本号已升级到 `2.6.0`
- 用户安装 V2.6 时，会先检测并卸载已安装的旧版本，再继续覆盖安装
- 安装器沿用同一个 `AppId`，并兼容识别 V2.3、V2.4 等旧版本的卸载记录
- 安装器会在检测到 `finance_tool.exe` 运行时提示关闭后继续覆盖安装
