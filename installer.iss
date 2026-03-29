; American Prospector — Inno Setup Installer Script
;
; Prerequisites: Run "python build.py" first to create dist/AmericanProspector/
; Then compile this .iss with Inno Setup to create the installer.
;
; Download Inno Setup: https://jrsoftware.org/isinfo.php

[Setup]
AppName=American Prospector
AppVersion=0.1
AppPublisher=American Prospector
DefaultDirName={autopf}\AmericanProspector
DefaultGroupName=American Prospector
OutputBaseFilename=AmericanProspector_Setup
OutputDir=installer_output
Compression=lzma2/ultra64
SolidCompression=yes
SetupIconFile=icon.ico
; Estimated install size in KB (game ~200MB, model downloads separately ~4.7GB)
ExtraDiskSpaceRequired=5000000000
LicenseFile=
WizardStyle=modern
DisableProgramGroupPage=yes
PrivilegesRequired=lowest

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Messages]
WelcomeLabel2=This will install American Prospector on your computer.%n%nThe game includes a ~4.7 GB AI model that will download automatically on first launch. You will need an internet connection for the first run.%n%nFor GPU acceleration (recommended), install NVIDIA CUDA Toolkit 12.x from nvidia.com/cuda-downloads before playing.

[Files]
; Bundle everything from the PyInstaller dist folder
Source: "dist\AmericanProspector\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\American Prospector"; Filename: "{app}\AmericanProspector.exe"
Name: "{commondesktop}\American Prospector"; Filename: "{app}\AmericanProspector.exe"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional options:"

[Run]
Filename: "{app}\AmericanProspector.exe"; Description: "Launch American Prospector"; Flags: nowait postinstall skipifsilent
