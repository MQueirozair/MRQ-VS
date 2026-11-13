; Instalador oficial do MRQ Audio Studio para Windows (Inno Setup 6).
; Gera dist\MRQ-VS-Setup-windows-x64.exe com atalho automático na Área de Trabalho
; e no Menu Iniciar, sem exigir permissão de Administrador.

#ifndef MyAppVersion
  #define MyAppVersion "0.1.24"
#endif
#define MyAppName "MRQ Audio Studio"
#define MyAppExeName "mrq-vs.exe"

[Setup]
AppId={{B97A4E31-8D42-4C6A-9E15-7C2F91D38A10}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher=MRQ
AppPublisherURL=https://github.com/MQueirozair/MRQ-VS
AppSupportURL=https://github.com/MQueirozair/MRQ-VS/issues
AppUpdatesURL=https://github.com/MQueirozair/MRQ-VS/releases
SourceDir=..
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
OutputDir=dist
OutputBaseFilename=MRQ-VS-Setup-windows-x64
SetupIconFile=windows\mrq-vs.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
UninstallDisplayName={#MyAppName}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern

[Languages]
#if FileExists(AddBackslash(CompilerPath) + "Languages\BrazilianPortuguese.isl")
Name: "brazilianportuguese"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"
#endif
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
; marcado por padrão: o pedido é "instalar e ficar com o ícone na Área de Trabalho"
Name: "desktopicon"; Description: "Criar ícone na Área de Trabalho ({#MyAppName})"; GroupDescription: "Atalhos:"; Flags: checkedonce

[Files]
Source: "dist\{#MyAppExeName}"; DestDir: "{app}"; Flags: ignoreversion
Source: "windows\mrq-vs.ico"; DestDir: "{app}"; Flags: ignoreversion
Source: "README.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "LICENSE"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\mrq-vs.ico"; WorkingDir: "{app}"; Comment: "Separador de Stems e Editor Musical MRQ Audio Studio"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\mrq-vs.ico"; WorkingDir: "{app}"; Tasks: desktopicon; Comment: "Abrir {#MyAppName}"

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Abrir o {#MyAppName} ao concluir"; Flags: nowait postinstall skipifsilent
