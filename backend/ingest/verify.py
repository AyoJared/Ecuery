"""Check a source batch end to end: database rows -> manifest -> Solana -> (optionally) the agency itself."""

import hashlib

from verify.solana_client import SolanaUnavailable, get_client as get_solana

from . import store
from .provenance import MEMO_PREFIX, manifest_sha256, rows_sha256, _http


def batch_info(batch_ids: list[str]) -> list[dict]:
    """Public provenance for the batches behind an answer."""
    if not batch_ids:
        return []
    out = []
    for r in store.registry(sorted(set(batch_ids))):
        out.append({
            "batch_id": r["batch_id"], "source": r["source"], "dataset": r["dataset"], "quality": r["quality"],
            "fetched_at": r["fetched_at"].isoformat(), "row_count": r["row_count"],
            "manifest_sha256": r["manifest_sha256"], "signature": r["solana_signature"],
            "explorer_url": _explorer(r), "anchored": bool(r["solana_signature"]),
            # First exact request to the agency, so people can open the raw data (credentials are
            # stripped before it's shown: shared/source_links.py).
            "request_url": next((q["url"] for q in (r.get("manifest") or {}).get("requests", []) if q.get("url")), None),
        })
    return sorted(out, key=lambda b: (b["source"], b["fetched_at"]))


def _explorer(r: dict) -> str | None:
    if not r["solana_signature"]:
        return None
    suffix = "" if r["solana_cluster"] == "mainnet-beta" else f"?cluster={r['solana_cluster']}"
    return f"https://explorer.solana.com/tx/{r['solana_signature']}{suffix}"


def verify_batch(batch_id: str, refetch: bool = False, max_refetch: int = 3) -> dict:
    found = store.registry([batch_id])
    if not found:
        return {"batch_id": batch_id, "found": False}
    reg = found[0]
    manifest = reg["manifest"]
    checks: dict[str, dict] = {}

    # 1. The manifest in the registry is the one that was anchored.
    recomputed = manifest_sha256(manifest)
    checks["manifest"] = {"ok": recomputed == reg["manifest_sha256"], "expected": reg["manifest_sha256"], "actual": recomputed}

    # 2. Solana holds exactly that manifest hash, signed by our wallet.
    if reg["solana_signature"]:
        try:
            tx = get_solana().get_transaction(reg["solana_signature"])
            memo = tx.memo if tx else None
            checks["solana"] = {"ok": memo == MEMO_PREFIX + reg["manifest_sha256"], "memo": memo,
                                "slot": tx.slot if tx else None, "signer": tx.fee_payer if tx else None}
        except SolanaUnavailable as e:
            checks["solana"] = {"ok": False, "error": str(e)}
    else:
        checks["solana"] = {"ok": False, "error": reg["anchor_error"] or "never anchored"}

    # 3. The rows in Tiger/Snowflake are the ones that were ingested (nobody edited them since).
    rows = store.stored_rows(batch_id, reg["store"])
    rows_hash = rows_sha256(rows)
    superseded = len(rows) < manifest["row_count"]
    checks["rows"] = {"ok": rows_hash == manifest["rows_sha256"], "stored": len(rows), "ingested": manifest["row_count"],
                      "expected": manifest["rows_sha256"], "actual": rows_hash,
                      **({"note": "some rows were since replaced by a newer ingest of the same source"} if superseded else {})}

    # 4. Optional: does the agency still serve the same bytes? (Agencies do revise data; that's reported, not hidden.)
    if refetch:
        results = []
        for req in manifest["requests"][:max_refetch]:
            try:
                body = _http.get(req["url"]).content
                results.append({"url": req["url"], "same_bytes": hashlib.sha256(body).hexdigest() == req["sha256"]})
            except Exception as e:
                results.append({"url": req["url"], "error": str(e)[:120]})
        checks["source"] = {"ok": all(r.get("same_bytes") for r in results), "checked": results,
                            "total_files": len(manifest["requests"])}

    status = "verified" if checks["manifest"]["ok"] and checks["solana"]["ok"] and checks["rows"]["ok"] else \
        "superseded" if checks["manifest"]["ok"] and checks["solana"]["ok"] and superseded else "failed"
    return {"batch_id": batch_id, "found": True, "status": status, "source": reg["source"], "dataset": reg["dataset"],
            "quality": reg["quality"], "store": reg["store"], "fetched_at": reg["fetched_at"].isoformat(),
            "explorer_url": _explorer(reg), "checks": checks}
