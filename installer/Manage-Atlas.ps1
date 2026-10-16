param(
    [ValidateSet('Install','Uninstall')][string]$Mode = 'Install',
    [string]$LauncherRoot,
    [string]$PackageRoot = (Split-Path -Parent $PSScriptRoot),
    [string]$CancellationFile,
    [switch]$NoDialog
)
$ErrorActionPreference = 'Stop'
$stockHash = $null
$maintenanceHandle = $null
$maintenancePath = $null
$priorMaintenanceToken = $env:BB_ATLAS_MAINTENANCE_TOKEN
function Hash([string]$p) { (Get-FileHash -LiteralPath $p -Algorithm SHA256).Hash.ToLowerInvariant() }
function Read-Json([string]$p) { Get-Content -LiteralPath $p -Raw -Encoding UTF8 | ConvertFrom-Json }
function Write-Json([string]$p, $value) {
    $text = ($value | ConvertTo-Json -Depth 100) + "`n"
    $temp = $p + '.tmp-' + [guid]::NewGuid().ToString('N')
    [IO.File]::WriteAllText($temp, $text, (New-Object Text.UTF8Encoding($false)))
    if (Test-Path -LiteralPath $p) { [IO.File]::Replace($temp,$p,[System.Management.Automation.Language.NullString]::Value) } else { [IO.File]::Move($temp,$p) }
}
function Same-Path([string]$a,[string]$b) { [string]::Equals([IO.Path]::GetFullPath($a).TrimEnd('\'),[IO.Path]::GetFullPath($b).TrimEnd('\'),[StringComparison]::OrdinalIgnoreCase) }
function No-Running-Game([string]$port,[string]$package) {
    $running = @(Get-Process -Name Bloodborne,Bloodborne.stock,bb-probe -ErrorAction SilentlyContinue | Where-Object {
        $_.Path -and ($_.Path.StartsWith($port+'\',[StringComparison]::OrdinalIgnoreCase) -or $_.Path.StartsWith($package+'\',[StringComparison]::OrdinalIgnoreCase))
    })
    if ($running.Count) { throw 'Close Bloodborne and its launcher before installing or uninstalling Atlas.' }
}
function Profile-Path {
    if ($env:BB_LAUNCHER_SETTINGS_ROOT) { return Join-Path $env:BB_LAUNCHER_SETTINGS_ROOT 'settings.json' }
    Join-Path $env:APPDATA 'bbport-launcher\settings.json'
}
function Set-Field($obj,[string]$name,$value) { $obj | Add-Member -MemberType NoteProperty -Name $name -Value $value -Force }
function Fail-PreparationTreeStop([System.Diagnostics.Process]$process,[string]$cancelPath,[string]$reason,$taskkillExitCode=$null) {
    $script:PreparationTreeStopFailed = $true
    $stopMarker = Join-Path (Split-Path -Parent $cancelPath) 'preparation-stop-failed.json'
    $escapedReason = $reason.Replace('\','\\').Replace('"','\"')
    $markerJson = '{"parent_pid":'+$process.Id+',"reason":"'+$escapedReason+'"'
    if ($null -ne $taskkillExitCode) { $markerJson += ',"taskkill_exit_code":'+$taskkillExitCode }
    $markerJson += '}'
    try {
        $markerEncoding = New-Object Text.UTF8Encoding($false)
        [IO.File]::WriteAllText($stopMarker,$markerJson,$markerEncoding)
    } catch { $script:PreparationTreeStopMarkerError = $_.Exception.Message }
    try { if (-not $process.HasExited) { $process.Kill() } } catch { }
    try { $null = $process.WaitForExit(5000) } catch { }
    throw "Windows could not verify termination of the owned preparation process tree ($reason). The launcher remains unchanged; keep this package folder and its logs for recovery until the generator has stopped."
}
function Stop-PreparationProcessTree([System.Diagnostics.Process]$process,[string]$cancelPath,[int]$graceMilliseconds=15000) {
    if ($process.HasExited) { return }
    [IO.File]::WriteAllText($cancelPath,'cancel')
    if ($process.WaitForExit($graceMilliseconds)) { return }

    # The stock frozen launcher owns the Python preparation process, which in
    # turn owns the generator. Killing only the launcher can leave the generator
    # writing into the package while the install transaction rolls back.
    $killer = $null
    try {
        $taskkill = Join-Path $env:SystemRoot 'System32\taskkill.exe'
        if (-not (Test-Path -LiteralPath $taskkill -PathType Leaf)) { Fail-PreparationTreeStop $process $cancelPath 'taskkill.exe is unavailable' }
        $killStart = New-Object System.Diagnostics.ProcessStartInfo
        $killStart.FileName = $taskkill
        $killStart.Arguments = '/PID ' + $process.Id + ' /T /F'
        $killStart.UseShellExecute = $false
        $killStart.CreateNoWindow = $true
        $killStart.RedirectStandardOutput = $true
        $killStart.RedirectStandardError = $true
        $killer = New-Object System.Diagnostics.Process
        $killer.StartInfo = $killStart
        $null = $killer.Start()
        $killerStdout = $killer.StandardOutput.ReadToEndAsync()
        $killerStderr = $killer.StandardError.ReadToEndAsync()
        if (-not $killer.WaitForExit(10000)) {
            try { $killer.Kill() } catch { }
            Fail-PreparationTreeStop $process $cancelPath 'taskkill.exe timed out'
        }
        $null = $killerStdout.GetAwaiter().GetResult()
        $null = $killerStderr.GetAwaiter().GetResult()
        if ($killer.ExitCode -ne 0) { Fail-PreparationTreeStop $process $cancelPath 'taskkill.exe returned failure' $killer.ExitCode }
    } catch {
        if ($script:PreparationTreeStopFailed) { throw }
        $exit = $null
        if ($killer -and $killer.HasExited) { $exit = $killer.ExitCode }
        Fail-PreparationTreeStop $process $cancelPath ("taskkill attempt failed: " + $_.Exception.Message) $exit
    }

    # Do not let the caller enter transaction rollback until the exact process
    # handle we started is confirmed exited. WaitForExit is safe here because
    # taskkill has already targeted only this owned PID and its descendants.
    if (-not $process.WaitForExit(10000)) { Fail-PreparationTreeStop $process $cancelPath 'parent did not exit after tree kill' $killer.ExitCode }
    $process.Refresh()
    if (-not $process.HasExited) { Fail-PreparationTreeStop $process $cancelPath 'parent exit could not be verified' $killer.ExitCode }
}
function Prepare-Maps([string]$launcher,[string]$package,[string]$game,[string]$state) {
    $tool=Join-Path $package 'tools\prepare.py'
    $cancel=if ($CancellationFile) { [IO.Path]::GetFullPath($CancellationFile) } else { Join-Path $state 'cancel-preparation.request' }
    $stdout=Join-Path $state 'prepare.stdout.log'
    $stderr=Join-Path $state 'prepare.stderr.log'
    $arguments='--script "'+$tool+'" --game-dir "'+$game+'" --output-dir "'+$package+'" --headless --cancel-file "'+$cancel+'"'
    Write-Host 'Preparing your local maps (usually 5-15 minutes). No game files are changed.'
    # Own the .NET process handle directly. Windows PowerShell 5.1 can lose the
    # ExitCode on a long-running Start-Process -PassThru GUI-subsystem executable.
    $start=New-Object System.Diagnostics.ProcessStartInfo
    $start.FileName=$launcher
    $start.Arguments=$arguments
    $start.UseShellExecute=$false
    $start.CreateNoWindow=$true
    $start.RedirectStandardOutput=$true
    $start.RedirectStandardError=$true
    $process=New-Object System.Diagnostics.Process
    $process.StartInfo=$start
    $null=$process.Start()
    $null=$process.Handle
    $stdoutTask=$process.StandardOutput.ReadToEndAsync()
    $stderrTask=$process.StandardError.ReadToEndAsync()
    $progressLog=Join-Path $package 'state\preparation.log'
    $lineCount=0
    try {
        while(-not $process.HasExited) {
            if(Test-Path -LiteralPath $progressLog) {
                $lines=@(Get-Content -LiteralPath $progressLog -Encoding UTF8)
                for($i=$lineCount;$i -lt $lines.Count;$i++) {
                    try {
                        $record=$lines[$i]|ConvertFrom-Json
                        if($record.stage -eq 'complete' -and $record.prepared -eq $true){Write-Host '100% Local maps verified.'}
                        elseif($null -ne $record.progress){Write-Host ("{0}% {1}" -f ([Math]::Min(95,[Math]::Round(.95*$record.progress))),$record.stage)}
                    } catch { }
                }
                $lineCount=$lines.Count
            }
            Start-Sleep -Milliseconds 500
            $process.Refresh()
        }
        $process.WaitForExit()
        [IO.File]::WriteAllText($stdout,$stdoutTask.GetAwaiter().GetResult(),(New-Object Text.UTF8Encoding($false)))
        [IO.File]::WriteAllText($stderr,$stderrTask.GetAwaiter().GetResult(),(New-Object Text.UTF8Encoding($false)))
        if($process.ExitCode -ne 0){throw "Map preparation failed (exit $($process.ExitCode)). See $stdout and $stderr. The original launcher will be preserved."}
    } finally {
        if(-not $process.HasExited) {
            try { Stop-PreparationProcessTree $process $cancel }
            catch { $script:PreparationTreeStopFailed = $true; throw }
        }
    }
}
function Owned-Path([string]$root,[string]$rel) {
    if ($rel -match '(^[\\/]|:|(^|[\\/])\.\.([\\/]|$))') { throw "Unsafe relative path: $rel" }
    $full = [IO.Path]::GetFullPath((Join-Path $root $rel))
    if (-not $full.StartsWith($root.TrimEnd('\')+'\',[StringComparison]::OrdinalIgnoreCase)) { throw 'Path escaped its root.' }
    $cursor = $full
    while ($cursor -and $cursor.Length -ge $root.Length) {
        if (Test-Path -LiteralPath $cursor) {
            if ((Get-Item -LiteralPath $cursor -Force).Attributes -band [IO.FileAttributes]::ReparsePoint) { throw "Linked path refused: $cursor" }
        }
        if (Same-Path $cursor $root) { break }
        $cursor = Split-Path -Parent $cursor
    }
    return $full
}
try {
    $script:PreparationTreeStopFailed = $false
    $PackageRoot = (Resolve-Path -LiteralPath $PackageRoot).Path
    $state = Join-Path $PackageRoot '.install'
    $packageReceipt = Join-Path $state 'receipt.json'
    if ($Mode -eq 'Uninstall') {
        if (-not (Test-Path -LiteralPath $packageReceipt -PathType Leaf)) { throw 'This extracted package has no installed Atlas receipt.' }
        $receipt = Read-Json $packageReceipt
        if ($receipt.schema -notin @(1,2)) { throw 'Unsupported Atlas installation receipt schema.' }
        $restoreDependencies = Read-Json (Join-Path $state 'dependencies.json')
        $stockHash = [string]$receipt.stock_sha256
        if ($stockHash -notmatch '^[0-9a-f]{64}$' -or -not $restoreDependencies.ordinary_port.launcher_variants.PSObject.Properties[$stockHash]) { throw 'The stock restore identity does not match the original dependency profile.' }
        if (-not (Same-Path $receipt.atlas_folder $PackageRoot)) { throw 'Extracted package moved after installation. Restore its original folder first.' }
        if (-not $LauncherRoot) { $LauncherRoot = $receipt.launcher_root }
    }
    if (-not $LauncherRoot) {
        if ($NoDialog) { throw 'LauncherRoot is required in noninteractive mode.' }
        Add-Type -AssemblyName System.Windows.Forms
        $picker = New-Object Windows.Forms.FolderBrowserDialog
        $picker.Description = 'Select the supported official launcher folder containing Bloodborne.exe.'
        if ($picker.ShowDialog() -ne [Windows.Forms.DialogResult]::OK) { exit 130 }
        $LauncherRoot = $picker.SelectedPath
    }
    $LauncherRoot = (Resolve-Path -LiteralPath $LauncherRoot).Path
    No-Running-Game $LauncherRoot $PackageRoot
    $maintenancePath = Join-Path (Split-Path -Parent $LauncherRoot) ('.'+[IO.Path]::GetFileName($LauncherRoot)+'.atlas-maintenance.lock')
    if (Test-Path -LiteralPath $maintenancePath) {
        $priorLock = Read-Json $maintenancePath
        if (Get-Process -Id $priorLock.pid -ErrorAction SilentlyContinue) { throw 'Another Atlas install or update is active.' }
        Remove-Item -LiteralPath $maintenancePath -Force
    }
    $maintenanceHandle = [IO.File]::Open($maintenancePath,[IO.FileMode]::CreateNew,[IO.FileAccess]::ReadWrite,[IO.FileShare]::Read)
    $env:BB_ATLAS_MAINTENANCE_TOKEN = [guid]::NewGuid().ToString('N')
    $lockBytes = [Text.Encoding]::UTF8.GetBytes(('{"pid":'+$PID+',"token":"'+$env:BB_ATLAS_MAINTENANCE_TOKEN+'"}'))
    $maintenanceHandle.Write($lockBytes,0,$lockBytes.Length)
    $maintenanceHandle.Flush()
    if ($PackageRoot.StartsWith($LauncherRoot+'\',[StringComparison]::OrdinalIgnoreCase) -or (Same-Path $PackageRoot $LauncherRoot)) { throw 'Extract Atlas to a separate folder outside the launcher directory.' }
    $exe = Owned-Path $LauncherRoot 'Bloodborne.exe'
    $stock = Owned-Path $LauncherRoot 'Bloodborne.stock.exe'
    $bridge = Owned-Path $LauncherRoot 'atlas-lite-launcher.py'
    $launcherReceipt = Owned-Path $LauncherRoot 'atlas-lite-install.json'
    $profilePath = Profile-Path
    if ($Mode -eq 'Install') {
        if ((Test-Path -LiteralPath $launcherReceipt) -or (Test-Path -LiteralPath $stock) -or (Test-Path -LiteralPath $bridge)) { throw 'Atlas is installed or has unfinished files. Use Update.cmd from a fresh compatible Atlas package for a combined update, or finish recovery.' }
        $legacyReceipt = Join-Path $LauncherRoot 'atlas-install-receipt.json'
        $legacyActive = (Test-Path -LiteralPath $legacyReceipt)
        if ($legacyActive) { $legacyActive = (Read-Json $legacyReceipt).state -ne 'uninstalled' }
        if ($legacyActive) { throw 'An earlier Atlas adapter is active. Use its recorded uninstall or a combined Atlas update.' }
        $stockHash = Hash $exe
        if (Test-Path -LiteralPath $state) { throw 'This extracted package already contains installation state. Use a fresh extraction or uninstall it first.' }
        $initialManifest = Read-Json (Join-Path $PackageRoot 'manifest.json')
        foreach ($f in $initialManifest.files.PSObject.Properties) {
            if ((Hash (Owned-Path $PackageRoot $f.Name)) -ne $f.Value) { throw "Package hash mismatch: $($f.Name)" }
        }
        $initialDeps = Read-Json (Join-Path $PackageRoot 'dependencies.json')
        if (-not $initialDeps.ordinary_port.launcher_variants.PSObject.Properties[$stockHash] -and (Test-Path -LiteralPath (Join-Path $PackageRoot '.distribution'))) {
            Write-Host 'Selecting the authenticated Atlas adapter for this launcher...'
            $selectStart = New-Object System.Diagnostics.ProcessStartInfo
            $selectStart.FileName = $exe
            $selectStart.Arguments = '--script "'+(Join-Path $PackageRoot 'updates\coordinator.py')+'" --select-initial --package "'+$PackageRoot+'" --launcher "'+$LauncherRoot+'"'
            $selectStart.UseShellExecute = $false
            $selectStart.CreateNoWindow = $true
            $selectStart.RedirectStandardOutput = $true
            $selectStart.RedirectStandardError = $true
            $selectProcess = New-Object System.Diagnostics.Process
            $selectProcess.StartInfo = $selectStart
            $null = $selectProcess.Start()
            $null = $selectProcess.Handle
            $selectOut = $selectProcess.StandardOutput.ReadToEndAsync()
            $selectError = $selectProcess.StandardError.ReadToEndAsync()
            $selectProcess.WaitForExit()
            $selectText = $selectOut.GetAwaiter().GetResult()+$selectError.GetAwaiter().GetResult()
            if ($selectProcess.ExitCode -ne 0) { throw "Atlas adapter selection failed: $selectText" }
        }
        Write-Host 'Verifying Atlas package and existing launcher dependencies...'
        $packageManifestHash = Hash (Join-Path $PackageRoot 'manifest.json')
        $manifest = Read-Json (Join-Path $PackageRoot 'manifest.json')
        if ($manifest.id -ne 'hunters-atlas-lite') { throw 'Wrong package identity.' }
        foreach ($f in $manifest.files.PSObject.Properties) {
            if ((Hash (Owned-Path $PackageRoot $f.Name)) -ne $f.Value) { throw "Package hash mismatch: $($f.Name)" }
        }
        $deps = Read-Json (Join-Path $PackageRoot 'dependencies.json')
        $variantProperty = $deps.ordinary_port.launcher_variants.PSObject.Properties[$stockHash]
        if (-not $variantProperty) {
            $supported = if ($deps.compatibility.upstream_release) { $deps.compatibility.upstream_release } else { 'the package dependency profile' }
            throw "Unsupported launcher SHA-256 $stockHash. This Atlas package supports $supported. Keep the working installation or choose a matching Atlas adapter."
        }
        foreach ($f in $deps.ordinary_port.files.PSObject.Properties) {
            if ((Hash (Owned-Path $LauncherRoot $f.Name)) -ne $f.Value) { throw "Unsupported launcher dependency: $($f.Name)" }
        }
        $variant = $deps.ordinary_port.launcher_variants.PSObject.Properties[$stockHash].Value
        if (-not $variant -or $variant.runtime_dir -ne '_internal') { throw 'Supported stock interpreter metadata is missing.' }
        foreach ($f in $variant.files.PSObject.Properties) {
            if ((Hash (Owned-Path $LauncherRoot $f.Name)) -ne $f.Value) { throw "Unsupported launcher Python runtime: $($f.Name)" }
        }
        $profile = if (Test-Path -LiteralPath $profilePath) { Read-Json $profilePath } else { New-Object PSObject }
        if (-not $profile.game_dir -or -not (Test-Path -LiteralPath (Join-Path $profile.game_dir 'eboot.bin'))) { throw 'Choose your game folder in the ordinary launcher before installing Atlas.' }
        $gameRoot = (Resolve-Path -LiteralPath $profile.game_dir).Path
        $blockedRoots = @($gameRoot)
        foreach ($blocked in $blockedRoots) {
            if ((Same-Path $PackageRoot $blocked) -or $PackageRoot.StartsWith($blocked+'\',[StringComparison]::OrdinalIgnoreCase)) { throw 'Extract Atlas into a separate permanent folder outside the game and launcher directories.' }
        }
        if ((Hash (Join-Path $profile.game_dir 'eboot.bin')) -ne 'd65f0b4f01d59166aed16f8604196d8b7dd805abbf0758b356e8f1354c9429f9') { throw 'Atlas supports the verified CUSA00207 1.09 executable. Other regions and modified executables are not currently verified.' }
        New-Item -ItemType Directory -Path $state | Out-Null
        Copy-Item -LiteralPath $exe -Destination (Join-Path $state 'stock.exe')
        Copy-Item -LiteralPath (Join-Path $PackageRoot 'dependencies.json') -Destination (Join-Path $state 'dependencies.json')
        Copy-Item -LiteralPath (Join-Path $PackageRoot 'manifest.json') -Destination (Join-Path $state 'manifest.json')
        Copy-Item -LiteralPath (Join-Path $PackageRoot 'assets.atlaslite') -Destination (Join-Path $state 'assets.atlaslite')
        if (Test-Path -LiteralPath $profilePath) { Copy-Item -LiteralPath $profilePath -Destination (Join-Path $state 'settings-before.json') }
        $originalFields = @{}
        foreach ($k in @('atlas_dir','atlas_enabled')) { if ($profile.PSObject.Properties[$k]) { $originalFields[$k]=$profile.$k } }
        $installed = $false
        try {
            Copy-Item -LiteralPath $exe -Destination $stock
            if ((Hash $stock) -ne $stockHash) { throw 'Stock backup verification failed.' }
            Set-Field $deps.ordinary_port 'root' $LauncherRoot
            Set-Field $deps.ordinary_port 'launcher_path' 'Bloodborne.stock.exe'
            $variant.path = 'Bloodborne.stock.exe'
            $deps.ordinary_port.launcher_variants = [pscustomobject]@{ $stockHash = $variant }
            Write-Json (Join-Path $PackageRoot 'dependencies.json') $deps
            $manifest.files.'dependencies.json' = Hash (Join-Path $PackageRoot 'dependencies.json')
            Write-Json (Join-Path $PackageRoot 'manifest.json') $manifest
            Prepare-Maps $stock $PackageRoot $gameRoot $state
            $uiPath = Join-Path $PackageRoot 'integration\ui\bbport_launcher_win.py'
            $pythonString = ConvertTo-Json $uiPath -Compress
            [IO.File]::WriteAllText($bridge,"import runpy`nrunpy.run_path($pythonString, run_name='__main__')`n",(New-Object Text.UTF8Encoding($false)))
            Copy-Item -LiteralPath (Join-Path $PackageRoot 'integration\AtlasLauncher.exe') -Destination $exe -Force
            Set-Field $profile 'atlas_dir' $PackageRoot
            Set-Field $profile 'atlas_enabled' $false
            Write-Json $profilePath $profile
            $owned=@{ 'Bloodborne.exe'=(Hash $exe); 'Bloodborne.stock.exe'=(Hash $stock); 'atlas-lite-launcher.py'=(Hash $bridge) }
            $receipt=[pscustomobject]@{schema=2;state='installed';atlas_folder=$PackageRoot;launcher_root=$LauncherRoot;stock_sha256=$stockHash;owned_files=$owned;profile_path=$profilePath;previous_atlas_fields=$originalFields;compatibility=$deps.compatibility;coordinator_protocol=1;artifact_manifest_sha256=$packageManifestHash}
            Write-Json $packageReceipt $receipt
            Write-Json $launcherReceipt $receipt
            $installed=$true
        } finally {
            if (-not $installed) {
                if ($script:PreparationTreeStopFailed -or (Test-Path -LiteralPath (Join-Path $state 'preparation-stop-failed.json'))) {
                    throw 'Preparation shutdown could not be verified. Package rollback was withheld to avoid racing a generator that may still be writing. Keep this folder and its logs for recovery until the generator has stopped.'
                }
                Copy-Item -LiteralPath (Join-Path $state 'stock.exe') -Destination $exe -Force
                foreach ($p in @($stock,$bridge,$launcherReceipt)) { if (Test-Path -LiteralPath $p) { Remove-Item -LiteralPath $p -Force } }
                foreach ($n in @('dependencies.json','manifest.json','assets.atlaslite')) { Copy-Item -LiteralPath (Join-Path $state $n) -Destination (Join-Path $PackageRoot $n) -Force }
                if (Test-Path -LiteralPath (Join-Path $state 'settings-before.json')) { Copy-Item -LiteralPath (Join-Path $state 'settings-before.json') -Destination $profilePath -Force }
                if (Test-Path -LiteralPath $packageReceipt) { Remove-Item -LiteralPath $packageReceipt -Force }
                Write-Json (Join-Path $state 'failed-install.json') ([pscustomobject]@{state='rolled-back';launcher_root=$LauncherRoot})
            }
        }
        Write-Host "Installed. Open your normal Bloodborne launcher, Mods, enable Hunter's Atlas, then Play."
        Write-Host 'Keep this extracted folder in place until you run its Uninstall.cmd.'
    } else {
        if (-not (Same-Path $receipt.launcher_root $LauncherRoot)) { throw 'Uninstall launcher path differs from receipt.' }
        $active = Read-Json $launcherReceipt
        if ($active.state -ne 'installed' -or -not (Same-Path $active.atlas_folder $PackageRoot)) { throw 'Active launcher receipt belongs to another package.' }
        $stockRestored = (Hash $exe) -eq $stockHash
        foreach ($f in $receipt.owned_files.PSObject.Properties) {
            $ownedFile = Owned-Path $LauncherRoot $f.Name
            if ($stockRestored -and ($f.Name -eq 'Bloodborne.exe' -or -not (Test-Path -LiteralPath $ownedFile))) { continue }
            if ((Hash $ownedFile) -ne $f.Value) { throw "Installed file changed; preserve it before uninstall: $($f.Name)" }
        }
        if ((Hash (Join-Path $state 'stock.exe')) -ne $stockHash) { throw 'Original launcher backup failed verification.' }
        if (-not $stockRestored) {
            $restoreStage = Owned-Path $LauncherRoot 'Bloodborne.restore.tmp'
            Copy-Item -LiteralPath (Join-Path $state 'stock.exe') -Destination $restoreStage
            if ((Hash $restoreStage) -ne $stockHash) { throw 'Staged stock restore hash mismatch.' }
            [IO.File]::Replace($restoreStage,$exe,[System.Management.Automation.Language.NullString]::Value)
        }
        if ((Hash $exe) -ne $stockHash) { throw 'Restored launcher hash mismatch.' }
        if (Test-Path -LiteralPath $profilePath) {
            $profile = Read-Json $profilePath
            if ($profile.atlas_dir -and (Same-Path $profile.atlas_dir $PackageRoot)) {
                foreach ($k in @('atlas_dir','atlas_enabled')) {
                    if ($receipt.previous_atlas_fields.PSObject.Properties[$k]) { Set-Field $profile $k $receipt.previous_atlas_fields.$k }
                    else { $profile.PSObject.Properties.Remove($k) }
                }
                Write-Json $profilePath $profile
            }
        }
        foreach ($n in @('dependencies.json','manifest.json','assets.atlaslite')) { Copy-Item -LiteralPath (Join-Path $state $n) -Destination (Join-Path $PackageRoot $n) -Force }
        $receipt.state='uninstalled';Write-Json $packageReceipt $receipt
        foreach ($p in @($stock,$bridge)) { if (Test-Path -LiteralPath $p) { Remove-Item -LiteralPath $p -Force } }
        Remove-Item -LiteralPath $launcherReceipt -Force
        Write-Host 'Uninstalled. The original launcher is restored. Game files, saves, DLC and ordinary settings were preserved.'
    }
} catch {
    Write-Host "Atlas: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
} finally {
    if ($maintenanceHandle) {
        $maintenanceHandle.Dispose()
        if (Test-Path -LiteralPath $maintenancePath) { Remove-Item -LiteralPath $maintenancePath -Force }
    }
    $env:BB_ATLAS_MAINTENANCE_TOKEN = $priorMaintenanceToken
}
