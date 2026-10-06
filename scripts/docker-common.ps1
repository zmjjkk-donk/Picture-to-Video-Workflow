function Resolve-DockerExecutable {
    param([string]$ExplicitPath)
    if ($ExplicitPath) {
        if (-not (Test-Path -LiteralPath $ExplicitPath -PathType Leaf)) {
            throw '指定的 Docker 可执行文件不存在。'
        }
        return (Resolve-Path -LiteralPath $ExplicitPath).Path
    }
    $command = Get-Command docker -ErrorAction SilentlyContinue
    if ($command) { return $command.Source }
    $candidates = @(
        (Join-Path $env:LOCALAPPDATA 'Programs\DockerDesktop\resources\bin\docker.exe'),
        'C:\Program Files\Docker\Docker\resources\bin\docker.exe'
    )
    foreach ($candidate in $candidates) {
        if (Test-Path -LiteralPath $candidate -PathType Leaf) { return $candidate }
    }
    throw '找不到 Docker。请安装 Docker Desktop，或使用 -DockerExe 指定完整路径。'
}

function Assert-DockerLinuxReady {
    param([string]$Executable)
    $engineType = & $Executable info --format '{{.OSType}}' 2>&1
    if ($LASTEXITCODE -ne 0) { throw 'Docker 引擎不可连接。请打开 Docker Desktop 并等待引擎启动。' }
    if (($engineType | Out-String).Trim() -ne 'linux') { throw '本项目需要 Docker Linux 容器模式。' }
}

function Resolve-ProjectPath {
    param([string]$PathValue, [string]$ProjectRoot)
    if ([System.IO.Path]::IsPathRooted($PathValue)) {
        return [System.IO.Path]::GetFullPath($PathValue)
    }
    return [System.IO.Path]::GetFullPath((Join-Path $ProjectRoot $PathValue))
}

function Assert-DockerEnvFile {
    param([string]$FilePath)
    if (-not (Test-Path -LiteralPath $FilePath -PathType Leaf)) { throw '指定的容器环境文件不存在。' }
    foreach ($rawLine in Get-Content -LiteralPath $FilePath -Encoding UTF8) {
        $line = $rawLine.Trim()
        if (-not $line -or $line.StartsWith('#')) { continue }
        if ($line -notmatch '^[A-Za-z_][A-Za-z0-9_]*=') { throw '容器环境文件必须使用 KEY=value 格式，不能使用 export。' }
        $value = $line.Substring($line.IndexOf('=') + 1)
        if ($value.StartsWith('"') -or $value.StartsWith("'")) {
            throw 'docker --env-file 不去除引号，请移除环境变量值外层的引号。'
        }
    }
}
