# build.ps1 — Agentisub 单二进制构建：npm build → 复制 dist 进 server/ → go build（embed 内嵌）
$ErrorActionPreference = 'Stop'
$root = 'D:\Kita-Tools\Media\agentisub'

Write-Output "==== 1/3 npm build ===="
Push-Location "$root\web"
npm run build 2>&1 | Select-Object -Last 2
Pop-Location

Write-Output "==== 2/3 copy dist -> server/dist (for go:embed) ===="
$src = "$root\web\dist"
$dst = "$root\server\dist"
if (Test-Path $dst) { Remove-Item $dst -Recurse -Force }
Copy-Item $src $dst -Recurse

Write-Output "==== 3/3 go build ===="
Push-Location "$root\server"
go build -o "$root\agentisub.exe" main.go
if ($LASTEXITCODE -eq 0) {
  $size = [Math]::Round((Get-Item "$root\agentisub.exe").Length / 1MB, 1)
  Write-Output "OK: $root\agentisub.exe ($size MB, dist 已内嵌)"
} else {
  Write-Output "go build FAILED"
}
Pop-Location
