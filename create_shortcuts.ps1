# Create Windows Desktop + Start Menu shortcuts for Swara AI (Jarvis)

$ProjectDir = "D:\Coding\Projects\Antigravity"
$TargetBat  = Join-Path $ProjectDir "run_jarvis.bat"
$IconPath   = Join-Path $ProjectDir "jarvis.ico"
$AppName    = "Swara AI"

# --- Desktop Shortcut ---
$DesktopPath = [Environment]::GetFolderPath("Desktop")
$DesktopLnk  = Join-Path $DesktopPath "$AppName.lnk"

$WshShell = New-Object -ComObject WScript.Shell
$Shortcut = $WshShell.CreateShortcut($DesktopLnk)
$Shortcut.TargetPath       = $TargetBat
$Shortcut.WorkingDirectory = $ProjectDir
$Shortcut.IconLocation     = $IconPath
$Shortcut.Description      = "Launch Swara AI Dashboard"
$Shortcut.WindowStyle      = 7   # Minimized (hides console)
$Shortcut.Save()
Write-Output "Created Desktop shortcut: $DesktopLnk"

# --- Start Menu Shortcut ---
$StartMenu    = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs"
$StartMenuLnk = Join-Path $StartMenu "$AppName.lnk"

$Shortcut2 = $WshShell.CreateShortcut($StartMenuLnk)
$Shortcut2.TargetPath       = $TargetBat
$Shortcut2.WorkingDirectory = $ProjectDir
$Shortcut2.IconLocation     = $IconPath
$Shortcut2.Description      = "Launch Swara AI Dashboard"
$Shortcut2.WindowStyle      = 7
$Shortcut2.Save()
Write-Output "Created Start Menu shortcut: $StartMenuLnk"

Write-Output ""
Write-Output "Done. '$AppName' should now appear in:"
Write-Output "  - Desktop"
Write-Output "  - Start Menu / Search"
