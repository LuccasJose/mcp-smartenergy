#requires -Version 5.1
<#
.SYNOPSIS
Configura o Graphify no clone atual ou atualiza o mapa local, sem APIs de LLM.
.PARAMETER Atualizar
Atualiza o mapa e o HTML sem reinstalar integracoes do editor e do Git.
#>
[CmdletBinding()]
param([switch]$Atualizar)

$ErrorActionPreference = 'Stop'
$requiredVersion = '0.9.55'
$projectRoot = Split-Path -Parent $PSScriptRoot

Push-Location $projectRoot
try {
    $command = Get-Command graphify -ErrorAction SilentlyContinue
    if (-not $command) {
        # uv pode estar no PATH mesmo quando seu diretorio de ferramentas nao esta.
        $uv = Get-Command uv -ErrorAction SilentlyContinue
        if ($uv) {
            $binDir = & $uv.Source tool dir --bin
            if ($LASTEXITCODE -eq 0) {
                $candidate = Join-Path ($binDir.Trim()) 'graphify.exe'
                if (Test-Path $candidate) {
                    $command = Get-Command $candidate
                }
            }
        }
    }
    if (-not $command) {
        throw "Instale o Graphify isolado: uv tool install graphifyy==$requiredVersion. Depois execute este script novamente."
    }
    $graphifyExe = $command.Source
    $version = & $graphifyExe --version
    if ($LASTEXITCODE -ne 0 -or ($version -join ' ').Trim() -ne "graphify $requiredVersion") {
        throw "Versao esperada: $requiredVersion; encontrada: $version. Consulte docs/desenvolvimento-ia.md antes de atualizar."
    }

    function Invoke-GraphifyCommand {
        param([string[]]$Arguments)
        & $graphifyExe @Arguments
        if ($LASTEXITCODE -ne 0) {
            throw "Graphify falhou ($LASTEXITCODE): $($Arguments -join ' ')"
        }
    }

    if (-not (Test-Path '.graphifyignore')) {
        throw 'A politica .graphifyignore esta ausente; interrompendo para nao ampliar o escopo.'
    }
    if (-not $Atualizar) {
        Invoke-GraphifyCommand -Arguments @('vscode', 'install')
        Invoke-GraphifyCommand -Arguments @('hook', 'install')
    }

    if (Test-Path 'graphify-out/graph.json') {
        Invoke-GraphifyCommand -Arguments @('update', '.')
    }
    else {
        Invoke-GraphifyCommand -Arguments @('extract', '.', '--code-only')
    }
    if (-not (Test-Path 'graphify-out/graph.json')) {
        throw 'A extracao nao produziu graph.json. Consulte a saida antes de continuar.'
    }
    $graph = Get-Content 'graphify-out/graph.json' -Raw -Encoding UTF8 | ConvertFrom-Json
    $nodeCount = @($graph.nodes).Count
    if ($nodeCount -eq 0) {
        throw 'Grafo vazio; nao ha mapa utilizavel.'
    }
    if ($nodeCount -gt 5000) {
        Write-Warning "Grafo com $nodeCount nos: o HTML sera agregado por comunidades."
    }
    Invoke-GraphifyCommand -Arguments @('export', 'html')
    Invoke-GraphifyCommand -Arguments @('hook', 'status')
    Write-Host "Pronto: $nodeCount nos. Nenhum commit ou push foi realizado."
}
finally {
    Pop-Location
}