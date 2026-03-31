from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import numpy as np

from spinelab.ai.pointcloud.contracts import StructureContext
from spinelab.ai.pointcloud.geometry import derive_primitives_from_point_cloud
from spinelab.ontology import SURFACE_PATCH_CLASS_INDEX, SurfacePatchId


@dataclass(frozen=True, slots=True)
class StructurePrediction:
    semantic_labels: np.ndarray
    boundary_scores: np.ndarray
    primitives: dict[str, object]
    qc_summary: dict[str, object]
    vertex_groups: dict[str, dict[str, object]]
    confidence: float


class PointCloudLandmarkModel(Protocol):
    provider_name: str

    def predict_structure(
        self,
        *,
        points_xyz: np.ndarray,
        context: StructureContext,
    ) -> StructurePrediction: ...


class HeuristicPointCloudModel:
    provider_name = "heuristic"

    def predict_structure(
        self,
        *,
        points_xyz: np.ndarray,
        context: StructureContext,
    ) -> StructurePrediction:
        points = np.asarray(points_xyz, dtype=float)
        if points.ndim != 2 or points.shape[1] != 3 or len(points) == 0:
            raise ValueError("HeuristicPointCloudModel requires a non-empty (N, 3) point cloud.")

        z_min = float(np.min(points[:, 2]))
        z_max = float(np.max(points[:, 2]))
        y_min = float(np.min(points[:, 1]))
        y_max = float(np.max(points[:, 1]))
        z_span = max(z_max - z_min, 1e-6)
        y_span = max(y_max - y_min, 1e-6)

        semantic_labels = np.full(
            len(points),
            SURFACE_PATCH_CLASS_INDEX[SurfacePatchId.VERTEBRAL_BODY_SURFACE],
            dtype=np.int32,
        )
        superior_mask = points[:, 2] >= (z_max - (0.15 * z_span))
        inferior_mask = points[:, 2] <= (z_min + (0.15 * z_span))
        posterior_mask = points[:, 1] >= (y_max - (0.15 * y_span))
        semantic_labels[posterior_mask] = SURFACE_PATCH_CLASS_INDEX[
            SurfacePatchId.POSTERIOR_BODY_WALL
        ]
        semantic_labels[inferior_mask] = SURFACE_PATCH_CLASS_INDEX[SurfacePatchId.INFERIOR_ENDPLATE]
        semantic_labels[superior_mask] = SURFACE_PATCH_CLASS_INDEX[SurfacePatchId.SUPERIOR_ENDPLATE]

        boundary_scores = np.zeros(len(points), dtype=np.float32)
        boundary_scores[superior_mask | inferior_mask | posterior_mask] = 0.9

        primitives, qc_summary = derive_primitives_from_point_cloud(points)
        vertex_groups: dict[str, dict[str, object]] = {
            SurfacePatchId.VERTEBRAL_BODY_SURFACE.value: {
                "class_index": SURFACE_PATCH_CLASS_INDEX[SurfacePatchId.VERTEBRAL_BODY_SURFACE],
                "support_count": int(
                    np.count_nonzero(
                        ~(superior_mask | inferior_mask | posterior_mask),
                    )
                ),
                "confidence": 0.8,
            },
            SurfacePatchId.SUPERIOR_ENDPLATE.value: {
                "class_index": SURFACE_PATCH_CLASS_INDEX[SurfacePatchId.SUPERIOR_ENDPLATE],
                "support_count": int(np.count_nonzero(superior_mask)),
                "confidence": 0.86,
            },
            SurfacePatchId.INFERIOR_ENDPLATE.value: {
                "class_index": SURFACE_PATCH_CLASS_INDEX[SurfacePatchId.INFERIOR_ENDPLATE],
                "support_count": int(np.count_nonzero(inferior_mask)),
                "confidence": 0.85,
            },
            SurfacePatchId.POSTERIOR_BODY_WALL.value: {
                "class_index": SURFACE_PATCH_CLASS_INDEX[SurfacePatchId.POSTERIOR_BODY_WALL],
                "support_count": int(np.count_nonzero(posterior_mask)),
                "confidence": 0.83,
            },
        }
        qc_summary = {
            **qc_summary,
            "provider_name": self.provider_name,
            "numbering_confidence": context.numbering_confidence,
            "variant_tags": list(context.variant_tags),
        }
        return StructurePrediction(
            semantic_labels=semantic_labels,
            boundary_scores=boundary_scores,
            primitives=primitives,
            qc_summary=qc_summary,
            vertex_groups=vertex_groups,
            confidence=0.84 if context.supports_standard_measurements else 0.66,
        )


class PointceptPointTransformerV3Adapter:
    provider_name = "pointcept"

    def __init__(
        self,
        *,
        weights_path: Path | None = None,
        config_path: Path | None = None,
    ) -> None:
        self._weights_path = weights_path
        self._config_path = config_path

    def predict_structure(
        self,
        *,
        points_xyz: np.ndarray,
        context: StructureContext,
    ) -> StructurePrediction:
        del points_xyz, context
        try:
            import pointcept  # noqa: F401
        except ImportError as exc:
            raise RuntimeError(
                "Pointcept is not installed in the active landmark runtime."
            ) from exc
        raise RuntimeError(
            "PointceptPointTransformerV3Adapter is scaffolded but not yet wired to trained weights."
        )


def build_model(
    provider_name: str,
    *,
    weights_path: Path | None = None,
    config_path: Path | None = None,
) -> PointCloudLandmarkModel:
    normalized = provider_name.strip().lower()
    if normalized in {"heuristic", "mock", "contract"}:
        return HeuristicPointCloudModel()
    if normalized in {"pointcept", "ptv3"}:
        return PointceptPointTransformerV3Adapter(
            weights_path=weights_path,
            config_path=config_path,
        )
    raise ValueError(f"Unsupported point-cloud provider: {provider_name}")
