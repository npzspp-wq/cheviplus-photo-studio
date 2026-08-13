#define MyAppName "Cheviplus Photo Studio"
#define MyAppVersion "5.12"
#define MyAppPublisher "Cheviplus"
#define MyAppExeName "Cheviplus Photo Studio.exe"

[Setup]
; IMPORTANT: Keep this AppId forever. Inno Setup uses it to recognize previous
; Cheviplus Photo Studio installations and upgrade them in place.
AppId={{A2F11BC4-7E17-4D58-9C57-2A2E5E3075C8}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={localappdata}\Cheviplus Photo Studio
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
OutputDir=..\installer-dist
OutputBaseFilename=Cheviplus-Photo-Studio-Setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
SetupIconFile=..\assets\app_icon.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
ArchitecturesInstallIn64BitMode=x64compatible
UsePreviousAppDir=yes
UsePreviousGroup=yes
DisableDirPage=auto
CloseApplications=yes
RestartApplications=no

[Files]
; Application files are replaced on update. User/license data live in APPDATA
; and therefore are intentionally not included in this section.
Source: "..\dist\Cheviplus Photo Studio\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autodesktop}\Cheviplus Photo Studio"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; IconFilename: "{app}\{#MyAppExeName}"
Name: "{userprograms}\Cheviplus Photo Studio"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; IconFilename: "{app}\{#MyAppExeName}"

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Запустить Cheviplus Photo Studio"; Flags: nowait postinstall skipifsilent
