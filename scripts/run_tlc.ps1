#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Model-check the TLA+ specs in specs/ with TLC, inside a container.

.DESCRIPTION
    TLC needs a JVM. This repository does not depend on one, so the model
    checker runs in a throwaway container instead of adding a Java toolchain to
    a Python project whose dependency policy admits nothing without an ADR.

    A JDK image and tla2tools.jar are pulled once and cached by Docker. The jar
    is not vendored into the repository: it is a build input, not source, and
    vendoring a 2 MB binary into git is exactly the kind of thing the release
    packager exists to refuse.

    Run:
        pwsh scripts/run_tlc.ps1
        pwsh scripts/run_tlc.ps1 -JarPath C:\path\to\tla2tools.jar

    Exit code is non-zero if any spec fails to check or any property is
    violated, so this is usable as a gate.

.NOTES
    CHECK_DEADLOCK is disabled in the .cfg files. Every terminal state in both
    specs is deliberately a dead end -- a filled order, a published event -- and
    TLC's default deadlock check reports that intended behaviour as an error.
#>
[CmdletBinding()]
param(
    [string]$JarPath = "",
    [string]$Image = "eclipse-temurin:21-jdk",
    [string]$TlcUrl = "https://github.com/tlaplus/tlaplus/releases/latest/download/tla2tools.jar"
)

$ErrorActionPreference = 'Stop'
Set-Location (git rev-parse --show-toplevel)

$SpecsDir = Join-Path $PWD 'specs'
$Work = Join-Path ([System.IO.Path]::GetTempPath()) "aios-tlc-$(Get-Random)"

function Say([string]$m) { Write-Host "== $m" -ForegroundColor Cyan }

Say 'prepare a scratch directory'
New-Item -ItemType Directory -Force $Work | Out-Null
Copy-Item (Join-Path $SpecsDir '*') $Work -Force

if (-not $JarPath) {
    $JarPath = Join-Path $Work 'tla2tools.jar'
}
if (-not (Test-Path $JarPath)) {
    Say "fetch tla2tools.jar -> $JarPath"
    curl.exe -sL -o $JarPath $TlcUrl
}
if (-not (Test-Path $JarPath)) { throw "tla2tools.jar not available at $JarPath" }
Copy-Item $JarPath (Join-Path $Work 'tla2tools.jar') -Force

$Modules = Get-ChildItem (Join-Path $SpecsDir '*.tla') | ForEach-Object { $_.BaseName }
if (-not $Modules) { throw "no .tla modules in $SpecsDir" }

$failed = @()
foreach ($module in $Modules) {
    Say "model-check $module"
    # -metadir points inside the container: TLC needs to write its state set,
    # and the host mount may be read-only for a CI checkout.
    $output = docker run --rm -v "${Work}:/tla" -w /tla $Image `
        java -XX:+UseParallelGC -cp tla2tools.jar tlc2.TLC `
        -workers 1 -metadir "/tmp/meta_$module" "$module.tla" 2>&1
    $code = $LASTEXITCODE
    $output | Select-String -Pattern 'Error|violated|distinct states found|depth of the complete|Model checking completed|No error' |
        ForEach-Object { Write-Host "   $_" }
    if ($code -ne 0) {
        Write-Host "   FAILED (exit $code)" -ForegroundColor Red
        $failed += $module
    }
    else {
        Write-Host "   ok" -ForegroundColor Green
    }
}

Remove-Item -Recurse -Force $Work -ErrorAction SilentlyContinue

if ($failed) {
    Write-Host "`nspec(s) failed: $($failed -join ', ')" -ForegroundColor Red
    exit 1
}
Write-Host "`nall specs checked, no property violated" -ForegroundColor Green
exit 0