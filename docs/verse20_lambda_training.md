# VERSe20 nnU-Net Training On Lambda

This is the shortest clean path to a first SpineLab segmentation baseline.

Goal:

- train a custom vertebra segmentation model on `VERSe2020`
- keep the evaluation logic clean
- use Lambda only for the GPU-heavy work
- avoid inventing a second parallel workflow outside the repo

## What We Already Have

- `VERSe2020` subject-based data downloaded locally at `E:\data\verse_data`
- conversion script:
  - [tools/prepare_verse20_nnunet.py](/D:/claude/spinelab/tools/prepare_verse20_nnunet.py)
- Lambda training bootstrap:
  - [tools/nnunet_verse20_lambda_train.sh](/D:/claude/spinelab/tools/nnunet_verse20_lambda_train.sh)
- dedicated training environment definitions:
  - [envs/nnunet_verse20.yml](/D:/claude/spinelab/envs/nnunet_verse20.yml)
  - [envs/nnunet_verse20_requirements.txt](/D:/claude/spinelab/envs/nnunet_verse20_requirements.txt)

## The Mental Model

There are four distinct phases:

1. Prepare the dataset in `nnU-Net` layout
2. Extract the fingerprint and plan the experiment
3. Preprocess the data
4. Train a fold

`nnU-Net` expects three environment variables:

- `nnUNet_raw`
- `nnUNet_preprocessed`
- `nnUNet_results`

Think of them as:

- `raw`: linked/copied dataset in nnU-Net folder structure
- `preprocessed`: cached resampling and planning outputs
- `results`: checkpoints, logs, and validation outputs

## Our Starting Policy

For the first clean baseline:

- train only on `01_training`
- keep `02_validation` as an untouched official holdout
- keep `03_test` untouched as a later holdout

Do not merge validation into training until the pipeline itself is stable.
If `03_test` is not uploaded to Lambda for the first run, the prep script now treats it as optional and continues with training plus validation only.

## Why Lambda Needs A Filesystem

Your instance is the GPU computer.

The attached filesystem is the durable disk.

If you put the dataset, preprocessed data, or checkpoints only on the instance root, you risk losing them when the instance is terminated. Put the repo copy, raw data, `nnUNet_preprocessed`, and `nnUNet_results` under the attached filesystem path.

Use a structure like:

```text
/lambda/nfs/spinelab/
  data/
    verse_data/
  nnunet/
    raw/
    preprocessed/
    results/
  spinelab_0.2/
  venvs/
```

## Step 1 — Launch The Lambda Instance

In the Lambda console:

- create or reuse an SSH key
- create or attach a persistent filesystem
- launch a single-GPU instance
- choose a GPU with enough VRAM for a residual-encoder 3D run

Practical guidance:

- start with a single GPU
- treat `24 GB` VRAM as the minimum target
- `48 GB` is safer if you want more headroom for the residual-encoder plan and preprocessing

Do not optimize for the cheapest instance first. Optimize for getting one stable baseline run.

## Step 2 — Connect And Create The Workspace

SSH in, then create the working layout on the attached filesystem:

```bash
mkdir -p /lambda/nfs/spinelab/{data,nnunet/{raw,preprocessed,results},venvs}
cd /lambda/nfs/spinelab
git clone <YOUR-REPO-URL> spinelab_0.2
```

If you are not cloning from GitHub, copy the repo there manually.

## Step 3 — Upload The VERSe Data

Copy `E:\data\verse_data` to:

```text
/lambda/nfs/spinelab/data/verse_data
```

From Windows PowerShell, `scp` is the simplest starting point:

```powershell
scp -r E:\data\verse_data ubuntu@<lambda-host>:/lambda/nfs/spinelab/data/
```

If you already have `rsync` available through WSL or Git Bash, use that instead for resumable transfers.

## Step 4 — Run The Bootstrap Script

From the Lambda shell:

```bash
cd /lambda/nfs/spinelab/spinelab_0.2
tmux new -s verse20
bash tools/nnunet_verse20_lambda_train.sh
```

