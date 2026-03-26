#define MyAppName "Ghost Creator AI"
#define MyAppVersion "3.0"
#define MyAppPublisher "HunterIsLive"
#define MyAppURL "https://getmaya.online"
#define MyAppExeName "GhostCreatorAI.exe"

[Setup]
AppId={{GhostCreatorAI-2025-HunterIsLive-UUID}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} v{#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}
DefaultDirName={autopf}\GhostCreatorAI
DefaultGroupName={#MyAppName}
AllowNoIcons=yes
OutputDir=installer_output
OutputBaseFilename=GhostCreatorAI_v3_Setup
SetupIconFile=icon.ico
UninstallDisplayIcon={app}\icon.ico
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=admin
MinVersion=10.0
; Version checking — allows silent upgrade over old version
AppMutex=GhostCreatorAIMutex
CloseApplications=yes
CloseApplicationsFilter=*.exe
RestartApplications=no
; Uninstall previous version automatically before installing new one
; This ensures clean update without duplicate entries

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a &Desktop shortcut"; GroupDescription: "Additional icons:"
Name: "startmenuicon"; Description: "Create a &Start Menu shortcut"; GroupDescription: "Additional icons:"

[Files]
; Main executable from PyInstaller output
Source: "dist\GhostCreatorAI.exe"; DestDir: "{app}"; DestName: "GhostCreatorAI.exe"; Flags: ignoreversion

; App icon for shortcuts
Source: "icon.ico"; DestDir: "{app}"; Flags: ignoreversion

; ComfyUI Workflow API
Source: "workflow_api.json"; DestDir: "{app}"; Flags: ignoreversion

; Note: FFmpeg is already bundled inside GhostCreatorAI.exe using --add-data in build.bat
; Note: config.json is generated automatically in %LOCALAPPDATA%\GhostCreatorAI on first run
; Note: Chatterbox Server path can be set in the App Settings inside the UI. No need to package gigabytes of data.

[Icons]
; Desktop shortcut
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\icon.ico"; Tasks: desktopicon

; Start Menu shortcuts
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\icon.ico"; Tasks: startmenuicon
Name: "{group}\Uninstall {#MyAppName}"; Filename: "{uninstallexe}"; Tasks: startmenuicon

[Run]
; Launch app after install
Filename: "{app}\{#MyAppExeName}"; Description: "Launch {#MyAppName}"; Flags: nowait postinstall skipifsilent

[UninstallRun]
; Kill app if running before uninstall
Filename: "taskkill"; Parameters: "/F /IM GhostCreatorAI.exe"; Flags: runhidden waituntilterminated; RunOnceId: "KillApp"

[UninstallDelete]
; Delete entire install folder on uninstall (clean removal)
Type: filesandordirs; Name: "{app}"

; Delete Start Menu folder
Type: dirifempty; Name: "{group}"

[Code]
// ─── Auto-uninstall previous version before installing new one ───────────────
function GetUninstallString(): String;
var
  sUnInstPath: String;
  sUnInstallString: String;
begin
  sUnInstPath := ExpandConstant('Software\Microsoft\Windows\CurrentVersion\Uninstall\{#SetupSetting("AppId")}_is1');
  sUnInstallString := '';
  if not RegQueryStringValue(HKLM, sUnInstPath, 'UninstallString', sUnInstallString) then
    RegQueryStringValue(HKCU, sUnInstPath, 'UninstallString', sUnInstallString);
  Result := sUnInstallString;
end;

function IsUpgrade(): Boolean;
begin
  Result := (GetUninstallString() <> '');
end;

function UnInstallOldVersion(): Integer;
var
  sUnInstallString: String;
  iResultCode: Integer;
begin
  Result := 0;
  sUnInstallString := GetUninstallString();
  if sUnInstallString <> '' then begin
    sUnInstallString := RemoveQuotes(sUnInstallString);
    if Exec(sUnInstallString, '/SILENT /NORESTART /SUPPRESSMSGBOXES', '', SW_HIDE, ewWaitUntilTerminated, iResultCode) then
      Result := 3
    else
      Result := 2;
  end else
    Result := 1;
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if (CurStep = ssInstall) then begin
    if (IsUpgrade()) then begin
      UnInstallOldVersion();
    end;
  end;
end;

// ─── Microsoft SmartScreen / Defender bypass hint ────────────────────────────
// (Adding version info and publisher helps avoid false positives)
function InitializeSetup(): Boolean;
begin
  Result := True;
end;
