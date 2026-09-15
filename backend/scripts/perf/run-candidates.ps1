<#
.SYNOPSIS
    article 인덱스 후보 성능 측정 자동화.

.DESCRIPTION
    후보를 하나씩 생성 -> ANALYZE -> measure.sql 2회 -> write-test.sql -> 삭제 하며
    baseline 대비 배수를 표로 출력합니다.

    손으로 하면 틀리기 쉬운 것들을 스크립트가 강제합니다:
      * measure.sql 을 2회 돌리고 2회차만 채택 (1회차는 콜드 캐시)
      * 후보 간 반드시 DROP (섞이면 어느 쪽 효과인지 알 수 없음)
      * 인덱스 생성 후 ANALYZE (빼먹으면 플래너가 새 인덱스를 안 씀)

.PARAMETER Mode
    single : 후보를 하나씩 단독 측정 (기본)
    combo  : 조합(S1~S4) 측정
    both   : 둘 다

.PARAMETER Only
    쉼표로 구분한 후보 이름만 측정. 예: -Only G4,G5
    빠르게 확인할 때 사용.

.PARAMETER OutDir
    결과 저장 위치. 기본 .\perf-results

.EXAMPLE
    .\scripts\perf\run-candidates.ps1
    .\scripts\perf\run-candidates.ps1 -Mode both
    .\scripts\perf\run-candidates.ps1 -Only G4,G5

.NOTES
    ⚠ 이 파일은 반드시 UTF-8 **BOM 포함**으로 저장하십시오.
      Windows PowerShell 5.1 은 BOM 이 없으면 .ps1 을 ANSI(cp949)로 읽습니다.
      한글 주석이 깨지는 데서 끝나지 않고, 깨진 바이트가 따옴표로 해석되면
      파싱이 어긋나 제어 흐름이 조용히 바뀝니다 (실제로 겪었습니다).
      편집 후 BOM 확인:
        (Get-Content $f -Encoding Byte -TotalCount 3) -join ' '   # 239 187 191 이어야 함

    선행 조건 — DOCS/PERF.md 1장 참조
      1. perf 컨테이너 기동
      2. 마이그레이션 적용 (perf DB 는 빈 Postgres 라 Flyway 가 돈 적이 없음)
      3. generate-bulk.sql 로 데이터 생성
      4. measure.sql / write-test.sql 을 컨테이너 /tmp 로 복사
#>
[CmdletBinding()]
param(
    [ValidateSet('single','combo','both')]
    [string]$Mode = 'single',
    [string[]]$Only,
    [string]$OutDir = '.\perf-results',
    [string]$Container = 'witw-postgres-perf'
)

$ErrorActionPreference = 'Stop'

# measure.sql 의 EXPLAIN 블록 순서와 1:1 대응합니다.
# measure.sql 에 쿼리를 추가하면 여기도 같이 고쳐야 합니다.
$Labels = @('C1','C2','C3','C4','C5','C6','C7','C8','C9','C10','C11',
            'D1','D2','D3','D4','D5','E1','E2','E3','E4','F1','F2')

$Candidates = [ordered]@{
    G1     = 'idx_article_country_published  ON article (publisher_country_code, published_at) WHERE deleted_at IS NULL'
    G2     = 'idx_article_published_theme    ON article (published_at, theme_id) WHERE deleted_at IS NULL'
    G2alt  = 'idx_article_theme_published    ON article (theme_id, published_at) WHERE deleted_at IS NULL'
    G4     = 'idx_article_theme_relevance    ON article (theme_id, theme_relevance_score DESC, id ASC) WHERE deleted_at IS NULL'
    G5     = 'idx_article_issue_similarity   ON article (issue_id, issue_similarity DESC NULLS LAST, id ASC) WHERE deleted_at IS NULL'
    G7     = 'idx_article_issue_published    ON article (issue_id, published_at) WHERE deleted_at IS NULL'
}

$Combos = [ordered]@{
    S1 = @('G1','G2','G4','G5','G7')
    S2 = @('G1','G4','G5','G7')
    S3 = @('G4','G5','G7')
    S4 = @('G1','G4','G5')
}

# ---------------------------------------------------------------------------

function Invoke-Psql {
    param([string]$Sql)
    docker exec $Container psql -U postgres -d witw -q -c $Sql | Out-Null
}

function Invoke-PsqlScalar {
    param([string]$Sql)
    (docker exec $Container psql -U postgres -d witw -t -A -c $Sql).Trim()
}

function Get-IndexName {
    param([string]$Tag)
    ($Candidates[$Tag] -split '\s+')[0]
}

