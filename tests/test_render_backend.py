import sys
from pathlib import Path

from spinelab.services import classify_render_backend


def test_classify_render_backend_reports_hardware_for_native_driver_modules() -> None:
    probe = classify_render_backend(
        backend_class="OpenGL2",
        opengl_vendor="NVIDIA Corporation",
        opengl_renderer="NVIDIA GeForce RTX 4090/PCIe/SSE2",
        opengl_version="4.5.0 NVIDIA 591.86",
        render_window_class="vtkWin32OpenGLRenderWindow",
        loaded_module_paths=(
            r"C:\Windows\System32\OPENGL32.dll",
            r"C:\Windows\System32\nvoglv64.dll",
        ),
    )

    assert probe.classification == "hardware"
    assert probe.hardware_ok is True
    assert probe.failure_reason is None


def test_classify_render_backend_rejects_software_modules() -> None:
    env_bin = Path(sys.prefix) / "Library" / "bin"
    probe = classify_render_backend(
        backend_class="OpenGL2",
        opengl_vendor="Mesa/X.org",
        opengl_renderer="llvmpipe",
        opengl_version="4.5",
        render_window_class="vtkWin32OpenGLRenderWindow",
        loaded_module_paths=(
            str(env_bin / "OPENGL32.dll"),
            str(env_bin / "libgallium_wgl.dll"),
        ),
    )

    assert probe.classification == "software"
    assert probe.hardware_ok is False
    assert probe.failure_reason is not None
    assert "software OpenGL module" in probe.failure_reason


def test_classify_render_backend_rejects_env_local_opengl32() -> None:
    env_bin = Path(sys.prefix) / "Library" / "bin"
    probe = classify_render_backend(
        backend_class="OpenGL2",
        opengl_vendor="NVIDIA Corporation",
        opengl_renderer="NVIDIA GeForce RTX 4090/PCIe/SSE2",
        opengl_version="4.5.0 NVIDIA 591.86",
        render_window_class="vtkWin32OpenGLRenderWindow",
        loaded_module_paths=(
            str(env_bin / "OPENGL32.dll"),
            r"C:\Windows\System32\nvoglv64.dll",
        ),
    )

    assert probe.classification == "software"
    assert probe.hardware_ok is False
    assert probe.failure_reason == (
        "Resolved OPENGL32.dll from the Conda environment instead of the system OpenGL driver path."
    )


def test_classify_render_backend_reports_unknown_without_vendor_strings() -> None:
    probe = classify_render_backend(
        backend_class="OpenGL2",
        opengl_vendor="",
        opengl_renderer="",
        opengl_version="",
        render_window_class="vtkWin32OpenGLRenderWindow",
        loaded_module_paths=(),
    )

    assert probe.classification == "unknown"
    assert probe.hardware_ok is False
    assert probe.failure_reason == "VTK did not report a usable OpenGL vendor and renderer."
