"""One confidence policy for live control, verification and evaluation."""
ZOOM_MINIMUM = 0.10


def effective_threshold(mapping, settings):
    configured = mapping.get('threshold') if mapping else None
    configured = settings.threshold if configured is None else configured
    return max(ZOOM_MINIMUM if mapping and mapping.get('action') in ('zoom_in', 'zoom_out') else 0., configured)