function Remove-AllCandidateIndexes {
    # DROP 과 VACUUM 을 한 -c 에 묶으면 안 됩니다. psql 은 -c 의 여러 문장을 한
    # 트랜잭션으로 묶는데 VACUUM 은 트랜잭션 안에서 못 돌고, 실패하면서 DROP 까지
    # 롤백됩니다. 반드시 따로 실행하십시오.
    # client_min_messages 를 올려 "does not exist, skipping" NOTICE 를 숨깁니다.
    # SET 과 DROP 은 한 트랜잭션에 묶여도 무방합니다 (VACUUM 만 안 됩니다).
    $names = $Candidates.Keys | ForEach-Object { Get-IndexName $_ }
    Invoke-Psql ("SET client_min_messages=warning; DROP INDEX IF EXISTS " + ($names -join ', ') + ";")
}

function Measure-Read {
    param([string]$Tag)
    # 1회차는 캐시 워밍용이므로 결과를 버립니다.
    docker exec $Container psql -U postgres -d witw -f /tmp/measure.sql | Out-Null
    $raw = docker exec $Container psql -U postgres -d witw -f /tmp/measure.sql
    $raw | Out-File -FilePath (Join-Path $OutDir "$Tag.txt") -Encoding utf8

    $times = @()
    foreach ($m in ($raw | Select-String -Pattern 'Execution Time: ([0-9.]+)' -AllMatches)) {
        foreach ($g in $m.Matches) { $times += [double]$g.Groups[1].Value }
    }
    if ($times.Count -ne $Labels.Count) {
        Write-Warning "$Tag : EXPLAIN 블록 $($times.Count)개 (예상 $($Labels.Count)개). measure.sql 과 `$Labels 가 어긋났을 수 있습니다."
    }
    return $times
}

function Measure-Write {
    param([string]$Tag)
    $raw = docker exec $Container psql -U postgres -d witw -f /tmp/write-test.sql
    $raw | Out-File -FilePath (Join-Path $OutDir "$Tag.write.txt") -Encoding utf8
    $m = $raw | Select-String -Pattern 'Execution Time: ([0-9.]+)' | Select-Object -First 1
    if ($null -eq $m) { return 0.0 }
    return [double]$m.Matches[0].Groups[1].Value
}

function Get-NewIndexSize {
    $bytes = Invoke-PsqlScalar "SELECT COALESCE(sum(pg_relation_size(indexrelid)),0) FROM pg_stat_user_indexes WHERE relname='article' AND indexrelname LIKE 'idx_%';"
    $heap  = Invoke-PsqlScalar "SELECT pg_relation_size('article');"
    if ([double]$heap -eq 0) { return '0 (0%)' }
    $mb  = [math]::Round([double]$bytes / 1MB, 0)
    $pct = [math]::Round(100.0 * [double]$bytes / [double]$heap, 1)
    return "$mb MB ($pct%)"
}

# ---------------------------------------------------------------------------

if (-not (Test-Path $OutDir)) { New-Item -ItemType Directory -Path $OutDir | Out-Null }

$check = Invoke-PsqlScalar "SELECT count(*) FROM article;"
if ([int]$check -eq 0) {
    throw "article 테이블이 비어 있습니다. generate-bulk.sql 을 먼저 실행하십시오 (DOCS/PERF.md 1장)."
}
Write-Host "article $check 행, 컨테이너 $Container" -ForegroundColor Cyan

$results = [ordered]@{}
$writes  = [ordered]@{}
$sizes   = [ordered]@{}

Write-Host "`n=== baseline (인덱스 0개) ===" -ForegroundColor Yellow
Remove-AllCandidateIndexes
Invoke-Psql "ANALYZE article;"
$results['baseline'] = Measure-Read 'baseline'
$writes['baseline']  = Measure-Write 'baseline'
$sizes['baseline']   = Get-NewIndexSize
Write-Host ("  읽기 합계 {0:N1}ms / 쓰기 {1:N1}ms" -f (($results['baseline'] | Select-Object -First 20) | Measure-Object -Sum).Sum, $writes['baseline'])

$targets = $Candidates.Keys
if ($Only) { $targets = $Candidates.Keys | Where-Object { $Only -contains $_ } }

