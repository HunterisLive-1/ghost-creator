#define MyAppName "Ghost Creator AI"
#define MyAppVersion "4.3.0"
#define MyAppPublisher "HunterIsLive"
#define MyAppURL "https://github.com/HunterisLive-1/ghost-creator"
#define MyAppSupportURL "https://github.com/HunterisLive-1/ghost-creator/issues"
#define MyAppExeName "GhostCreatorAI.exe"
#define MyAppApiExeName "GhostCreatorAPI.exe"

; Compile-time checks (run when you Build in Inno Setup — NOT when end user installs).
; Note: #ifexist does not expand {#define} constants — use literal file names.
#ifexist "release\win-unpacked\GhostCreatorAI.exe"
#else
  #error "Missing build output: release\win-unpacked\GhostCreatorAI.exe. Run build-electron.bat first."
#endif
#ifexist "dist-api\GhostCreatorAPI\GhostCreatorAPI.exe"
#else
  #error "Missing build output: dist-api\GhostCreatorAPI\GhostCreatorAPI.exe. Run build-api.bat first."
#endif

; Build before compiling this installer:
;   1. build-electron.bat   (cleans old output, builds API exe + Electron release\win-unpacked)
;   2. Open this script in Inno Setup Compiler and Compile
;
; Installed layout:
;   {app}\GhostCreatorAI.exe                      — Electron shell
;   {app}\resources\GhostCreatorAPI\GhostCreatorAPI.exe — Python FastAPI sidecar
;   {app}\resources\GhostCreatorAPI\_internal\    — Python runtime files
;   %LOCALAPPDATA%\GhostCreatorAI\                — config.json + first-run FFmpeg download

[Setup]
; AppId kabhi mat badlo — warna purana install alag app ban jayega / upgrade toot jayega.
AppId={{GhostCreatorAI-2025-HunterIsLive-UUID}}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} v{#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppSupportURL}
AppUpdatesURL={#MyAppURL}/releases
DefaultDirName={autopf}\GhostCreatorAI
DefaultGroupName={#MyAppName}
AllowNoIcons=yes
OutputDir=installer_output
OutputBaseFilename=GhostCreatorAI_v{#MyAppVersion}_Setup
SetupIconFile=icon.ico
UninstallDisplayIcon={app}\icon.ico
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=admin
MinVersion=10.0
AppMutex=GhostCreatorAIMutex
CloseApplications=yes
CloseApplicationsFilter=*.exe
RestartApplications=no
LicenseFile=LICENSE
VersionInfoVersion={#MyAppVersion}
VersionInfoCompany={#MyAppPublisher}
VersionInfoDescription={#MyAppName} — Documentary video automation (MIT)
VersionInfoCopyright=Copyright (C) 2026 {#MyAppPublisher}
VersionInfoProductName={#MyAppName}
VersionInfoProductVersion={#MyAppVersion}

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a &Desktop shortcut"; GroupDescription: "Additional icons:"
Name: "startmenuicon"; Description: "Create a &Start Menu shortcut"; GroupDescription: "Additional icons:"

[Files]
; Electron app (build-electron.bat → release\win-unpacked)
Source: "release\win-unpacked\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

; Python API sidecar (onedir build) — full folder with _internal runtime
Source: "dist-api\GhostCreatorAPI\*"; DestDir: "{app}\resources\GhostCreatorAPI"; Flags: ignoreversion recursesubdirs createallsubdirs

; App icon for shortcuts
Source: "icon.ico"; DestDir: "{app}"; Flags: ignoreversion

; MIT license (also shown in wizard via LicenseFile)
Source: "LICENSE"; DestDir: "{app}"; Flags: ignoreversion

; FFmpeg: downloaded on first launch to {localappdata}\GhostCreatorAI\ffmpeg
; config.json: created in {localappdata}\GhostCreatorAI on first run

[Icons]
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\icon.ico"; Tasks: desktopicon
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\icon.ico"; Tasks: startmenuicon
Name: "{group}\Uninstall {#MyAppName}"; Filename: "{uninstallexe}"; Tasks: startmenuicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Launch {#MyAppName}"; Flags: nowait postinstall skipifsilent

[UninstallRun]
Filename: "taskkill"; Parameters: "/F /IM {#MyAppExeName}"; Flags: runhidden waituntilterminated; RunOnceId: "KillElectronApp"
Filename: "taskkill"; Parameters: "/F /IM {#MyAppApiExeName}"; Flags: runhidden waituntilterminated; RunOnceId: "KillApiSidecar"

[UninstallDelete]
Type: filesandordirs; Name: "{localappdata}\GhostCreatorAI\ffmpeg"
Type: filesandordirs; Name: "{app}"
Type: dirifempty; Name: "{group}"

[Code]
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
