[CmdletBinding()]
param(
    [ValidatePattern('^[a-z0-9][a-z0-9._/:-]*$')][string]$Image = 'outfit-studio:docker-v1',
    [ValidatePattern('^[A-Za-z0-9][A-Za-z0-9_.-]*$')][string]$Name = 'outfit-studio',
    [ValidateRange(1,65535)][int]$Port = 8000,
    [string]$DataDir = 'docker-data',
    [string]$EnvFile = '',
    [string]$DockerExe = '',
    [switch]$DryRun
)
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'docker-common.ps1')
$projectRoot = Split-Path -Parent $PSScriptRoot
$dockerPath = Resolve-DockerExecutable $DockerExe
$dataPath = Resolve-ProjectPath $DataDir $projectRoot
if ($dataPath.Contains(',')) { throw '数据目录不能包含逗号，Docker --mount 使用逗号分隔字段。' }
if ((Test-Path -LiteralPath $dataPath) -and -not (Test-Path -LiteralPath $dataPath -PathType Container)) {
    throw '数据目录指向了文件，请指定文件夹。'
}
$configPath = ''
if ($EnvFile) {
    $configPath = Resolve-ProjectPath $EnvFile $projectRoot
} elseif (Test-Path -LiteralPath (Join-Path $projectRoot '.env.docker') -PathType Leaf) {
    $configPath = Join-Path $projectRoot '.env.docker'
}
if ($configPath) { Assert-DockerEnvFile $configPath }
$dockerArguments = @('run', '--detach', '--name', $Name, '--restart', 'unless-stopped',
    '--stop-timeout', '150', '--label', 'outfit-studio.purpose=application',
    '--publish', "127.0.0.1:${Port}:8000", '--mount', "type=bind,source=$dataPath,target=/app/data")
if ($configPath) { $dockerArguments += @('--env-file', $configPath) }
# Keep the persistent path fixed even if an external env file overrides it.
$dockerArguments += @('--env', 'APP_DATA_DIR=/app/data', $Image)
if ($DryRun) {
    return [pscustomobject]@{Executable=$dockerPath; Arguments=$dockerArguments; DataDir=$dataPath; EnvFile=$configPath}
}
Assert-DockerLinuxReady $dockerPath
New-Item -ItemType Directory -Force -Path $dataPath | Out-Null
& $dockerPath @dockerArguments
if ($LASTEXITCODE -ne 0) { throw "容器启动失败，退出码 $LASTEXITCODE。请检查容器名、端口及目录权限。" }
Write-Host "工作台：http://127.0.0.1:$Port/"
Write-Host "数据目录：$dataPath"
Write-Host '首次运行请在系统设置中选择 Mock 演示 Provider；配置 Agnes Key 后可选择真实生成。'
