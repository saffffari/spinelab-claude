from __future__ import annotations

from spinelab.pipeline.backends.landmark_point_transformer import (
    ENVIRONMENT as LANDMARKPT_ENVIRONMENT,
)
from spinelab.pipeline.backends.landmark_point_transformer import (
    LandmarkPointTransformerAdapter,
)
from spinelab.pipeline.backends.nanodrr import ENVIRONMENT as NANODRR_ENVIRONMENT
from spinelab.pipeline.backends.nanodrr import NanoDrrAdapter
from spinelab.pipeline.backends.nnunet import ENVIRONMENT as NNUNET_ENVIRONMENT
from spinelab.pipeline.backends.nnunet import NnUNetV2Adapter
from spinelab.pipeline.backends.polypose import (
    ENVIRONMENT as POLYPOSE_ENVIRONMENT,
)
from spinelab.pipeline.backends.polypose import (
    PolyPoseAdapter,
)

BACKEND_ADAPTERS = (
    NnUNetV2Adapter(),
    NanoDrrAdapter(),
    PolyPoseAdapter(),
    LandmarkPointTransformerAdapter(),
)

ENVIRONMENT_SPECS = (
    NNUNET_ENVIRONMENT,
    NANODRR_ENVIRONMENT,
    POLYPOSE_ENVIRONMENT,
    LANDMARKPT_ENVIRONMENT,
)

__all__ = ["BACKEND_ADAPTERS", "ENVIRONMENT_SPECS"]