if ($Mode -in 'single','both') {
    foreach ($tag in $targets) {
        Write-Host "`n=== $tag ===" -ForegroundColor Yellow
        Write-Host "  $($Candidates[$tag])" -ForegroundColor DarkGray
        Remove-AllCandidateIndexes
        Invoke-Psql "CREATE INDEX $($Candidates[$tag]);"
        Invoke-Psql "ANALYZE article;"          # 빼먹으면 플래너가 새 인덱스를 안 씁니다
        $results[$tag] = Measure-Read $tag
        $writes[$tag]  = Measure-Write $tag
        $sizes[$tag]   = Get-NewIndexSize
        Write-Host ("  읽기 합계 {0:N1}ms / 쓰기 {1:N1}ms / 크기 {2}" -f (($results[$tag] | Select-Object -First 20) | Measure-Object -Sum).Sum, $writes[$tag], $sizes[$tag])
    }
}

if ($Mode -in 'combo','both') {
    foreach ($tag in $Combos.Keys) {
        Write-Host "`n=== $tag [$($Combos[$tag] -join ' + ')] ===" -ForegroundColor Yellow
        Remove-AllCandidateIndexes
        foreach ($m in $Combos[$tag]) { Invoke-Psql "CREATE INDEX $($Candidates[$m]);" }
        Invoke-Psql "ANALYZE article;"
        $results[$tag] = Measure-Read $tag
        $writes[$tag]  = Measure-Write $tag
        $sizes[$tag]   = Get-NewIndexSize
        Write-Host ("  읽기 합계 {0:N1}ms / 쓰기 {1:N1}ms / 크기 {2}" -f (($results[$tag] | Select-Object -First 20) | Measure-Object -Sum).Sum, $writes[$tag], $sizes[$tag])
    }
}

Remove-AllCandidateIndexes
Invoke-Psql "ANALYZE article;"

# ---------------------------------------------------------------------------
# 결과표
# ---------------------------------------------------------------------------

$tags = @($results.Keys)
$base = $results['baseline']

Write-Host "`n`n########## 실행 시간 (ms) ##########" -ForegroundColor Cyan
$rows = @()
for ($i = 0; $i -lt $Labels.Count; $i++) {
    $row = [ordered]@{ query = $Labels[$i] }
    foreach ($t in $tags) { $row[$t] = [math]::Round($results[$t][$i], 1) }
    $rows += [pscustomobject]$row
}
$rows | Format-Table -AutoSize | Out-String -Width 200 | Write-Host

Write-Host "########## baseline 대비 배수 (1.0 초과 = 개선, 0.9 미만 = 회귀) ##########" -ForegroundColor Cyan
$rows2 = @()
for ($i = 0; $i -lt $Labels.Count; $i++) {
    $row = [ordered]@{ query = $Labels[$i] }
    foreach ($t in $tags) {
        if ($t -eq 'baseline') { continue }
        $v = $results[$t][$i]
        if ($v -le 0) { $row[$t] = '-' } else { $row[$t] = [math]::Round($base[$i] / $v, 2) }
    }
    $rows2 += [pscustomobject]$row
}
$rows2 | Format-Table -AutoSize | Out-String -Width 200 | Write-Host

Write-Host "########## 쓰기 영향 / 크기 ##########" -ForegroundColor Cyan
$rows3 = @()
foreach ($t in $tags) {
    $delta = if ($writes['baseline'] -gt 0) { [math]::Round(100.0 * ($writes[$t] - $writes['baseline']) / $writes['baseline'], 1) } else { 0 }
    $rows3 += [pscustomobject][ordered]@{
        set          = $t
        'write(ms)'  = [math]::Round($writes[$t], 1)
        'write(%)'   = "$delta%"
        'index size' = $sizes[$t]
        'read total' = [math]::Round(((($results[$t] | Select-Object -First 20) | Measure-Object -Sum).Sum), 1)
        'read x'     = [math]::Round(((($base | Select-Object -First 20) | Measure-Object -Sum).Sum) / ((($results[$t] | Select-Object -First 20) | Measure-Object -Sum).Sum), 2)
    }
}
$rows3 | Format-Table -AutoSize | Out-String -Width 200 | Write-Host

Write-Host "원본 출력: $OutDir" -ForegroundColor DarkGray
Write-Host @"

주의
  * 쓰기 수치는 단발 측정이라 분산이 큽니다 (베이스라인에서도 340~415ms 폭).
    채택 판단에 쓰려면 같은 조합으로 5회 이상 돌려 중앙값을 보십시오.
  * 표 안의 읽기 수치는 배치 측정이라 앞 쿼리가 캐시를 데운 효과가 섞입니다.
    특정 쿼리가 예산 근처면 그 쿼리만 단독으로 재측정하십시오.
  * 판정 기준은 DOCS/PERF.md 2장(0~3층)을 따르십시오.
"@ -ForegroundColor DarkGray
