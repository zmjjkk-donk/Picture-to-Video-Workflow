[CmdletBinding()]
param(
    [ValidatePattern('^[a-z0-9][a-z0-9._/:-]*$')][string]$Image = 'outfit-studio:docker-v1',
    [string]$DockerExe = '',
    [switch]$DryRun
)
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'docker-common.ps1')
$projectRoot = Split-Path -Parent $PSScriptRoot
$dockerPath = Resolve-DockerExecutable $DockerExe
$dockerArguments = @('build', '--progress=plain', '--build-arg', 'VITE_API_BASE=/api', '-t', $Image, $projectRoot)
if ($DryRun) {
    return [pscustomobject]@{Executable=$dockerPath; Arguments=$dockerArguments; ProjectRoot=$projectRoot}
}
Assert-DockerLinuxReady $dockerPath
& $dockerPath @dockerArguments
if ($LASTEXITCODE -ne 0) { throw "镜像构建失败，退出码 $LASTEXITCODE。" }
Write-Host "镜像构建完成：$Image"
