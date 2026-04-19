#define MyAppName "Finance Tool"
#define MyAppDisplayName "财务统计小工具"
#define MyAppVisibleName "财务统计小工具 V1.2"
#define MyAppVersion "1.2.0"
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
OutputDir=installer_output
OutputBaseFilename=finance-tool-v1.2-setup
Compression=lzma
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=lowest
UninstallDisplayIcon={app}\{#MyAppExeName}
UninstallDisplayName={#MyAppVisibleName}
VersionInfoVersion=1.2.0.0
VersionInfoProductVersion=1.2.0.0
UsePreviousAppDir=yes

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
