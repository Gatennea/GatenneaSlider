# Gatennea Slider Puzzle - Zip helper (invoked by package_zip.bat)
# Reads $env:PACK_SOURCE and $env:PACK_ZIPNAME from the caller batch file.

$ErrorActionPreference = 'Stop'

$Source  = [string]$env:PACK_SOURCE
$ZipName = [string]$env:PACK_ZIPNAME
if (-not $Source -or -not $ZipName) {
    Write-Host '[ERROR] PACK_SOURCE / PACK_ZIPNAME env vars not set.'
    exit 1
}

$excludeDirs    = @('__pycache__', '.venv', 'venv', 'build', 'dist', '.git', '.vscode', '.clinerules')
$excludeFileExt = @('.pyc', '.spec', '.zip')
$excludeFiles   = @('*.pyc', '*.spec', '*.zip')

# Normalize paths (strip trailing backslash)
$Source = $Source.TrimEnd('\', '/')
$dest   = Join-Path $Source $ZipName

# Create a temp staging directory to avoid recursive copy issues & filter easily
$temp     = Join-Path $env:TEMP ('Gatenneaslider_pack_' + [guid]::NewGuid().ToString('n'))
$stageDir = Join-Path $temp (Split-Path $Source -Leaf)
New-Item -ItemType Directory -Path $stageDir -Force | Out-Null
Write-Host ('[INFO] Staging directory: ' + $stageDir)

# Build a list of files/dirs at top level to copy - exclude certain top-level dirs/files
$topItems = Get-ChildItem -LiteralPath $Source
foreach ($item in $topItems) {
    if ($item.PSIsContainer) {
        if ($item.Name -in $excludeDirs) {
            Write-Host ('  skip dir : ' + $item.FullName)
            continue
        }
    } else {
        if ($item.Name -like '*.pyc' -or $item.Name -like '*.spec' -or $item.Name -like '*.zip') {
            Write-Host ('  skip file: ' + $item.FullName)
            continue
        }
    }
    Copy-Item -LiteralPath $item.FullName -Destination $stageDir -Recurse -Force
}

# Now recursively clean the staged copy
foreach ($dname in $excludeDirs) {
    $matches = Get-ChildItem -LiteralPath $stageDir -Recurse -Directory -Filter $dname -ErrorAction SilentlyContinue |
               Sort-Object FullName -Descending
    foreach ($m in $matches) {
        Write-Host ('  remove dir : ' + $m.FullName)
        Remove-Item -LiteralPath $m.FullName -Recurse -Force
    }
}

foreach ($pattern in $excludeFiles) {
    $matches = Get-ChildItem -LiteralPath $stageDir -Recurse -File -Filter $pattern -ErrorAction SilentlyContinue
    foreach ($m in $matches) {
        Write-Host ('  remove file: ' + $m.FullName)
        Remove-Item -LiteralPath $m.FullName -Force
    }
}

# Create zip - use .NET API to avoid Compress-Archive edge cases
Add-Type -AssemblyName System.IO.Compression.FileSystem
if (Test-Path -LiteralPath $dest) { Remove-Item -LiteralPath $dest -Force }
$items = Get-ChildItem -LiteralPath $stageDir
if (-not $items) {
    Write-Host '[ERROR] Nothing to zip (staging dir empty).'
    exit 1
}
$compression = [System.IO.Compression.CompressionLevel]::Optimal
[System.IO.Compression.ZipFile]::CreateFromDirectory($stageDir, $dest)

# Report size
$sizeKB = [math]::Round((Get-Item -LiteralPath $dest).Length / 1KB, 2)
Write-Host ('[OK] Zip written: ' + $dest + ' (' + $sizeKB + ' KB)')

# Cleanup staging
Remove-Item -LiteralPath $temp -Recurse -Force
