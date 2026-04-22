#define MyAppName "Finance Tool"
#define MyAppDisplayName "财务统计小工具"
#define MyAppVisibleName "财务统计小工具 V2.5"
#define MyAppVersion "2.5.0"
#define MyAppPublisher "13349811148"
#define MyAppExeName "finance_tool.exe"
#define MyAppSourceDir "dist\finance_tool"

[Setup]
AppId={{6A7A43A1-71B0-4D7D-9B5A-8A8D1F3F3C11}
AppName={#MyAppDisplayName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppVisibleName}
AppPublisher={#MyAppPublisher}
DefaultDirName={localappdata}\Programs\{#MyAppDisplayName}
DefaultGroupName={#MyAppDisplayName}
DisableProgramGroupPage=yes
OutputDir={#GetEnv('USERPROFILE') + '\Desktop'}
OutputBaseFilename=财务统计小工具安装包_V2.5
Compression=lzma
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=lowest
UninstallDisplayIcon={app}\{#MyAppExeName}
UninstallDisplayName={#MyAppVisibleName}
VersionInfoVersion=2.5.0.0
VersionInfoProductVersion=2.5.0.0
UsePreviousAppDir=yes
CloseApplications=yes
CloseApplicationsFilter=finance_tool.exe

[Languages]
Name: "default"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create desktop shortcut"; GroupDescription: "Additional tasks:"; Flags: unchecked

[Files]
Source: "{#MyAppSourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppVisibleName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\{#MyAppVisibleName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Launch {#MyAppVisibleName} after setup"; Flags: nowait postinstall skipifsilent
