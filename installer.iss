#define AppName "Video Downloader"
#ifndef AppVersion
#define AppVersion "0.3.1"
#endif
[Setup]
AppId={{0A065A63-454A-44CC-A06B-3B22BDCE2F18}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher=Video Downloader
DefaultDirName={localappdata}\Programs\VideoDownloader
DefaultGroupName={#AppName}
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0.19041
OutputDir=dist
OutputBaseFilename=VideoDownloader-{#AppVersion}-win64-setup
SetupIconFile=assets\app.ico
UninstallDisplayIcon={app}\VideoDownloader.exe
Compression=lzma2/fast
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes
RestartApplications=no
DisableProgramGroupPage=yes
SetupLogging=yes

[Languages]
Name: "traditionalchinese"; MessagesFile: "packaging\ChineseTraditional.isl"

[Tasks]
Name: "desktopicon"; Description: "建立桌面捷徑"; Flags: unchecked

[Files]
Source: "dist\VideoDownloader\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\VideoDownloader.exe"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\VideoDownloader.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\VideoDownloader.exe"; Description: "開啟 Video Downloader"; Flags: nowait postinstall skipifsilent

; Intentionally no deletion of downloads or LocalAppData user preferences.
