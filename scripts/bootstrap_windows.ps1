# NEXUS AI - configurazione iniziale del repository GitHub (una sola volta)
# Leggere lo script prima di eseguirlo. Non carica database, password, token o wallet.
param(
    [string]$Source = "$HOME\Desktop\NEXUS_AI_2_0_PAPER_TRADING\NEXUS_AI_2_0"
)
$ErrorActionPreference = "Stop"
$RepoUrl = "https://github.com/manuQ001/NEXUS-AI-Trading.git"
$Dest = Join-Path $HOME "Desktop\NEXUS-AI-Trading-repo"
if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    throw "Git non installato. Installa Git for Windows dal sito ufficiale git-scm.com e riprova."
}
if (-not (Test-Path (Join-Path $Source "src\core.py"))) {
    throw "Cartella NEXUS non trovata: $Source. Specifica -Source con il percorso attuale."
}
if (Test-Path $Dest) {
    if (-not (Test-Path (Join-Path $Dest ".git"))) { throw "Cartella di destinazione già esistente, ma non è un clone Git: $Dest" }
    $remote = git -C $Dest remote get-url origin
    if ($remote -ne $RepoUrl) { throw "Il clone esistente punta a un repository diverso: $remote" }
    git -C $Dest pull --ff-only origin main
    if ($LASTEXITCODE -ne 0) { throw "Impossibile aggiornare il clone Git esistente" }
} else {
    git clone $RepoUrl $Dest
    if ($LASTEXITCODE -ne 0) { throw "Clone GitHub non riuscito" }
}
$paths = @(
    "src\core.py","src\server.py","src\dashboard.html","src\selftest.py",
    "src\maintenance.py","src\backtest.py","src\downloader.py",
    "tests\test_backtest.py","tests\test_core.py",
    "tests\test_maintenance.py","tests\test_downloader.py",
    "updater.py","migrate.py","updates.json","AVVIA_WINDOWS.ps1"
)
foreach ($path in $paths) {
    $from = Join-Path $Source $path
    if (-not (Test-Path $from)) { throw "Manca un file del programma: $from" }
    $to = Join-Path $Dest $path
    New-Item -ItemType Directory -Force -Path (Split-Path $to) | Out-Null
    Copy-Item -LiteralPath $from -Destination $to -Force
}
# Il tag di rilascio deve essere maggiore della V2.4 già installata.
$maintenance = Join-Path $Dest "src\maintenance.py"
$text = Get-Content $maintenance -Raw
if (-not $text.Contains("VERSION='2.4.0'")) { throw "Versione sorgente inattesa: serve NEXUS 2.4" }
$text = $text.Replace("VERSION='2.4.0'", "VERSION='2.4.1'")
[System.IO.File]::WriteAllText($maintenance,$text,[System.Text.UTF8Encoding]::new($false))
# GitHub Releases utilizza redirect HTTPS verso domini CDN GitHub.
$downloader = Join-Path $Dest "src\downloader.py"
$text = Get-Content $downloader -Raw
$original = "if r.geturl()!=url:raise ValueError('Redirect non consentito')"
$replacement = "host=urlsplit(r.geturl()).hostname or ''; scheme=urlsplit(r.geturl()).scheme; " +
               "if scheme!='https' or not (host=='github.com' or host.endswith('.githubusercontent.com')):raise ValueError('Redirect fuori da GitHub')"
# Usa due istruzioni Python separate (evita un if compound dopo punto e virgola).
$replacement = "host=urlsplit(r.geturl()).hostname or ''" + "`n" +
               "                scheme=urlsplit(r.geturl()).scheme" + "`n" +
               "                if scheme!='https' or not (host=='github.com' or host.endswith('.githubusercontent.com')):raise ValueError('Redirect fuori da GitHub')"
if (-not $text.Contains($original)) { throw "Versione downloader inattesa" }
$text = $text.Replace("from pathlib import Path", "from pathlib import Path`nfrom urllib.parse import urlsplit")
$text = $text.Replace($original,$replacement)
[System.IO.File]::WriteAllText($downloader,$text,[System.Text.UTF8Encoding]::new($false))
# Adegua i test della V2.4 alla nuova configurazione V2.4.1.
$testFile = Join-Path $Dest "tests\\test_maintenance.py"
$testContent = Get-Content $testFile -Raw
if (-not $testContent.Contains("self.assertEqual(VERSION,'2.4.0')")) { throw "Test versione inatteso: controllo manuale necessario" }
$testContent = $testContent.Replace("self.assertEqual(VERSION,'2.4.0')", "self.assertEqual(VERSION,'2.4.1')")
$oldTest = "x=check_updates();self.assertFalse(x['configured'])"
$newTest = "from unittest.mock import patch" + "`n" +
           "        with patch('maintenance.get_config', return_value={}):" + "`n" +
           "            x=check_updates()" + "`n" +
           "        self.assertFalse(x['configured'])"
if (-not $testContent.Contains($oldTest)) { throw "Test manifest inatteso: controllo manuale necessario" }
$testContent = $testContent.Replace($oldTest, $newTest)
[System.IO.File]::WriteAllText($testFile,$testContent,[System.Text.UTF8Encoding]::new($false))
$updates = Join-Path $Dest "updates.json"
[System.IO.File]::WriteAllText($updates, '{ "manifest_url": "https://raw.githubusercontent.com/manuQ001/NEXUS-AI-Trading/main/latest.json" }' + "`n", [System.Text.UTF8Encoding]::new($false))
Push-Location $Dest
try {
    py -m unittest discover -s tests -p "test_*.py"
    if ($LASTEXITCODE -ne 0) { throw "Test falliti: nessun file inviato a GitHub" }
    git add -- src tests updater.py migrate.py updates.json AVVIA_WINDOWS.ps1
    if ($LASTEXITCODE -ne 0) { throw "git add non riuscito" }
    git commit -m "feat: publish NEXUS 2.4.1 initial paper trading sources"
    if ($LASTEXITCODE -ne 0) { throw "Commit Git fallito. Verifica git config user.name/user.email." }
    git push origin main
    if ($LASTEXITCODE -ne 0) { throw "Push non riuscito. Nessuna release pubblicata." }
    git tag v2.4.1
    git push origin v2.4.1
    if ($LASTEXITCODE -ne 0) { throw "Invio del tag non riuscito" }
    Write-Host "Sorgenti pubblicati. Controlla la scheda Actions e Releases del repository GitHub."
} finally { Pop-Location }
