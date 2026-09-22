#define MyAppName "Cheviplus Photo Studio"
#define MyAppVersion "5.34"
#define MyAppPublisher "Cheviplus"
#define MyAppExeName "Cheviplus Photo Studio.exe"

[Setup]
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
Source: "..\dist\Cheviplus Photo Studio\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{userprograms}\Cheviplus Photo Studio"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; IconFilename: "{app}\{#MyAppExeName}"

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Запустить Cheviplus Photo Studio"; Flags: nowait postinstall skipifsilent
