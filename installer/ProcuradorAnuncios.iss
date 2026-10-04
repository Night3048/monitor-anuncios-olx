; Valores substituídos pelo script de build; as predefinições permitem abrir
; este ficheiro diretamente no Inno Setup durante o desenvolvimento.
#ifndef AppVersion
  #define AppVersion "1.0.0"
#endif
#ifndef SourceDir
  #define SourceDir "..\dist"
#endif
[Setup]
; GUID estável: permite ao Windows reconhecer reinstalações como atualizações.
AppId={{A8A4D4E2-3D4C-4B33-97D0-029292632391}
AppName=Procurador de Anúncios
AppVersion={#AppVersion}
AppPublisher=Procurador de Anúncios
; Instalação por utilizador, sem pedir credenciais de administrador.
DefaultDirName={localappdata}\Programs\Procurador de Anúncios
DefaultGroupName=Procurador de Anúncios
UninstallDisplayIcon={app}\ProcuradorAnuncios.exe
OutputDir=..\dist
OutputBaseFilename=ProcuradorAnuncios-Setup
; A configuração e a cache ficam fora de {app}, em %APPDATA%, e são preservadas.
PrivilegesRequired=lowest
ArchitecturesInstallIn64BitMode=x64compatible
CloseApplications=yes
RestartApplications=no
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
SetupLogging=yes

[Files]
; O executável já contém o runtime Python e os recursos da interface.
Source: "{#SourceDir}\ProcuradorAnuncios.exe"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
; O atalho do ambiente de trabalho é opcional; o menu Iniciar é criado sempre.
Name: "{group}\Procurador de Anúncios"; Filename: "{app}\ProcuradorAnuncios.exe"
Name: "{autodesktop}\Procurador de Anúncios"; Filename: "{app}\ProcuradorAnuncios.exe"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Criar atalho no ambiente de trabalho"; GroupDescription: "Atalhos adicionais:"

[Run]
; A última página do assistente permite abrir a aplicação após a instalação.
Filename: "{app}\ProcuradorAnuncios.exe"; Description: "Abrir Procurador de Anúncios"; Flags: nowait postinstall skipifsilent
