#define MyAppName "TV AutoSEO"
#ifndef MyAppVersion
  #define MyAppVersion "2026.11.27.1"
#endif
#define MyAppExeName "TV AutoSEO.exe"
#define MyAppInstallName "TV AutoSEO 512BB19D"

#ifndef BuildSourceDir
  #define BuildSourceDir "dist\TV AutoSEO"
#endif

#ifndef BuildOutputDir
  #define BuildOutputDir "installer_dist"
#endif

[Setup]
AppId={{512BB19D-FEFA-4B22-9362-A62C123B1F1D}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
DefaultDirName={localappdata}\Programs\{#MyAppInstallName}
DefaultGroupName={#MyAppInstallName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir={#BuildOutputDir}
OutputBaseFilename=TVAutoSEO_Setup
SetupIconFile=assets\logo.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
UninstallDisplayName={#MyAppName}
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes
RestartApplications=no
VersionInfoVersion={#MyAppVersion}
VersionInfoProductName={#MyAppName}
VersionInfoProductVersion={#MyAppVersion}

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional shortcuts:"; Flags: unchecked

[InstallDelete]
; Remove the previous packaged runtime so stale optional Python modules cannot
; survive an upgrade. User databases and settings live under AppData and are
; intentionally not touched here.
Type: filesandordirs; Name: "{app}\_internal"

[Files]
Source: "{#BuildSourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppInstallName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"
Name: "{autodesktop}\{#MyAppInstallName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Flags: nowait skipifsilent
