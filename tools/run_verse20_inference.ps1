param(
    [ValidateSet("setup", "raw-test-data", "verse03-random")]
    [string]$Action = "raw-test-data",
    [string]$ResultsRoot = "E:\data\spinelab\nnunet\results",
    [string]$OutputRoot = "E:\data\spinelab\raw_test_data\outputs",
    [int]$SampleSize = 3,
    [int]$Seed = 20260326,
    [string]$Device = "auto",
    [string]$Fold = "0",
    [string]$Checkpoint = "checkpoint_final.pth"
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
$EnvName = "spinelab-nnunet-verse20-win"

if ($Action -eq "setup") {
    conda create -n $EnvName -c conda-forge -y python=3.10 pip git
    conda run -n $EnvName python -m pip install -r (Join-Path $RepoRoot "envs\nnunet_verse20_requirements.txt")
    conda run -n $EnvName python -m pip install --force-reinstall --index-url https://download.pytorch.org/whl/cu124 torch==2.5.1 torchvision==0.20.1
    Write-Host "Environment ready: $EnvName"
    exit 0
}

$scriptArgs = @(
    "python",
    (Join-Path $RepoRoot "tools\run_verse20_inference.py"),
    "--output-root", $OutputRoot,
    "--results-root", $ResultsRoot,
    "--fold", $Fold,
    "--checkpoint", $Checkpoint,
    "--device", $Device
)

switch ($Action) {
    "raw-test-data" {
        $scriptArgs += @("--mode", "raw-test-data", "--job-name", "raw_test_data_all")
    }
    "verse03-random" {
        $scriptArgs += @(
            "--mode", "verse03-random",
            "--sample-size", $SampleSize,
            "--seed", $Seed,
            "--job-name", ("verse03_random{0}_{1}" -f $SampleSize, $Seed)
        )
    }
}

conda run -n $EnvName @scriptArgs
