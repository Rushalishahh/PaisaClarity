# ============================================================================
# Phase 1 smoke test - PowerShell 5.1 compatible.
#
# Verifies the ingestion overhaul end-to-end against a running backend:
#   1. Signup + login
#   2. For each sample in frontend-react/public/samples (3 CSVs + 1 PDF):
#        - POST /upload-statement/preview  (parse only, nothing saved)
#        - POST /upload-statement          (full analysis, saved)
#   3. Checks that /upload-statement/preview persisted nothing.
#
# Windows PowerShell 5.1 has no Invoke-RestMethod -Form, so every multipart
# body is built manually with a boundary. Binary files (the PDF) are
# embedded byte-exact by decoding the whole body as iso-8859-1, which
# round-trips every byte 0-255 (UTF-8 JSON text survives because the JSON
# uses only ASCII).
#
# Run from the repo root (backend must already be running on :8000):
#     powershell -ExecutionPolicy Bypass -File scripts\smoke_phase1.ps1
# ============================================================================

$ErrorActionPreference = 'Stop'
# Override with SMOKE_BASE when the backend runs on another port, e.g.:
#     $env:SMOKE_BASE = 'http://127.0.0.1:8010'; .\scripts\smoke_phase1.ps1
$base = if ($env:SMOKE_BASE) { $env:SMOKE_BASE } else { 'http://127.0.0.1:8000' }
$LF = "`r`n"
$script:failures = 0

function Step([string]$name, [scriptblock]$check) {
  try {
    & $check
    Write-Host ("PASS  " + $name)
  } catch {
    $script:failures++
    Write-Host ("FAIL  " + $name + "  ->  " + $_.Exception.Message)
  }
}

function Assert($cond, [string]$msg) {
  if (-not $cond) { throw $msg }
}

function Send-Multipart($uri, $headers, $filePath, $filename, $contentType, $extraFields) {
  # Builds a multipart/form-data body manually (PS 5.1 safe) and posts it.
  $boundary = '----smoke' + [guid]::NewGuid().ToString('N')
  $enc = [System.Text.Encoding]::GetEncoding('iso-8859-1')
  $bytes = [System.IO.File]::ReadAllBytes($filePath)
  $body = ''
  foreach ($field in $extraFields) {   # extra text fields BEFORE the file part
    $body += "--$boundary$LF" +
             ('Content-Disposition: form-data; name="' + $field[0] + '"') + "$LF$LF" +
             $field[1] + "$LF"
  }
  $body += "--$boundary$LF" +
           ('Content-Disposition: form-data; name="file"; filename="' + $filename + '"') + "$LF" +
           "Content-Type: $contentType$LF$LF" +
           $enc.GetString($bytes) +
           "$LF--$boundary--$LF"
  $hdrs = $headers
  if ($null -eq $hdrs) { $hdrs = @{} }
  return Invoke-RestMethod -Uri $uri -Method Post -Headers $hdrs `
    -ContentType "multipart/form-data; boundary=$boundary" -Body $body
}

# ------------------------------------------------------------------ 1. auth
$email = 'p1_' + [guid]::NewGuid().ToString('N').Substring(0, 8) + '@test.com'
Step 'signup' {
  $r = Invoke-RestMethod -Uri "$base/auth/signup" -Method Post -ContentType 'application/json' `
    -Body ('{"email":"' + $email + '","password":"testpass123","full_name":"P1"}')
  Assert ($null -ne $r.access_token) 'signup returned no token'
}
$login = Invoke-RestMethod -Uri "$base/auth/login" -Method Post -ContentType 'application/json' `
  -Body ('{"email":"' + $email + '","password":"testpass123"}')
$headers = @{ Authorization = 'Bearer ' + $login.access_token }
Write-Host ("      logged in as " + $email)

# ------------------------------------------------ 2. per-sample preview+upload
$samplesDir = Join-Path $PSScriptRoot '..\frontend-react\public\samples'
$samples = @(
  @{ name = 'sample_statement.csv';                    mime = 'text/csv' },
  @{ name = 'sample_statement_alt_format.csv';         mime = 'text/csv' },
  @{ name = 'sample_statement_alt_format_2.csv';       mime = 'text/csv' },
  @{ name = 'sample_statement.pdf';                    mime = 'application/pdf' }
)
$uploadedTotal = 0
foreach ($s in $samples) {
  $path = Join-Path $samplesDir $s.name
  Assert (Test-Path $path) ("missing sample file: " + $s.name)

  Step ("preview  " + $s.name) {
    $r = Send-Multipart "$base/upload-statement/preview" $headers $path $s.name $s.mime @()
    Assert ($null -ne $r.preview_rows -and $r.preview_rows.Count -gt 0) 'no preview_rows'
    Assert ($null -ne $r.mapping_used -and $r.mapping_used.PSObject.Properties.Count -gt 0) 'empty mapping_used'
    Assert ($r.report.rows_parsed -gt 0) ('report.rows_parsed=' + $r.report.rows_parsed)
  }
  Step ("upload   " + $s.name) {
    $r = Send-Multipart "$base/upload-statement" $headers $path $s.name $s.mime @()
    Assert ($r.savings_summary.total_income -gt 0) 'total_income not > 0'
    Assert ($null -ne $r.ingest_report) 'ingest_report missing'
    $script:uploadedTotal++
  }
}

# --------------------------------- 3. preview must not persist anything
Step 'preview saves nothing' {
  $list = Invoke-RestMethod -Uri "$base/statements" -Method Get -Headers $headers
  Assert ($list.Count -eq $uploadedTotal) `
    ('statements count=' + $list.Count + ' but uploads=' + $uploadedTotal)
}

# ------------------------------------------------------------- summary
Write-Host ''
if ($script:failures -eq 0) {
  Write-Host 'SMOKE RESULT: ALL PASS'
} else {
  Write-Host ('SMOKE RESULT: ' + $script:failures + ' FAILURE(S)')
  exit 1
}
