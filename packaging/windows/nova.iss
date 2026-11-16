#ifndef NovaVersion
  #error NovaVersion is required
#endif

[Setup]
AppId=io.nova.launcher
AppName=Nova Launcher
AppVersion={#NovaVersion}
DefaultDirName={localappdata}\Programs\Nova Launcher
DefaultGroupName=Nova Launcher
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputBaseFilename=nova-launcher-{#NovaVersion}-windows-x64-setup
Compression=lzma2
SolidCompression=yes

[Files]
Source: "bundle\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion

[Icons]
Name: "{group}\Nova Launcher"; Filename: "{app}\runtime\bin\pythonw.exe"; Parameters: """{app}\app\nova.py"""; WorkingDir: "{app}\app"

[Run]
Filename: "{app}\runtime\bin\pythonw.exe"; Parameters: """{app}\app\nova.py"""; WorkingDir: "{app}\app"; Description: "Abrir Nova Launcher"; Flags: nowait postinstall skipifsilent
Filename: "{app}\runtime\bin\pythonw.exe"; Parameters: """{app}\app\nova.py"""; WorkingDir: "{app}\app"; Flags: nowait runasoriginaluser; Check: RelaunchAfterUpdate

[Code]
{ Nova starts the silent installer with /RELAUNCH=1 when it updates itself: open it again when the install ends. }
function RelaunchAfterUpdate: Boolean;
begin
  Result := ExpandConstant('{param:RELAUNCH|0}') = '1';
end;
