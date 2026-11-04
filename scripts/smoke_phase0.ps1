# Phase 0 smoke: signup -> login -> upload CSV via multipart.
# Windows PowerShell 5.1 has no -Form, so the multipart body is built manually
# with a boundary (binary-safe via iso-8859-1 round-trip).
$ErrorActionPreference = 'Stop'
$base = 'http://127.0.0.1:8000'
$email = 'p0_' + [guid]::NewGuid().ToString('N').Substring(0, 8) + '@test.com'
$LF = "`r`n"

# Signup (ignore "already exists" style failures - login below is the real check)
try {
  Invoke-RestMethod -Uri "$base/auth/signup" -Method Post -ContentType 'application/json' `
    -Body ('{"email":"' + $email + '","password":"testpass123","full_name":"P0"}') | Out-Null
} catch { }

$login = Invoke-RestMethod -Uri "$base/auth/login" -Method Post -ContentType 'application/json' `
  -Body ('{"email":"' + $email + '","password":"testpass123"}')
Write-Host "LOGIN OK (token received: $($null -ne $login.access_token))"

$headers = @{ Authorization = 'Bearer ' + $login.access_token }
$boundary = [guid]::NewGuid().ToString()
$enc = [System.Text.Encoding]::GetEncoding('iso-8859-1')
$bytes = [System.IO.File]::ReadAllBytes((Join-Path $PSScriptRoot '..\backend\data\sample_statement.csv'))
$body = "--$boundary$LF" +
        'Content-Disposition: form-data; name="file"; filename="sample_statement.csv"' + "$LF" +
        'Content-Type: text/csv' + "$LF$LF" +
        $enc.GetString($bytes) +
        "$LF--$boundary--$LF"

$r = Invoke-RestMethod -Uri "$base/upload-statement" -Method Post -Headers $headers `
  -ContentType "multipart/form-data; boundary=$boundary" -Body $body
Write-Host ("UPLOAD OK income=" + $r.savings_summary.total_income + " categories=" + (($r.category_totals.Keys | Sort-Object) -join ','))
