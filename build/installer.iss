; ============================================================
;  Expediente Extractor — Inno Setup script
;  Genera un autoinstalable que preserva config.json existente
;  Compila con: iscc build\installer.iss
; ============================================================

#define AppName      "Expediente Extractor"
#define AppVersion   "1.0"
#define AppPublisher "IABD - FP Mislata"
#define AppExeName   "ExpedienteExtractor.exe"
#define SourceDir    "..\dist\ExpedienteExtractor"
#define OutputDir    "..\dist"

[Setup]
AppId={{A3F2B1C8-9D4E-4F6A-8B2C-1E5D7F3A9C0B}}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
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

; ── Preserve config.json on reinstall / upgrade ──────────────

[Code]
var
  ConfigBackupPath: String;
  HasBackup: Boolean;

procedure CurStepChanged(CurStep: TSetupStep);
var
  ExistingConfig: String;
begin
  if CurStep = ssInstall then
  begin
    // Backup config.json if it already exists
    ExistingConfig := ExpandConstant('{app}\config.json');
    HasBackup := FileExists(ExistingConfig);
    if HasBackup then
    begin
      ConfigBackupPath := ExpandConstant('{tmp}\expediente_config_backup.json');
      FileCopy(ExistingConfig, ConfigBackupPath, False);
    end;
  end;

  if CurStep = ssPostInstall then
  begin
    // Restore config.json after install
    if HasBackup and FileExists(ConfigBackupPath) then
    begin
      FileCopy(ConfigBackupPath, ExpandConstant('{app}\config.json'), False);
      DeleteFile(ConfigBackupPath);
    end;
  end;
end;
