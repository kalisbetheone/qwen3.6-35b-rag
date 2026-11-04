# Dong bo code tu laptop sang Google Drive (G:\My Drive\vilex-annd = /content/drive/MyDrive/vilex-annd tren Colab).
#   powershell -ExecutionPolicy Bypass -File scripts\sync_to_drive.ps1
# Chi chep them / ghi de file moi hon (/XO), KHONG xoa gi tren Drive.
# Bo qua thu muc sinh ra tren Colab (index, logs, eval\results, frontend\dist) de khong ghi de ket qua o do.
# (File giu ASCII: Windows PowerShell 5.1 doc .ps1 khong BOM theo ma ANSI.)
param([string]$Dest = "G:\My Drive\vilex-annd")

$Src = Split-Path -Parent $PSScriptRoot
$Parent = Split-Path -Parent $Dest
if (-not (Test-Path $Parent)) {
    Write-Error "Khong thay $Parent - Google Drive for Desktop da chay chua?"
    exit 1
}

robocopy $Src $Dest /E /XO /NFL /NDL /NJH /NP /R:2 /W:2 `
  /XD node_modules dist __pycache__ .pytest_cache .venv index logs hf_cache appdata "$Src\eval\results" `
  /XF *.pyc .env.local

# robocopy: ma 0-7 la thanh cong
if ($LASTEXITCODE -ge 8) {
    Write-Error "robocopy loi ($LASTEXITCODE)"
    exit $LASTEXITCODE
}
Write-Host "Da dong bo $Src -> $Dest"
exit 0
