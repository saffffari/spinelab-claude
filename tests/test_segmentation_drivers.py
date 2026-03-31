from __future__ import annotations

import subprocess
from pathlib import Path

import spinelab.segmentation.drivers as drivers_module
import spinelab.segmentation.process_control as process_control_module
from spinelab.segmentation import SegmentationDriverError, build_legacy_nnunet_runtime_model


def _write_fake_results_root(tmp_path: Path) -> tuple[Path, Path]:
    results_root = tmp_path / "results"
    trainer_root = (
        results_root
        / "Dataset321_VERSE20Vertebrae"
        / "nnUNetTrainer__nnUNetResEncL_24G__3d_fullres"
    )
    checkpoint_path = trainer_root / "fold_0" / "checkpoint_final.pth"
    checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
    checkpoint_path.write_bytes(b"checkpoint")
    return results_root, checkpoint_path


def test_nnunet_driver_builds_expected_command_and_env(tmp_path: Path, monkeypatch) -> None:
    results_root, _checkpoint_path = _write_fake_results_root(tmp_path)
    runtime_model = build_legacy_nnunet_runtime_model(
        results_root=results_root,
        dataset_id=321,
        dataset_name="VERSE20Vertebrae",
        trainer_name="nnUNetTrainer",
        plan_name="nnUNetResEncL_24G",
        configuration="3d_fullres",
        fold="0",
        checkpoint_name="checkpoint_final.pth",
    )
    conda_executable = tmp_path / "conda.bat"
    conda_executable.write_text("@echo off\n", encoding="utf-8")
    input_path = tmp_path / "case-001.nii.gz"
    input_path.write_bytes(b"nifti")
    captured: dict[str, object] = {}

    monkeypatch.setenv("CONDA_EXE", str(conda_executable))

    def _fake_run(command, *, stdout, stderr, text, env, check, label):
        del stderr, text, check
        command_list = [str(item) for item in command]
        captured["command"] = command_list
        captured["env"] = dict(env)
        captured["label"] = label
        prediction_dir = Path(command_list[command_list.index("--output-dir") + 1])
        (prediction_dir / "case-001.nii.gz").write_bytes(b"prediction")
        stdout.write("ok\n")
        stdout.flush()
        return subprocess.CompletedProcess(command_list, 0, stdout="", stderr="")

    monkeypatch.setattr(drivers_module, "run_tracked_segmentation_subprocess", _fake_run)

    driver = drivers_module.NNUNetV2SegmentationDriver(
        preprocessing_workers=4,
        export_workers=5,
    )
    result = driver.predict(
        input_path,
        runtime_model,
        tmp_path / "job",
        device="cuda",
        continue_prediction=True,
        disable_tta=True,
    )

    command = captured["command"]
    assert isinstance(command, list)
    assert command[:6] == [
        str(conda_executable),
        "run",
        "-n",
        "spinelab-nnunet-verse20-win",
        "python",
        str(drivers_module._sidecar_entrypoint_path()),  # pyright: ignore[reportPrivateUsage]
    ]
    assert "--model-dir" in command
    assert "--input-dir" in command
    assert "--output-dir" in command
    assert "--npp" in command and command[command.index("--npp") + 1] == "4"
    assert "--nps" in command and command[command.index("--nps") + 1] == "5"
    assert "--disable_tta" in command
    assert "--continue_prediction" in command
    assert captured["label"] == "nnunet-sidecar-predict"
    assert result.outputs[0].prediction_path.exists() is True
    assert result.outputs[0].diagnostics_path == result.prediction_dir / "case-001.diagnostics.json"
    assert result.log_path is not None and result.log_path.exists() is True
    assert result.stdout == "ok"
    assert captured["env"]["nnUNet_results"] == str(runtime_model.runtime_results_root)
    assert captured["env"]["nnUNet_raw"] == str(runtime_model.runtime_raw_root)
    assert captured["env"]["nnUNet_preprocessed"] == str(
        runtime_model.runtime_preprocessed_root
    )


