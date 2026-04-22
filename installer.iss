#define MyAppName "Finance Tool"
#define MyAppDisplayName "财务统计小工具"
#define MyAppVisibleName "财务统计小工具 V2.7"
#define MyAppVersion "2.7.0"
#define MyAppPublisher "13349811148"
#define MyAppExeName "finance_tool.exe"
#define MyAppSourceDir "dist\finance_tool"

[Setup]
#define LegacyUpgradeKey "{6A7A43A1-71B0-4D7D-9B5A-8A8D1F3F3C11}_is1"
AppId={{6A7A43A1-71B0-4D7D-9B5A-8A8D1F3F3C11}
AppName={#MyAppDisplayName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppVisibleName}
AppPublisher={#MyAppPublisher}
DefaultDirName={localappdata}\Programs\{#MyAppDisplayName}
DefaultGroupName={#MyAppDisplayName}
DisableProgramGroupPage=yes
OutputDir={#GetEnv('USERPROFILE') + '\Desktop'}
OutputBaseFilename=财务统计小工具安装包_V2.7
Compression=lzma
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=lowest
UninstallDisplayIcon={app}\{#MyAppExeName}
UninstallDisplayName={#MyAppVisibleName}
VersionInfoVersion=2.7.0.0
VersionInfoProductVersion=2.7.0.0
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

[Code]
const
  UninstallRegPath = 'Software\Microsoft\Windows\CurrentVersion\Uninstall';
  LegacyUpgradeKey = '{#LegacyUpgradeKey}';

function StartsWithText(const Prefix, Value: string): Boolean;
begin
  Result := CompareText(Copy(Value, 1, Length(Prefix)), Prefix) = 0;
end;

function TryReadUninstallEntry(
  RootKey: Integer;
  const KeyName: string;
  var DisplayName: string;
  var UninstallString: string
): Boolean;
var
  FullKey: string;
begin
  FullKey := UninstallRegPath + '\' + KeyName;
  Result := RegQueryStringValue(RootKey, FullKey, 'UninstallString', UninstallString);
  if not Result then
    exit;

  if not RegQueryStringValue(RootKey, FullKey, 'DisplayName', DisplayName) then
    DisplayName := '{#MyAppDisplayName}';
end;

function FindUninstallEntryByDisplayName(
  RootKey: Integer;
  var DisplayName: string;
  var UninstallString: string
): Boolean;
var
  SubKeys: TArrayOfString;
  I: Integer;
  CandidateDisplayName: string;
  CandidateUninstallString: string;
begin
  Result := False;
  if not RegGetSubkeyNames(RootKey, UninstallRegPath, SubKeys) then
    exit;

  for I := 0 to GetArrayLength(SubKeys) - 1 do
  begin
    if TryReadUninstallEntry(RootKey, SubKeys[I], CandidateDisplayName, CandidateUninstallString) and
       StartsWithText('{#MyAppDisplayName}', CandidateDisplayName) then
    begin
      DisplayName := CandidateDisplayName;
      UninstallString := CandidateUninstallString;
      Result := True;
      exit;
    end;
  end;
end;

function FindExistingVersion(
  var DisplayName: string;
  var UninstallString: string
): Boolean;
begin
  Result :=
    TryReadUninstallEntry(HKCU, LegacyUpgradeKey, DisplayName, UninstallString) or
    TryReadUninstallEntry(HKLM, LegacyUpgradeKey, DisplayName, UninstallString);

  if Result then
    exit;

  Result :=
    FindUninstallEntryByDisplayName(HKCU, DisplayName, UninstallString) or
    FindUninstallEntryByDisplayName(HKLM, DisplayName, UninstallString);
end;

function UninstallExistingVersion(): Boolean;
var
  ExistingDisplayName: string;
  ExistingUninstallString: string;
  ExistingUninstallExe: string;
  ResultCode: Integer;
begin
  Result := True;
  if not FindExistingVersion(ExistingDisplayName, ExistingUninstallString) then
    exit;

  ExistingUninstallExe := RemoveQuotes(ExistingUninstallString);
  if ExistingUninstallExe = '' then
    exit;

  if not FileExists(ExistingUninstallExe) then
  begin
    Log('Skipping old-version uninstall because uninstall executable was not found: ' + ExistingUninstallExe);
    exit;
  end;

  if SuppressibleMsgBox(
       '检测到已安装版本：' + ExistingDisplayName + #13#10#13#10 +
       '安装程序将先卸载旧版本，再继续安装 {#MyAppVisibleName}，这样可以正确覆盖 V2.3、V2.4 等旧版本。' + #13#10#13#10 +
       '点击“确定”继续，点击“取消”中止安装。',
       mbInformation,
       MB_OKCANCEL,
       IDOK
     ) <> IDOK then
  begin
    Result := False;
    exit;
  end;

  if not Exec(
           ExistingUninstallExe,
           '/VERYSILENT /SUPPRESSMSGBOXES /NORESTART',
           '',
           SW_HIDE,
           ewWaitUntilTerminated,
           ResultCode
         ) then
  begin
    SuppressibleMsgBox(
      '旧版本卸载程序启动失败，请先手动卸载旧版本后再安装 {#MyAppVisibleName}。',
      mbError,
      MB_OK,
      IDOK
    );
    Result := False;
    exit;
  end;

  if ResultCode <> 0 then
  begin
    SuppressibleMsgBox(
      '旧版本卸载未成功完成，返回码：' + IntToStr(ResultCode) +
      '。请先手动卸载旧版本后再安装 {#MyAppVisibleName}。',
      mbError,
      MB_OK,
      IDOK
    );
    Result := False;
    exit;
  end;
end;

function InitializeSetup(): Boolean;
begin
  Result := UninstallExistingVersion();
end;
