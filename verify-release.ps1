$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
$version = & .\.venv\Scripts\python.exe -c "from main import VERSION; print(VERSION)"
if ($LASTEXITCODE -ne 0) { throw 'Could not read application version' }
$executable = (Resolve-Path "dist/LongScreenshotSplitter-v$version-windows-x64.exe").Path
$versionInfo = (Get-Item -LiteralPath $executable).VersionInfo
if ($versionInfo.ProductVersion -ne $version -or $versionInfo.FileVersion -ne "$version.0.0") {
    throw 'Executable version does not match the application'
}
$reportPath = Join-Path $PSScriptRoot 'dist/self-test.json'
if (Test-Path -LiteralPath $reportPath) { Remove-Item -LiteralPath $reportPath }
$process = Start-Process -FilePath $executable -ArgumentList @('--self-test', "`"$reportPath`"") -WindowStyle Hidden -PassThru
if (-not $process.WaitForExit(120000)) {
    Stop-Process -Id $process.Id -ErrorAction SilentlyContinue
    throw 'Packaged self-test timed out'
}
$process.Refresh()
if ($process.ExitCode -ne 0) { throw "Packaged self-test failed: exit code $($process.ExitCode)" }
$report = Get-Content -LiteralPath $reportPath -Raw | ConvertFrom-Json
if ($report.ok -ne $true -or $report.frozen -ne $true -or $report.version -ne $version) {
    throw 'Packaged self-test did not verify this executable version'
}
$checksum = (Get-FileHash -LiteralPath $executable -Algorithm SHA256).Hash.ToLowerInvariant()
"$checksum  $([System.IO.Path]::GetFileName($executable))" | Set-Content -LiteralPath 'dist/SHA256SUMS.txt' -Encoding ascii
Write-Output "Verified LongScreenshotSplitter v$version"
Write-Output ($report | ConvertTo-Json -Depth 5)
Get-Content -LiteralPath 'dist/SHA256SUMS.txt'
