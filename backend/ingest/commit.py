"""Load a batch, anchor its manifest on Solana, and register it. Loading first means we only vouch for stored rows."""

from . import store
from .provenance import Batch, anchor


def commit(batch: Batch) -> dict | None:
    if not batch.rows:
        return None
    if batch.store == "tiger":
        store.load_tiger(batch)
    else:
        store.load_snowflake(batch)
    manifest = batch.manifest()
    anchored = anchor(manifest)
    store.register(batch, manifest, anchored)
    return anchored
