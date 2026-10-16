param(
    [string]$LauncherRoot,
    [string]$PackageRoot=(Split-Path -Parent $PSScriptRoot),
    [string]$UpstreamZip,
    [switch]$NoDialog
)
$ErrorActionPreference='Stop'
try {
    $PackageRoot=(Resolve-Path -LiteralPath $PackageRoot).Path
    if (-not $LauncherRoot) {
        if ($NoDialog) { throw 'LauncherRoot is required in noninteractive mode.' }
        Add-Type -AssemblyName System.Windows.Forms
        $picker=New-Object Windows.Forms.FolderBrowserDialog
        $picker.Description='Choose the current Bloodborne launcher with Hunter''s Atlas installed. Close the game and launcher first.'
        if ($picker.ShowDialog() -ne [Windows.Forms.DialogResult]::OK) { exit 130 }
        $LauncherRoot=$picker.SelectedPath
    }
    $LauncherRoot=(Resolve-Path -LiteralPath $LauncherRoot).Path
    $receipt=Get-Content -LiteralPath (Join-Path $LauncherRoot 'atlas-lite-install.json') -Raw -Encoding UTF8 | ConvertFrom-Json
    if ($receipt.state -ne 'installed') { throw 'Atlas is not installed here. For a fresh installation use Install.cmd.' }
    $hostPath=Join-Path $LauncherRoot 'Bloodborne.stock.exe'
    $profile=if ($env:BB_LAUNCHER_SETTINGS_ROOT) { Join-Path $env:BB_LAUNCHER_SETTINGS_ROOT 'settings.json' } else { Join-Path $env:APPDATA 'bbport-launcher/settings.json' }
    $arguments=@('--script',(Join-Path $PackageRoot 'updates/coordinator.py'),'--update','--launcher',$LauncherRoot,
                 '--current-atlas',$receipt.atlas_folder,'--package',$PackageRoot,
                 '--catalog',(Join-Path $PackageRoot 'updates/catalog.json'),'--profile',$profile,'--allow-candidate')
    if ($UpstreamZip) { $arguments+=@('--upstream-zip',(Resolve-Path -LiteralPath $UpstreamZip).Path) }
    Write-Host 'Staging a combined launcher and Atlas update. Your current installation stays available if preparation fails.'
    # GUI-subsystem executables return immediately from PowerShell's call
    # operator. Own the process and its real ExitCode, including on PS 5.1.
    $quotedArguments=@($arguments | ForEach-Object {
        $quoted=[regex]::Replace([string]$_,'(\\*)"','$1$1\"')
        $quoted=[regex]::Replace($quoted,'(\\+)$','$1$1')
        '"'+$quoted+'"'
    }) -join ' '
    $start=New-Object System.Diagnostics.ProcessStartInfo
    $start.FileName=$hostPath
    $start.Arguments=$quotedArguments
    $start.UseShellExecute=$false
    $start.CreateNoWindow=$true
    $start.RedirectStandardOutput=$true
    $start.RedirectStandardError=$true
    $start.EnvironmentVariables['PYTHONIOENCODING']='utf-8'
    $start.EnvironmentVariables['PYTHONUNBUFFERED']='1'
    $start.StandardOutputEncoding=New-Object Text.UTF8Encoding($false)
    $start.StandardErrorEncoding=New-Object Text.UTF8Encoding($false)
    $process=New-Object System.Diagnostics.Process
    $process.StartInfo=$start
    $null=$process.Start()
    $null=$process.Handle
    $stdoutRead=$process.StandardOutput.ReadLineAsync()
    $stderrRead=$process.StandardError.ReadLineAsync()
    while($stdoutRead -or $stderrRead -or -not $process.HasExited) {
        if($stdoutRead -and $stdoutRead.IsCompleted) {
            $line=$stdoutRead.GetAwaiter().GetResult()
            if($null -eq $line){$stdoutRead=$null}
            else { Write-Host $line; $stdoutRead=$process.StandardOutput.ReadLineAsync() }
        }
        if($stderrRead -and $stderrRead.IsCompleted) {
            $line=$stderrRead.GetAwaiter().GetResult()
            if($null -eq $line){$stderrRead=$null}
            else { Write-Host $line -ForegroundColor Red; $stderrRead=$process.StandardError.ReadLineAsync() }
        }
        Start-Sleep -Milliseconds 100
    }
    $process.WaitForExit()
    if ($process.ExitCode -ne 0) { throw 'The update was not activated. Read the message above; your prior installation is retained.' }
    Write-Host 'The verified update request completed. Check the state above and keep its recovery folder.'
} catch {
    Write-Host ('Atlas update: '+$_.Exception.Message) -ForegroundColor Red
    exit 1
}
