; 数字画像メーカー インストーラ（Inno Setup 6）
; 通常は build.py から実行する。MyAppVersion と ExePath は build.py が渡す
#define MyAppName "数字画像メーカー"
#define MyAppExe "SujiMaker.exe"
#define MyPublisher "OnsooSystem Corp."
#ifndef MyAppVersion
  #define MyAppVersion "1.0.0"
#endif
#ifndef ExePath
  #define ExePath "release\SujiMaker.exe"
#endif

[Setup]
; AppId は更新のたびに同じ値を使う（変えると別アプリ扱いになる）
AppId={{601ED9A0-5699-44F0-8C67-6BC96D9C83C1}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyPublisher}
AppCopyright=© 2026 OnsooSystem Corp.
VersionInfoVersion={#MyAppVersion}
; ユーザーごとのインストール（管理者権限なしで入れられ、更新も自動でできる）
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
DefaultDirName={autopf}\SujiMaker
DisableProgramGroupPage=yes
OutputBaseFilename=SujiMaker-{#MyAppVersion}-setup
SetupIconFile=icon.ico
UninstallDisplayIcon={app}\{#MyAppExe}
UninstallDisplayName={#MyAppName}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes
RestartApplications=no

[Languages]
Name: "japanese"; MessagesFile: "compiler:Languages\Japanese.isl"

[Tasks]
Name: "desktopicon"; Description: "デスクトップにアイコンを作る"; GroupDescription: "アイコン:"

[Files]
Source: "{#ExePath}"; DestDir: "{app}"; DestName: "{#MyAppExe}"; Flags: ignoreversion

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExe}"; Tasks: desktopicon

[Run]
; 自動更新（/SILENT）のあとも起動し直すため skipifsilent は付けない
Filename: "{app}\{#MyAppExe}"; Description: "{#MyAppName} を起動する"; Flags: nowait postinstall
