"""Step 8 API: anchor an answer on Solana and verify it later.

POST /verify/anchor   answer payload -> hash, signature, explorer link, badge
POST /verify/check    signature + payload -> recompute hash, compare to memo
GET  /verify/tx/{sig} look up an anchored transaction
GET  /verify/status   mock or real chain, wallet address and balance
"""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from .hashing import build_record, digest_from_memo, memo_for, sha256_hex
from .solana_client import SolanaClient, SolanaUnavailable, get_client

router = APIRouter(prefix="/verify", tags=["verify"])


class AnchorRequest(BaseModel):
    query: str
    result: Any
    source: str
    timestamp: str | None = None


class CheckRequest(AnchorRequest):
    signature: str
    timestamp: str  # must match the timestamp that was anchored


class Badge(BaseModel):
    verified: bool
    label: str


class AnchorResponse(BaseModel):
    record: dict
    hash: str
    memo: str
    signature: str
    slot: int
    block_time: int
    cluster: str
    explorer_url: str
    badge: Badge


class CheckResponse(BaseModel):
    signature: str
    expected_hash: str
    onchain_hash: str | None
    explorer_url: str
    badge: Badge


@router.post("/anchor", response_model=AnchorResponse)
def anchor(req: AnchorRequest, client: SolanaClient = Depends(get_client)):
    record = build_record(req.query, req.result, req.source, req.timestamp)
    digest = sha256_hex(record)
    try:
        tx = client.send_memo(memo_for(digest))
    except SolanaUnavailable as e:
        raise HTTPException(503, str(e))
    return AnchorResponse(
        record=record,
        hash=digest,
        memo=tx.memo,
        signature=tx.signature,
        slot=tx.slot,
        block_time=tx.block_time,
        cluster=tx.cluster,
        explorer_url=tx.explorer_url,
        badge=Badge(verified=True, label="Verified on Solana" if client.mode == "rpc" else "Verified (simulated)"),
    )


@router.post("/check", response_model=CheckResponse)
def check(req: CheckRequest, client: SolanaClient = Depends(get_client)):
    tx = _lookup(client, req.signature)
    if tx is None:
        raise HTTPException(404, "Transaction not found")
    expected = sha256_hex(build_record(req.query, req.result, req.source, req.timestamp))
    onchain = digest_from_memo(tx.memo)
    ok = onchain == expected
    return CheckResponse(
        signature=tx.signature,
        expected_hash=expected,
        onchain_hash=onchain,
        explorer_url=tx.explorer_url,
        badge=Badge(verified=ok, label="Verified on Solana" if ok else "Data does not match on-chain hash"),
    )


@router.get("/tx/{signature}")
def get_tx(signature: str, client: SolanaClient = Depends(get_client)):
    tx = _lookup(client, signature)
    if tx is None:
        raise HTTPException(404, "Transaction not found")
    return tx.to_dict()


@router.get("/status")
def status(client: SolanaClient = Depends(get_client)):
    info = {"mode": client.mode, "cluster": client.cluster, "wallet": client.fee_payer}
    if client.mode == "rpc":
        try:
            info["balance_sol"] = client.balance()
        except SolanaUnavailable as e:
            info["error"] = str(e)
    return info


def _lookup(client: SolanaClient, signature: str):
    try:
        return client.get_transaction(signature)
    except SolanaUnavailable as e:
        raise HTTPException(503, str(e))
