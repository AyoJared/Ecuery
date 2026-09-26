"""Step 8c/8d: write the hash to Solana as a memo transaction, get a signature.

MockSolanaClient simulates devnet: it returns realistic base58 signatures,
slots and block times, and keeps an in-memory "ledger" so transactions can be
looked up again for verification. To go live, implement SolanaClient against
devnet (solders + solana-py: build a Memo program instruction, sign with the
backend keypair, send_transaction, then get_transaction to read it back) and
swap it in via get_client().
"""

import hashlib
import os
import time
from dataclasses import dataclass, asdict
from typing import Protocol

MEMO_PROGRAM_ID = "MemoSq4gqABAXKb96qnH8TysNcWxMyWCqXgDLGmfcHr"
_B58_ALPHABET = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"


def b58encode(data: bytes) -> str:
    n = int.from_bytes(data, "big")
    out = ""
    while n:
        n, rem = divmod(n, 58)
        out = _B58_ALPHABET[rem] + out
    pad = len(data) - len(data.lstrip(b"\0"))
    return "1" * pad + out


@dataclass
class MemoTransaction:
    signature: str
    memo: str
    slot: int
    block_time: int
    cluster: str
    fee_payer: str
    program_id: str = MEMO_PROGRAM_ID

    @property
    def explorer_url(self) -> str:
        return explorer_url(self.signature, self.cluster)

    def to_dict(self) -> dict:
        return {**asdict(self), "explorer_url": self.explorer_url}


def explorer_url(signature: str, cluster: str = "devnet") -> str:
    suffix = "" if cluster == "mainnet-beta" else f"?cluster={cluster}"
    return f"https://explorer.solana.com/tx/{signature}{suffix}"


class SolanaClient(Protocol):
    cluster: str

    def send_memo(self, memo: str) -> MemoTransaction: ...

    def get_transaction(self, signature: str) -> MemoTransaction | None: ...


class MockSolanaClient:
    def __init__(self, cluster: str = "devnet"):
        self.cluster = cluster
        self._ledger: dict[str, MemoTransaction] = {}
        self._slot = 312_000_000
        self.fee_payer = b58encode(hashlib.sha256(b"ecuery-backend-wallet").digest())

    def send_memo(self, memo: str) -> MemoTransaction:
        self._slot += 1
        # Real Solana signatures are 64-byte ed25519 sigs, base58 encoded.
        raw_sig = hashlib.sha512(f"{memo}|{self._slot}|{time.time_ns()}".encode()).digest()
        tx = MemoTransaction(
            signature=b58encode(raw_sig),
            memo=memo,
            slot=self._slot,
            block_time=int(time.time()),
            cluster=self.cluster,
            fee_payer=self.fee_payer,
        )
        self._ledger[tx.signature] = tx
        return tx

    def get_transaction(self, signature: str) -> MemoTransaction | None:
        return self._ledger.get(signature)


_client: SolanaClient | None = None


def get_client() -> SolanaClient:
    global _client
    if _client is None:
        _client = MockSolanaClient(cluster=os.getenv("SOLANA_CLUSTER", "devnet"))
    return _client