The bootstrap script resolves `REPO_DIR` from its own location by default, so it works from the mounted filesystem checkout without needing an extra environment override.

That script will:

- create a virtual environment using the system Python
- install the training requirements
- export `nnUNet_raw`, `nnUNet_preprocessed`, and `nnUNet_results`
- convert `VERSe2020` into `nnU-Net` dataset format
- skip exporting the official validation/test holdout files during the first training run so the model pipeline can start sooner
- verify dataset integrity
- plan a residual-encoder experiment with a `24 GB` memory target
- preprocess `3d_fullres`
- start fold `0` training on CUDA

The bootstrap script is intentionally for the first run only. Once raw data, plans, and preprocessing exist, later folds should use the fold-only launcher instead of rerunning the full bootstrap.

Reusable Lambda scripts now live under:

- [tools/nnunet_verse20_lambda_common.sh](/D:/claude/spinelab/tools/nnunet_verse20_lambda_common.sh)
- [tools/nnunet_verse20_lambda_train_fold.sh](/D:/claude/spinelab/tools/nnunet_verse20_lambda_train_fold.sh)
- [tools/nnunet_verse20_post_fold.sh](/D:/claude/spinelab/tools/nnunet_verse20_post_fold.sh)
- [tools/nnunet_verse20_post_fold_gate.py](/D:/claude/spinelab/tools/nnunet_verse20_post_fold_gate.py)
- [tools/run_lambda_post_fold.ps1](/D:/claude/spinelab/tools/run_lambda_post_fold.ps1)

## Step 5 — Understand What The Prep Script Creates

The conversion script creates:

```text
<nnUNet_raw>/
  Dataset321_VERSE20Vertebrae/
    imagesTr/
    labelsTr/
    dataset.json
  eval/
    official_validation/
      images/
      labels/
      centroids/
      previews/
    official_test/
      images/
      labels/
      centroids/
      previews/
  verse20_nnunet_manifest.json
```

Important:

- `imagesTr` and `labelsTr` contain only the official training split by default
- validation and test are exported separately for later evaluation
- VERSe occasionally includes native label `28` for an additional `T13`; the prep script remaps native VERSe labels into a consecutive nnU-Net training label space and records the native-to-training mapping in the manifest
- when you need to rebuild the holdout export later without touching the training dataset, run the prep tool with `--eval-only`

Example:

```bash
source /lambda/nfs/spinelab/venvs/verse20-nnunet/bin/activate
export nnUNet_raw=/lambda/nfs/spinelab/nnunet/raw
python /lambda/nfs/spinelab/spinelab_0.2/tools/prepare_verse20_nnunet.py \
  --verse-root /lambda/nfs/spinelab/data/verse_data \
  --output-root /lambda/nfs/spinelab/nnunet/raw \
  --dataset-id 321 \
  --dataset-name VERSE20Vertebrae \
  --link-mode symlink \
  --eval-only
```

## Step 6 — What The Core nnU-Net Commands Mean

In the current `nnunetv2==2.6.4` package, the residual-encoder planner exposed by the CLI is `ResEncUNetPlanner`.

For this project, we are using that planner with a higher GPU memory target and a custom plans name (`nnUNetResEncL_24G`) as our operational `ResEnc-L` baseline.

These are the commands the bootstrap script runs:

```bash
nnUNetv2_extract_fingerprint -d 321 -np 8 --verify_dataset_integrity
nnUNetv2_plan_experiment -d 321 -pl ResEncUNetPlanner -gpu_memory_target 24 -overwrite_plans_name nnUNetResEncL_24G
nnUNetv2_preprocess -d 321 -plans_name nnUNetResEncL_24G -c 3d_fullres -np 4
nnUNetv2_train 321 3d_fullres 0 -tr nnUNetTrainer -p nnUNetResEncL_24G -device cuda
```

Interpretation:

