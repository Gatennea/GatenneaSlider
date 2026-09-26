# Gatennea Slider Puzzle - Zip helper (invoked by package_zip.bat)
# Reads $env:PACK_SOURCE and $env:PACK_ZIPNAME from the caller batch file.
# Exclusions are derived from .gitignore; .git itself is kept.

$ErrorActionPreference = 'Stop'

$Source  = [string]$env:PACK_SOURCE
$ZipName = [string]$env:PACK_ZIPNAME
if (-not $Source -or -not $ZipName) {
    Write-Host '[ERROR] PACK_SOURCE / PACK_ZIPNAME env vars not set.'
    exit 1
}

$Source = $Source.TrimEnd('\', '/')
$dest   = Join-Path $Source $ZipName

# ── Parse .gitignore ────────────────────────────────────────────────────────
# Returns an array of rules: @{ Negate:$bool; Pattern:$str; DirOnly:$bool }
function Get-GitignoreRules {
    param([string]$Path)
    $rules = @()
    if (-not (Test-Path $Path)) { return $rules }
    Get-Content $Path -Encoding UTF8 | ForEach-Object {
        $line = $_.Trim()
        if (-not $line -or $line.StartsWith('#')) { return }
        $negate = $false
        if ($line.StartsWith('!')) { $negate = $true; $line = $line.Substring(1) }
        $dirOnly = $line.EndsWith('/')
        if ($dirOnly) { $line = $line.TrimEnd('/') }
        # Normalize: leading / makes it relative to repo root (no effect when we strip prefix anyway)
        if ($line.StartsWith('/')) { $line = $line.Substring(1) }
        # Normalize slashes for PS glob matching
        $line = $line -replace '/', '\'
        $rules += @{ Negate = $negate; Pattern = $line; DirOnly = $dirOnly }
    }
    return $rules
}

function Test-GitignoreMatch {
    param([string]$RelPath, [hashtable[]]$Rules)
    # Normalize to backslashes for PS glob matching
    $normPath = $RelPath -replace '/', '\'
    foreach ($rule in $Rules) {
        $pat = $rule.Pattern
        $matched = $false

        if ($rule.DirOnly) {
            # Directory-only pattern: match exact name or prefix (subtree)
            if ($normPath -eq $pat -or $normPath -like "$pat*") {
                $matched = $true
            }
        } else {
            # Convert gitignore glob to PowerShell wildcard pattern.
            # gitignore: foo/**/bar  →  PS:   foo\*\*\bar
            # gitignore: *.pyc       →  PS:   *.pyc
            # gitignore: dir/        →  handled by DirOnly above
            # gitignore: /a/b        →  PS:   a\b     (leading / stripped already)
            $psPat = $pat -replace '/\*\*/', '\*\*\*'
            $psPat = $psPat -replace '/\*',    '\**'
            if ($psPat -like '*\*') {
                # Glob pattern — test basename against pattern, then try full path
                $base = Split-Path $normPath -Leaf
                if ($base -like $psPat -or $normPath -like "*$psPat" -or $normPath -like $psPat) {
                    $matched = $true
                }
            } else {
                # Literal path — exact match or prefix (for directories)
                if ($normPath -eq $psPat)                      { $matched = $true }
                elseif ($normPath.StartsWith("$psPat\"))       { $matched = $true }
            }
        }

        if ($matched) { return -not $rule.Negate }
    }
    return $false   # not listed → include
}

$gitignorePath = Join-Path $Source '.gitignore'
$rules         = Get-GitignoreRules $gitignorePath
Write-Host ('[INFO] Loaded ' + $rules.Count + ' .gitignore rules from ' + $gitignorePath)

# ── Stage directory ─────────────────────────────────────────────────────────
$temp     = Join-Path $env:TEMP ('Gatenneaslider_pack_' + [guid]::NewGuid().ToString('n'))
$stageDir = Join-Path $temp (Split-Path $Source -Leaf)
New-Item -ItemType Directory -Path $stageDir -Force | Out-Null
Write-Host ('[INFO] Staging directory: ' + $stageDir)

# Copy helper: recurses $src under $srcRoot, writes to $dstRoot, applies gitignore
function Copy-StageItem {
    param([string]$SrcRoot, [string]$DstRoot, [string]$RelPath, [hashtable[]]$Rules)
    $srcItem = Join-Path $SrcRoot $RelPath
    $dstItem = Join-Path $DstRoot  $RelPath
    if ((Test-Path $srcItem -PathType Leaf)) {
        $parent = Split-Path $dstItem -Parent
        if (-not (Test-Path $parent)) { New-Item -ItemType Directory -Path $parent -Force | Out-Null }
        Copy-Item -LiteralPath $srcItem -Destination $dstItem -Force
        Write-Host ('  copy file: ' + $relPath)
    } elseif ((Test-Path $srcItem -PathType Container)) {
        # If this container is excluded by a DirOnly rule, do not recurse into it
        $isDirOnlyExcluded = $false
        foreach ($rule in $Rules) {
            if ($rule.DirOnly -and ($RelPath -eq $rule.Pattern -or $RelPath -like ($rule.Pattern + '*'))) {
                $isDirOnlyExcluded = $true
                break
            }
        }
        if ($isDirOnlyExcluded) {
            Write-Host ('  skip dir : ' + $relPath)
            return
        }
        $parent = Split-Path $dstItem -Parent
        if (-not (Test-Path $parent)) { New-Item -ItemType Directory -Path $parent -Force | Out-Null }
        Get-ChildItem -LiteralPath $srcItem -Force | ForEach-Object {
            $childRel = $RelPath + '/' + $_.Name
            if (Test-GitignoreMatch $childRel $Rules) {
                Write-Host ('  skip     : ' + $childRel)
            } else {
                Copy-StageItem -SrcRoot $SrcRoot -DstRoot $DstRoot -RelPath $childRel -Rules $Rules
            }
        }
    }
}

# Top-level items
$topItems = Get-ChildItem -LiteralPath $Source -Force
foreach ($item in $topItems) {
    $rel = $item.Name
    if (Test-GitignoreMatch $rel $rules) {
        Write-Host ('  skip top : ' + $rel)
    } else {
        Copy-StageItem -SrcRoot $Source -DstRoot $stageDir -RelPath $rel -Rules $rules
    }
}

# ── Zip ──────────────────────────────────────────────────────────────────────
Add-Type -AssemblyName System.IO.Compression.FileSystem
if (Test-Path -LiteralPath $dest) { Remove-Item -LiteralPath $dest -Force }
$items = Get-ChildItem -LiteralPath $stageDir
if (-not $items) {
    Write-Host '[ERROR] Nothing to zip (staging dir empty).'
    exit 1
}
[System.IO.Compression.ZipFile]::CreateFromDirectory($stageDir, $dest)

$sizeKB = [math]::Round((Get-Item -LiteralPath $dest).Length / 1KB, 2)
Write-Host ('[OK] Zip written: ' + $dest + ' (' + $sizeKB + ' KB)')

# Cleanup staging
Remove-Item -LiteralPath $temp -Recurse -Force
