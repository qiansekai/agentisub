# 从 blocks.jsonl 聚合生成 state/songs.json（曲目列表：标题来自 context.md 3.4 曲目表）
$ErrorActionPreference = 'Stop'
$root = 'D:\Kita-Tools\Media\agentisub'

$titles = @{
  '01' = '描き続けた君へ（开场）'
  '02' = 'ディメンション（开场）'
  '03' = '暮れなずむ約束（开场）'
  '04' = 'システムズコア（开场）'
  '05' = 'そして白に還る'
  '06' = 'ラピスのお人形'
  '07' = 'グレイスケイル'
  '08' = '物語りのワルツ'
  '09' = '此処に棘と死を'
  '10' = 'いろはに咲きて'
  '11' = 'ヰ世界の宝石譚'
  '12' = 'シリウスの心臓'
  '13' = '異世界転調リクヱスト'
  '13b' = 'ぼくらの逃避行（with VALIS）'
  '14' = 'new world（with Aiobahn）'
  '15' = 'Capullo（新曲）'
  '16' = 'アンビバレント（新曲）'
  '17' = 'ANGELIC'
  '18' = 'シェイク（with 星界）'
  '19' = '眠りゆく芽吹き（新曲）'
  '20' = 'ARCADIA'
  '21' = 'かたちなきもの'
  '22' = 'みらいのかたち（新曲）'
  'ED' = 'ETERNAL（片尾）'
}

$blocks = @()
Get-Content (Join-Path $root 'state\blocks.jsonl') | ForEach-Object {
  if ($_.Trim()) { $blocks += ($_ | ConvertFrom-Json) }
}
Write-Output ("blocks loaded: " + $blocks.Count)

$lyric = $blocks | Where-Object { $_.kind -eq 'lyric' }
$songs = $lyric | Group-Object song | ForEach-Object {
  $g = $_.Group
  $first = $g | Sort-Object start | Select-Object -First 1
  $last = $g | Sort-Object end | Select-Object -Last 1
  $green = ($g | Where-Object { $_.confidence -eq 'green' } | Measure-Object).Count
  $yellow = ($g | Where-Object { $_.confidence -eq 'yellow' } | Measure-Object).Count
  $red = ($g | Where-Object { $_.confidence -eq 'red' } | Measure-Object).Count
  [pscustomobject]@{
    id = $_.Name
    title = if ($titles.ContainsKey($_.Name)) { $titles[$_.Name] } else { '（未知曲目 ' + $_.Name + '）' }
    t0 = [math]::Round($first.start, 2)
    t1 = [math]::Round($last.end, 2)
    blocks = $g.Count
    green = $green
    yellow = $yellow
    red = $red
  }
} | Sort-Object { if ($_.id -eq 'ED') { 99.9 } else { [double]($_.id -replace '[a-z]', '') + $(if ($_.id -match 'b$') { 0.5 } else { 0 }) } }

$out = @{ songs = @($songs) } | ConvertTo-Json -Depth 4
Set-Content -Path (Join-Path $root 'state\songs.json') -Value $out -Encoding UTF8
Write-Output ("songs.json written: " + $songs.Count + " songs")
$songs | ForEach-Object { Write-Output ("  " + $_.id + " " + $_.title + "  [" + $_.t0 + " - " + $_.t1 + "] blocks=" + $_.blocks + " g=" + $_.green + " y=" + $_.yellow + " r=" + $_.red) }
