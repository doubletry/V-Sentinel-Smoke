# Migrating a core scene into backend

A scene should keep AI logic in `core/<scene>/` and expose a thin backend adapter in `backend/processing/<scene>/`.

## Steps

1. Implement `core/<scene>/processor.py` by inheriting `core.base_processor.BaseVideoProcessor`.
2. Return a generic `AnalysisResult` containing detections, messages, an annotated frame, and optional `extra` event payloads.
3. Create `backend/processing/<scene>/processor.py` that inherits both `backend.processing.base.BaseVideoProcessor` and the core processor.
4. Add `backend/processing/<scene>/metadata.py` for display names.
5. Register the adapter in `backend/processing/registry.py`.
6. Add scene settings to `backend/config.py`, `backend/models/schemas.py`, and the frontend settings page.

The default `smoke` plugin is the reference implementation.
