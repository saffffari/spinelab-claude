from __future__ import annotations

import ctypes
import os
import subprocess
import threading
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

SubprocessArg = str | bytes | os.PathLike[str] | os.PathLike[bytes]


@dataclass(slots=True)
class _TrackedSegmentationProcess:
    process: subprocess.Popen[str]
    label: str
    job_handle: int | None = None


_ACTIVE_SEGMENTATION_PROCESSES: dict[int, _TrackedSegmentationProcess] = {}
_ACTIVE_SEGMENTATION_PROCESSES_LOCK = threading.Lock()

_IS_WINDOWS = os.name == "nt"
_JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x00002000
_JOB_OBJECT_EXTENDED_LIMIT_INFORMATION_CLASS = 9
_PROCESS_SET_QUOTA = 0x0100
_PROCESS_TERMINATE = 0x0001
_PROCESS_QUERY_INFORMATION = 0x0400


if _IS_WINDOWS:
    class _IO_COUNTERS(ctypes.Structure):
        _fields_ = [
            ("ReadOperationCount", ctypes.c_ulonglong),
            ("WriteOperationCount", ctypes.c_ulonglong),
            ("OtherOperationCount", ctypes.c_ulonglong),
            ("ReadTransferCount", ctypes.c_ulonglong),
            ("WriteTransferCount", ctypes.c_ulonglong),
            ("OtherTransferCount", ctypes.c_ulonglong),
        ]


    class _JOBOBJECT_BASIC_LIMIT_INFORMATION(ctypes.Structure):
        _fields_ = [
            ("PerProcessUserTimeLimit", ctypes.c_longlong),
            ("PerJobUserTimeLimit", ctypes.c_longlong),
            ("LimitFlags", ctypes.c_uint32),
            ("MinimumWorkingSetSize", ctypes.c_size_t),
            ("MaximumWorkingSetSize", ctypes.c_size_t),
            ("ActiveProcessLimit", ctypes.c_uint32),
            ("Affinity", ctypes.c_size_t),
            ("PriorityClass", ctypes.c_uint32),
            ("SchedulingClass", ctypes.c_uint32),
        ]


    class _JOBOBJECT_EXTENDED_LIMIT_INFORMATION(ctypes.Structure):
        _fields_ = [
            ("BasicLimitInformation", _JOBOBJECT_BASIC_LIMIT_INFORMATION),
            ("IoInfo", _IO_COUNTERS),
            ("ProcessMemoryLimit", ctypes.c_size_t),
            ("JobMemoryLimit", ctypes.c_size_t),
            ("PeakProcessMemoryUsed", ctypes.c_size_t),
            ("PeakJobMemoryUsed", ctypes.c_size_t),
        ]


def run_tracked_segmentation_subprocess(
    args: Sequence[SubprocessArg],
    *,
    capture_output: bool = False,
    stdout: Any | None = None,
    stderr: Any | None = None,
    env: Mapping[str, str] | None = None,
    check: bool = False,
    text: bool = True,
    label: str = "segmentation-backend",
) -> subprocess.CompletedProcess[str]:
    if capture_output and (stdout is not None or stderr is not None):
        raise ValueError("capture_output cannot be used with stdout or stderr overrides")
    if not text:
        raise ValueError("Tracked segmentation subprocesses must use text mode.")

    resolved_stdout = subprocess.PIPE if capture_output else stdout
    resolved_stderr = subprocess.PIPE if capture_output else stderr
    process = subprocess.Popen(
        args,
        stdout=resolved_stdout,
        stderr=resolved_stderr,
        text=text,
        env=dict(env) if env is not None else None,
    )
    tracked = _register_tracked_process(process, label=label)
    try:
        stdout_data, stderr_data = process.communicate()
    except BaseException:
        _terminate_tracked_process(tracked, timeout_seconds=2.0)
        raise
    finally:
        _unregister_tracked_process(process.pid)

    completed = subprocess.CompletedProcess(args, process.returncode, stdout_data, stderr_data)
    if check and completed.returncode != 0:
        raise subprocess.CalledProcessError(
            completed.returncode,
            completed.args,
            output=completed.stdout,
            stderr=completed.stderr,
        )
    return completed