- `extract_fingerprint`: inspect the dataset and validate structure
- `plan_experiment`: choose patch size, batch size, and network planning
- `preprocess`: resample and cache the training data
- `train`: actually optimize the model

## Step 7 — What To Watch While It Runs

Monitor:

- GPU memory usage
- disk growth under `nnUNet_preprocessed` and `nnUNet_results`
- whether training survives the first epoch without OOM
- validation loss trend

Useful commands:

```bash
nvidia-smi
df -h
tail -f /lambda/nfs/spinelab/nnunet/results/*/*/*/training_log*.txt
```

## Step 8 — Launch Later Folds Without Rebootstrapping

After fold 0 finishes and the plans plus preprocessing cache already exist, launch later folds with the fold-only script:

```bash
cd /lambda/nfs/spinelab/spinelab_0.2
tmux new -s verse20-fold1
FOLD=1 bash tools/nnunet_verse20_lambda_train_fold.sh
```

That path:

- reuses the existing virtual environment
- reuses the existing `nnUNet_raw`
- reuses the existing `nnUNet_preprocessed`
- writes only to the requested fold directory under `nnUNet_results`

It refuses to reuse a non-empty fold directory, which protects you from accidentally overwriting an existing run.

## Step 9 — One-Click Post-Fold Automation

Once fold 0 is complete, the post-fold automation does three things:

1. run `nnUNetv2_train ... --val --val_best` for fold 0
2. write a quick gate summary
3. start fold 1 automatically in detached `tmux` if the gate passes

The quick gate policy is:

- require `checkpoint_final.pth`
- require `checkpoint_best.pth`
- require `validation/summary.json`
- fail on fatal log markers such as `Traceback`, `RuntimeError`, `out of memory`, or `nan`
- fail if `foreground_mean.Dice < 0.70`

The current single-GPU policy deliberately defers official `02_validation` holdout inference. Fold 0 internal validation is the gate. Official holdout evaluation is a later separate step so it does not contend with fold 1 on the same H100.

Remote tmux sessions used by this workflow:

- `verse20`: initial fold 0 bootstrap
- `verse20-postfold`: detached automation session started from Windows
- `verse20-fold1`: fold 1 training if the gate passes

From Windows PowerShell:

```powershell
powershell -File tools/run_lambda_post_fold.ps1 -Host 192.222.55.77 -KeyPath "$HOME\.ssh\lambda_ed25519"
```

That command SSHes into Lambda, starts the post-fold script in detached `tmux`, and prints the summary paths to watch.

If you want to run the remote post-fold step manually on Lambda instead:

```bash
cd /lambda/nfs/spinelab/spinelab_0.2
tmux new -s verse20-postfold
bash tools/nnunet_verse20_post_fold.sh
```

The gate summaries are written to:

```text
/lambda/nfs/spinelab/nnunet/results/Dataset321_VERSE20Vertebrae/nnUNetTrainer__nnUNetResEncL_24G__3d_fullres/fold_0/post_fold/
  fold_0_gate_summary.json
  fold_0_gate_summary.md
```

## Step 10 — What We Should Do First

Do this in order:

1. Prove the conversion script runs end to end
2. Run one fold on the official training split
3. Evaluate on the untouched official validation holdout
4. Only then decide whether to:
   - tune the memory target
   - merge validation into training
   - add `VERSe2019`
   - train multiple folds

## Why We Are Not Pulling In VERSe2019 Yet

`VERSe2020` is enough to start the pipeline.

`VERSe2019` is useful later if we want more cases, but it adds more bookkeeping:

- overlap checks
- patient-level deduplication
- split redesign

That is not where we should spend the first day.

## Sources

- Lambda public cloud getting started: [docs.lambda.ai/public-cloud/on-demand/getting-started](https://docs.lambda.ai/public-cloud/on-demand/getting-started/)
- Lambda guidance on virtual environments: [docs.lambda.ai/education/programming/virtual-environments-containers](https://docs.lambda.ai/education/programming/virtual-environments-containers/)
