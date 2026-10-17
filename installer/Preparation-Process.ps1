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