def terminate_tracked_segmentation_processes(*, timeout_seconds: float = 5.0) -> None:
    with _ACTIVE_SEGMENTATION_PROCESSES_LOCK:
        active = tuple(_ACTIVE_SEGMENTATION_PROCESSES.values())
    for tracked in active:
        _terminate_tracked_process(tracked, timeout_seconds=timeout_seconds)


def tracked_segmentation_process_pids() -> tuple[int, ...]:
    with _ACTIVE_SEGMENTATION_PROCESSES_LOCK:
        return tuple(sorted(_ACTIVE_SEGMENTATION_PROCESSES))


def _register_tracked_process(
    process: subprocess.Popen[str],
    *,
    label: str,
) -> _TrackedSegmentationProcess:
    tracked = _TrackedSegmentationProcess(
        process=process,
        label=label,
        job_handle=_assign_process_to_kill_on_close_job(process.pid),
    )
    with _ACTIVE_SEGMENTATION_PROCESSES_LOCK:
        _ACTIVE_SEGMENTATION_PROCESSES[process.pid] = tracked
    return tracked


def _unregister_tracked_process(pid: int) -> None:
    tracked: _TrackedSegmentationProcess | None
    with _ACTIVE_SEGMENTATION_PROCESSES_LOCK:
        tracked = _ACTIVE_SEGMENTATION_PROCESSES.pop(pid, None)
    if tracked is None:
        return
    _close_job_handle(tracked.job_handle)


def _terminate_tracked_process(
    tracked: _TrackedSegmentationProcess,
    *,
    timeout_seconds: float,
) -> None:
    process = tracked.process
    if process.poll() is not None:
        _unregister_tracked_process(process.pid)
        return

    if tracked.job_handle is not None:
        _close_job_handle(tracked.job_handle)
        tracked.job_handle = None
    else:
        _kill_process_tree_fallback(process.pid)

    try:
        process.wait(timeout=timeout_seconds)
    except subprocess.TimeoutExpired:
        _kill_process_tree_fallback(process.pid)
        try:
            process.wait(timeout=1.0)
        except subprocess.TimeoutExpired:
            pass
    finally:
        _unregister_tracked_process(process.pid)


def _kill_process_tree_fallback(pid: int) -> None:
    if _IS_WINDOWS:
        subprocess.run(
            ["taskkill", "/PID", str(pid), "/T", "/F"],
            capture_output=True,
            text=True,
            check=False,
        )
        return
    try:
        os.kill(pid, 15)
    except OSError:
        return


def _assign_process_to_kill_on_close_job(pid: int) -> int | None:
    if not _IS_WINDOWS:
        return None
    try:
        kernel32 = ctypes.windll.kernel32
    except AttributeError:
        return None
    job_handle = kernel32.CreateJobObjectW(None, None)
    if not job_handle:
        return None
    assigned = False
    try:
        info = _JOBOBJECT_EXTENDED_LIMIT_INFORMATION()
        info.BasicLimitInformation.LimitFlags = _JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        if not kernel32.SetInformationJobObject(
            job_handle,
            _JOB_OBJECT_EXTENDED_LIMIT_INFORMATION_CLASS,
            ctypes.byref(info),
            ctypes.sizeof(info),
        ):
            return None
        process_handle = kernel32.OpenProcess(
            _PROCESS_SET_QUOTA | _PROCESS_TERMINATE | _PROCESS_QUERY_INFORMATION,
            False,
            pid,
        )
        if not process_handle:
            return None
        try:
            if not kernel32.AssignProcessToJobObject(job_handle, process_handle):
                return None
        finally:
            kernel32.CloseHandle(process_handle)
        assigned = True
        return int(job_handle)
    except Exception:
        return None
    finally:
        if not assigned:
            _close_job_handle(job_handle)


def _close_job_handle(job_handle: int | None) -> None:
    if not _IS_WINDOWS or not job_handle:
        return
    try:
        ctypes.windll.kernel32.CloseHandle(job_handle)
    except Exception:
        return
