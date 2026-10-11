<#
.SYNOPSIS
    Pulls the newest successful GeneralsX x64 build from GitHub, installs it on
    this machine and runs the replay tests with the player's own game data.

.DESCRIPTION
    Meant to run from a Windows scheduled task on the test machine. It only
    downloads build artifacts produced by the "Build Windows x64 (experimental)"
    workflow on the given branch; it never runs workflow code from GitHub.

    Layout under -Root:
      builds\<run id>\     Every tested build (exe + DLLs)
      current              Junction to the newest build that passed the tests
      game\ZeroHour\       Copy of the Zero Hour data (.big files)
      game\Generals\       Copy of the base Generals data
      logs\<run id>\       Test logs and summary.md
      state.json           Last processed run id

    A GitHub token with read access to Actions is read from token.xml in -Root,
    created once with:  Read-Host -AsSecureString | Export-Clixml <Root>\token.xml

.EXAMPLE
    .\test-windows-x64-build.ps1 -Root E:\GeneralsX
#>
# GeneralsX @build Claude 11/10/2026 Pull-based install and replay tests for the Windows x64 build.
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$Root,
    [string]$Repo = "sav-labs/GeneralsX",
    [string]$Branch = "claude/win64-prep",
    [string]$Workflow = "build-windows-x64.yml",
    [string]$ArtifactName = "windows-x64-GeneralsXZH.zip",
    [int]$KeepBuilds = 10,
    [int]$ReplayTimeoutSeconds = 180,
    [switch]$Force
)

$ErrorActionPreference = "Stop"

$zeroHourData = Join-Path $Root "game\ZeroHour"
$generalsData = Join-Path $Root "game\Generals"
$statePath = Join-Path $Root "state.json"
$tokenPath = Join-Path $Root "token.xml"

if (!(Get-ChildItem -Path $zeroHourData -Filter "*.big" -ErrorAction SilentlyContinue)) {
    throw "No Zero Hour .big files in '$zeroHourData'"
}
if (!(Test-Path $tokenPath)) {
    throw "GitHub token not found at '$tokenPath'"
}
$token = [System.Net.NetworkCredential]::new("", (Import-Clixml $tokenPath)).Password
$headers = @{
    "Authorization" = "Bearer $token"
    "Accept" = "application/vnd.github+json"
    "User-Agent" = "GeneralsX-tester"
}

# Find the newest successful build on the branch.
$runsUrl = "https://api.github.com/repos/$Repo/actions/workflows/$Workflow/runs?branch=$([uri]::EscapeDataString($Branch))&status=success&per_page=1"
$run = (Invoke-RestMethod -Uri $runsUrl -Headers $headers).workflow_runs | Select-Object -First 1
if (!$run) {
    Write-Host "No successful build found on $Branch"
    exit 0
}

$lastRunId = $null
if (Test-Path $statePath) {
    $lastRunId = (Get-Content $statePath -Raw | ConvertFrom-Json).runId
}
if (!$Force -and $lastRunId -eq $run.id) {
    Write-Host "Build $($run.id) was already tested"
    exit 0
}

$buildId = "$($run.id)"
$buildDir = Join-Path $Root "builds\$buildId"
$logDir = Join-Path $Root "logs\$buildId"
New-Item -ItemType Directory -Force -Path $buildDir, $logDir | Out-Null
$summaryPath = Join-Path $logDir "summary.md"
"# Build $buildId ($($run.head_sha.Substring(0, 8)))" | Set-Content $summaryPath

# Download and unpack the build.
$artifacts = Invoke-RestMethod -Uri "https://api.github.com/repos/$Repo/actions/runs/$($run.id)/artifacts" -Headers $headers
$artifact = $artifacts.artifacts | Where-Object { $_.name -eq $ArtifactName -and !$_.expired } | Select-Object -First 1
if (!$artifact) {
    throw "Artifact $ArtifactName not found in run $($run.id)"
}
$downloadPath = Join-Path $env:TEMP "gx-$buildId.zip"
Invoke-WebRequest -Uri $artifact.archive_download_url -Headers $headers -OutFile $downloadPath
Expand-Archive -Path $downloadPath -DestinationPath $buildDir -Force
Remove-Item $downloadPath -Force
# The artifact is uploaded unarchived, so the download may hold the build zip itself.
Get-ChildItem -Path $buildDir -Filter "*.zip" | ForEach-Object {
    Expand-Archive -Path $_.FullName -DestinationPath $buildDir -Force
    Remove-Item $_.FullName -Force
}
$gameExe = Join-Path $buildDir "GeneralsXZH.exe"
if (!(Test-Path $gameExe)) {
    throw "GeneralsXZH.exe missing from build $buildId"
}

# The game finds its data through these variables and -setCwd, so the build folder stays clean.
$env:CNC_ZH_INSTALLPATH = $zeroHourData
$env:CNC_GENERALS_INSTALLPATH = $generalsData

