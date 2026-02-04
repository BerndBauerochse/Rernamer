# Quick Deployment Script
# Dieses Script erstellt das Deployment-Paket OHNE Daten

Write-Host "=== Audiobook Renamer - Deployment Paket erstellen ===" -ForegroundColor Cyan
Write-Host ""

# Prüfe ob wir im richtigen Ordner sind
if (-not (Test-Path "backend/renamer_core.py")) {
    Write-Host "FEHLER: Bitte führe das Script im audiobook_renamer_web Ordner aus!" -ForegroundColor Red
    exit 1
}

# Version
$version = "v2.1_abridged_fix"
$date = Get-Date -Format "yyyyMMdd_HHmm"
$filename = "audiobook_renamer_deploy_${version}_${date}.zip"

Write-Host "Version: $version" -ForegroundColor Green
Write-Host "Dateiname: $filename" -ForegroundColor Green
Write-Host ""

# Dateien sammeln
$filesToInclude = @(
    "backend",
    "frontend", 
    "Dockerfile",
    "docker-compose.yml",
    "README.md",
    "PROJECT_DOCUMENTATION.md",
    "CHANGELOG_ABRIDGED_FIX.md",
    "SAFE_UPDATE_GUIDE.md"
)

# Prüfe ob alle Dateien existieren
Write-Host "Prüfe Dateien..." -ForegroundColor Yellow
$missing = @()
foreach ($file in $filesToInclude) {
    if (-not (Test-Path $file)) {
        $missing += $file
        Write-Host "  ❌ $file (fehlt)" -ForegroundColor Red
    } else {
        Write-Host "  ✅ $file" -ForegroundColor Green
    }
}

if ($missing.Count -gt 0) {
    Write-Host ""
    Write-Host "FEHLER: Folgende Dateien fehlen:" -ForegroundColor Red
    $missing | ForEach-Object { Write-Host "  - $_" -ForegroundColor Red }
    exit 1
}

Write-Host ""
Write-Host "Erstelle ZIP-Archiv..." -ForegroundColor Yellow

# ZIP erstellen
try {
    Compress-Archive -Path $filesToInclude -DestinationPath $filename -Force
    Write-Host "✅ Paket erstellt: $filename" -ForegroundColor Green
} catch {
    Write-Host "❌ Fehler beim Erstellen: $_" -ForegroundColor Red
    exit 1
}

# Größe anzeigen
$size = (Get-Item $filename).Length / 1MB
Write-Host ""
Write-Host "Paketgröße: $([math]::Round($size, 2)) MB" -ForegroundColor Cyan

Write-Host ""
Write-Host "=== Nächste Schritte ===" -ForegroundColor Cyan
Write-Host "1. Auf Server hochladen:" -ForegroundColor Yellow
Write-Host "   scp $filename root@DEINE-SERVER-IP:~/" -ForegroundColor White
Write-Host ""
Write-Host "2. WICHTIG: Lies SAFE_UPDATE_GUIDE.md für sichere Installation!" -ForegroundColor Yellow
Write-Host ""
Write-Host "3. Auf Server entpacken und installieren (siehe Guide)" -ForegroundColor Yellow
Write-Host ""
