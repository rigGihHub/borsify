"""Refresh obsolete acquisition APIs retained by Streamlit during a hot deploy."""
import importlib
import inspect


def ensure_current_acquisition_modules() -> None:
    # Only reload a previously imported, obsolete API. Ordinary reruns leave
    # current modules alone, and this runs before scan workers are created.
    fundamental = importlib.import_module("fundamental_acquisition")
    if "force_refresh" not in inspect.signature(fundamental.fetch_fundamentals).parameters:
        importlib.reload(fundamental)
    snapshot = importlib.import_module("scan_snapshot_cache")
    if not hasattr(snapshot, "fundamental_coverage"):
        importlib.reload(snapshot)
