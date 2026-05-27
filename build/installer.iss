; ============================================================
;  Expediente Extractor — Inno Setup script
;  Genera un autoinstalable que preserva config.json y config_default.json
;  Compila con: iscc build\installer.iss
; ============================================================

#define AppName      "Expediente Extractor"
#define AppVersion   "1.0.9"
#define AppPublisher "IABD - FP Mislata"
#define AppURL       "https://iabd.cip.fpmislata.com"
#define AppExeName   "ExpedienteExtractor.exe"
#define SourceDir    "..\dist\ExpedienteExtractor"
#define OutputDir    "..\dist"

[Setup]
AppId={{A3F2B1C8-9D4E-4F6A-8B2C-1E5D7F3A9C0B}}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
AppPublisherURL={#AppURL}
AppSupportURL={#AppURL}
AppUpdatesURL={#AppURL}
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
OutputDir={#OutputDir}
OutputBaseFilename=ExpedienteExtractorSetup
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=commandline
DisableProgramGroupPage=yes
UninstallDisplayIcon={app}\{#AppExeName}
VersionInfoVersion={#AppVersion}
VersionInfoDescription={#AppName} Installer
VersionInfoCompany={#AppPublisher}

[Languages]
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"

[Tasks]
Name: "desktopicon"; Description: "Crear acceso directo en el Escritorio"; GroupDescription: "Accesos directos:"; Flags: unchecked

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExeName}"
Name: "{group}\Desinstalar {#AppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExeName}"; Description: "Ejecutar {#AppName}"; Flags: nowait postinstall skipifsilent

; ── Preserve config.json and config_default.json on reinstall / upgrade ───────

[Code]
var
  ConfigBackupPath:        String;
  ConfigDefaultBackupPath: String;
  HasConfigBackup:         Boolean;
  HasConfigDefaultBackup:  Boolean;

procedure CurStepChanged(CurStep: TSetupStep);
var
  ExistingConfig:        String;
  ExistingConfigDefault: String;
begin
  if CurStep = ssInstall then
  begin
    // Backup config.json if it already exists
    ExistingConfig := ExpandConstant('{app}\config.json');
    HasConfigBackup := FileExists(ExistingConfig);
    if HasConfigBackup then
    begin
      ConfigBackupPath := ExpandConstant('{tmp}\expediente_config_backup.json');
      FileCopy(ExistingConfig, ConfigBackupPath, False);
    end;

    // Backup config_default.json if it already exists
    ExistingConfigDefault := ExpandConstant('{app}\config_default.json');
    HasConfigDefaultBackup := FileExists(ExistingConfigDefault);
    if HasConfigDefaultBackup then
    begin
      ConfigDefaultBackupPath := ExpandConstant('{tmp}\expediente_config_default_backup.json');
      FileCopy(ExistingConfigDefault, ConfigDefaultBackupPath, False);
    end;
  end;

  if CurStep = ssPostInstall then
  begin
    // Restore config.json after install
    if HasConfigBackup and FileExists(ConfigBackupPath) then
    begin
      FileCopy(ConfigBackupPath, ExpandConstant('{app}\config.json'), False);
      DeleteFile(ConfigBackupPath);
    end;

    // Restore config_default.json after install
    if HasConfigDefaultBackup and FileExists(ConfigDefaultBackupPath) then
    begin
      FileCopy(ConfigDefaultBackupPath, ExpandConstant('{app}\config_default.json'), False);
      DeleteFile(ConfigDefaultBackupPath);
    end;
  end;
end;