def test_nnunet_driver_fails_without_conda(tmp_path: Path, monkeypatch) -> None:
    results_root, _checkpoint_path = _write_fake_results_root(tmp_path)
    runtime_model = build_legacy_nnunet_runtime_model(
        results_root=results_root,
        dataset_id=321,
        dataset_name="VERSE20Vertebrae",
        trainer_name="nnUNetTrainer",
        plan_name="nnUNetResEncL_24G",
        configuration="3d_fullres",
        fold="0",
        checkpoint_name="checkpoint_final.pth",
    )
    input_path = tmp_path / "case-001.nii.gz"
    input_path.write_bytes(b"nifti")

    monkeypatch.delenv("CONDA_EXE", raising=False)
    monkeypatch.setattr(drivers_module.shutil, "which", lambda _name: None)

    driver = drivers_module.NNUNetV2SegmentationDriver()
    try:
        driver.predict(input_path, runtime_model, tmp_path / "job", device="cuda")
    except SegmentationDriverError as exc:
        assert "Unable to locate conda" in str(exc)
    else:
        raise AssertionError("Expected SegmentationDriverError when conda is unavailable.")


def test_nnunet_driver_fails_when_checkpoint_is_missing(tmp_path: Path, monkeypatch) -> None:
    results_root, checkpoint_path = _write_fake_results_root(tmp_path)
    runtime_model = build_legacy_nnunet_runtime_model(
        results_root=results_root,
        dataset_id=321,
        dataset_name="VERSE20Vertebrae",
        trainer_name="nnUNetTrainer",
        plan_name="nnUNetResEncL_24G",
        configuration="3d_fullres",
        fold="0",
        checkpoint_name="checkpoint_final.pth",
    )
    checkpoint_path.unlink()
    input_path = tmp_path / "case-001.nii.gz"
    input_path.write_bytes(b"nifti")
    conda_executable = tmp_path / "conda.bat"
    conda_executable.write_text("@echo off\n", encoding="utf-8")
    monkeypatch.setenv("CONDA_EXE", str(conda_executable))

    driver = drivers_module.NNUNetV2SegmentationDriver()
    try:
        driver.predict(input_path, runtime_model, tmp_path / "job", device="cuda")
    except SegmentationDriverError as exc:
        assert "Resolved checkpoint is missing" in str(exc)
    else:
        raise AssertionError("Expected SegmentationDriverError for a missing checkpoint.")



def test_run_tracked_segmentation_subprocess_unregisters_completed_process(
    monkeypatch,
) -> None:
    class FakePopen:
        def __init__(self, command, *, stdout, stderr, text, env) -> None:
            del stdout, stderr, text, env
            self.args = list(command)
            self.pid = 321
            self.returncode = 0

        def communicate(self):
            return ("done", "")

        def poll(self):
            return self.returncode

        def wait(self, timeout=None):
            del timeout
            return self.returncode

    monkeypatch.setattr(process_control_module.subprocess, "Popen", FakePopen)
    monkeypatch.setattr(
        process_control_module,
        "_assign_process_to_kill_on_close_job",
        lambda _pid: None,
    )
    process_control_module.terminate_tracked_segmentation_processes()

    completed = process_control_module.run_tracked_segmentation_subprocess(
        ["python", "-c", "print('ok')"],
        capture_output=True,
        text=True,
        check=False,
        label="test-process",
    )

    assert completed.returncode == 0
    assert completed.stdout == "done"
    assert process_control_module.tracked_segmentation_process_pids() == ()


def test_terminate_tracked_segmentation_processes_closes_job_handle_and_clears_registry(
    monkeypatch,
) -> None:
    class FakePopen:
        def __init__(self) -> None:
            self.pid = 654
            self.returncode = None
            self.wait_calls = 0

        def poll(self):
            return self.returncode

        def wait(self, timeout=None):
            del timeout
            self.wait_calls += 1
            self.returncode = 1
            return self.returncode

    closed_handles: list[int] = []
    killed_pids: list[int] = []
    fake_process = FakePopen()
    tracked = process_control_module._TrackedSegmentationProcess(  # pyright: ignore[reportPrivateUsage]
        process=fake_process,
        label="test-process",
        job_handle=99,
    )
    process_control_module._ACTIVE_SEGMENTATION_PROCESSES.clear()  # pyright: ignore[reportPrivateUsage]
    process_control_module._ACTIVE_SEGMENTATION_PROCESSES[fake_process.pid] = tracked  # pyright: ignore[reportPrivateUsage]
    monkeypatch.setattr(
        process_control_module,
        "_close_job_handle",
        lambda handle: closed_handles.append(handle) if handle is not None else None,
    )
    monkeypatch.setattr(
        process_control_module,
        "_kill_process_tree_fallback",
        lambda pid: killed_pids.append(pid),
    )

    process_control_module.terminate_tracked_segmentation_processes(timeout_seconds=0.01)

    assert closed_handles == [99]
    assert killed_pids == []
    assert fake_process.wait_calls == 1
    assert process_control_module.tracked_segmentation_process_pids() == ()