# Fetch the public replay set used by upstream CI.
$replaySource = Join-Path $env:TEMP "gx-replays"
Remove-Item $replaySource -Recurse -Force -ErrorAction SilentlyContinue
$replayZip = Join-Path $env:TEMP "gx-replays.zip"
$replayUrls = @(
    "https://gitlab.com/fbraz3/generalsx-replays/-/archive/main/generalsx-replays-main.zip",
    "https://github.com/generalsx-project/GeneralsXReplays/archive/refs/heads/main.zip"
)
$downloaded = $false
foreach ($url in $replayUrls) {
    try {
        Invoke-WebRequest -Uri $url -OutFile $replayZip
        $downloaded = $true
        break
    } catch {
        Write-Host "Replay download failed from $url"
    }
}
if (!$downloaded) {
    throw "Unable to download replay files"
}
Expand-Archive -Path $replayZip -DestinationPath $replaySource -Force
Remove-Item $replayZip -Force

$userData = Join-Path ([Environment]::GetFolderPath("MyDocuments")) "Command and Conquer Generals Zero Hour Data"
$mapsDir = Join-Path $userData "Maps"
$replaysDir = Join-Path $userData "Replays"
New-Item -ItemType Directory -Force -Path $mapsDir, $replaysDir | Out-Null
$sourceRoot = Get-ChildItem -Path $replaySource -Directory | Select-Object -First 1
$sourceMaps = Join-Path $sourceRoot.FullName "GeneralsXZH\Maps"
if (Test-Path $sourceMaps) {
    Copy-Item (Join-Path $sourceMaps "*") $mapsDir -Recurse -Force
}
Copy-Item (Join-Path $sourceRoot.FullName "GeneralsXZH\Replays\*.rep") $replaysDir -Force

# Run every replay headless and require the completed Game Time marker, as upstream CI does.
$passed = 0
$failed = 0
"" | Add-Content $summaryPath
"| Replay | Result | Details |" | Add-Content $summaryPath
"|--------|--------|---------|" | Add-Content $summaryPath
foreach ($replay in (Get-ChildItem $replaysDir -Filter "*.rep" | Sort-Object Name)) {
    $stdout = Join-Path $logDir "$($replay.BaseName)-stdout.log"
    $stderr = Join-Path $logDir "$($replay.BaseName)-stderr.log"
    $arguments = "-headless -setCwd `"$zeroHourData`" -replay `"$($replay.FullName)`""
    $process = Start-Process -FilePath $gameExe -ArgumentList $arguments -WorkingDirectory $zeroHourData `
        -RedirectStandardOutput $stdout -RedirectStandardError $stderr -PassThru
    $timedOut = !$process.WaitForExit($ReplayTimeoutSeconds * 1000)
    if ($timedOut) {
        Stop-Process -Id $process.Id -Force
        $exitCode = "timeout"
    } else {
        $process.WaitForExit()
        $exitCode = $process.ExitCode
    }

    $completion = Select-String -Path $stdout -Pattern '^Elapsed Time: \d{2}:\d{2} Game Time: (\d{2}:\d{2})/\1$' -ErrorAction SilentlyContinue |
        Select-Object -Last 1
    if (!$timedOut -and $exitCode -eq 0 -and $completion) {
        $passed++
        "| $($replay.Name) | PASS | $($completion.Line) |" | Add-Content $summaryPath
    } else {
        $failed++
        $hexCode = if ($exitCode -is [int]) { "0x" + ([int64]$exitCode -band 0xFFFFFFFF).ToString("X8") } else { $exitCode }
        "| $($replay.Name) | FAIL | exit $hexCode |" | Add-Content $summaryPath
    }
}
"" | Add-Content $summaryPath
"**Results: $passed passed, $failed failed**" | Add-Content $summaryPath
Get-Content $summaryPath | Write-Host

@{ runId = $run.id; passed = $passed; failed = $failed; testedAt = (Get-Date).ToString("o") } |
    ConvertTo-Json | Set-Content $statePath

if ($failed -gt 0 -or $passed -eq 0) {
    Write-Host "Build $buildId failed the tests; 'current' still points to the previous build"
    exit 1
}

# Promote the build: 'current' is a junction, so rmdir removes only the link.
$current = Join-Path $Root "current"
if (Test-Path $current) {
    & cmd.exe /c rmdir "$current"
}
New-Item -ItemType Junction -Path $current -Target $buildDir | Out-Null
Write-Host "Build $buildId passed and is now current"

# Keep the newest builds and always keep the promoted one.
Get-ChildItem (Join-Path $Root "builds") -Directory |
    Where-Object { $_.FullName -ne $buildDir } |
    Sort-Object CreationTime -Descending |
    Select-Object -Skip ($KeepBuilds - 1) |
    Remove-Item -Recurse -Force
