[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$Host,

    [Parameter(Mandatory = $true)]
    [string]$KeyPath,

    [string]$User = "ubuntu",
    [string]$WorkRoot = "/lambda/nfs/spinelab",
    [string]$RepoDir = "/lambda/nfs/spinelab/spinelab_0.2",
    [string]$SessionName = "verse20-postfold"
)

function Quote-ForBash {
    param([Parameter(Mandatory = $true)][string]$Value)
    return "'" + $Value.Replace("'", "'\"'\"'") + "'"
}

$gateSummaryJson = "$WorkRoot/nnunet/results/Dataset321_VERSE20Vertebrae/nnUNetTrainer__nnUNetResEncL_24G__3d_fullres/fold_0/post_fold/fold_0_gate_summary.json"
$gateSummaryMarkdown = "$WorkRoot/nnunet/results/Dataset321_VERSE20Vertebrae/nnUNetTrainer__nnUNetResEncL_24G__3d_fullres/fold_0/post_fold/fold_0_gate_summary.md"

$repoDirQuoted = Quote-ForBash $RepoDir
$sessionQuoted = Quote-ForBash $SessionName
$gateSummaryJsonQuoted = Quote-ForBash $gateSummaryJson
$gateSummaryMarkdownQuoted = Quote-ForBash $gateSummaryMarkdown

$remoteCommand = @"
set -euo pipefail
cd $repoDirQuoted
if tmux has-session -t $sessionQuoted 2>/dev/null; then
  echo "tmux session $SessionName already exists" >&2
  exit 1
fi
tmux new-session -d -s $sessionQuoted "cd $repoDirQuoted && bash tools/nnunet_verse20_post_fold.sh"
echo "Started tmux session: $SessionName"
echo "Gate summary JSON: $gateSummaryJson"
echo "Gate summary Markdown: $gateSummaryMarkdown"
echo "Fold 1 tmux session: verse20-fold1"
"@

ssh -i $KeyPath "$User@$Host" $remoteCommand
