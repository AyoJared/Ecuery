"""Step 8c/8d: write the hash to Solana as a memo transaction, get a signature.

RpcSolanaClient sends a real Memo program transaction, signed by the backend
wallet (SOLANA_KEYPAIR_FILE), and reads memos back from the chain, so
verification survives restarts and anyone can check it on the explorer.
Without a keypair file, MockSolanaClient simulates this in memory.

Wallet status / funding: `python -m verify.wallet`
"""

import hashlib
import json
import os
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Protocol

import httpx

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


class SolanaUnavailable(RuntimeError):
    pass


class SolanaClient(Protocol):
    cluster: str
    mode: str

    def send_memo(self, memo: str) -> MemoTransaction: ...

    def get_transaction(self, signature: str) -> MemoTransaction | None: ...


class MockSolanaClient:
    mode = "mock"

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


class RpcSolanaClient:
    mode = "rpc"

    def __init__(self, keypair_file: Path, cluster: str = "devnet", rpc_url: str | None = None):
        from solders.keypair import Keypair

        self.keypair = Keypair.from_bytes(bytes(json.loads(keypair_file.read_text())))
        self.cluster = cluster
        self.rpc_url = rpc_url or f"https://api.{cluster}.solana.com"
        self.fee_payer = str(self.keypair.pubkey())
        self._http = httpx.Client(timeout=30)

    def _rpc(self, method: str, params: list, attempts: int = 3):
        # The public devnet endpoint rate-limits bursts (HTTP 429) and hiccups; retry those briefly.
        for attempt in range(attempts):
            try:
                resp = self._http.post(self.rpc_url, json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params})
                transient = resp.status_code == 429 or resp.status_code >= 500
                body = None if transient else resp.json()
                if body is not None and body.get("error", {}).get("code") == 429:
                    transient = True
            except (httpx.HTTPError, ValueError) as e:
                transient, body, reason = True, None, str(e)
            else:
                reason = f"HTTP {resp.status_code}"
            if not transient:
                break
            if attempt == attempts - 1:
                raise SolanaUnavailable(f"Solana {self.cluster} unavailable for {method}: {reason}")
            time.sleep(0.5 * 2 ** attempt)
        if "error" in body:
            message = body["error"].get("message", str(body["error"]))
            if "no record of a prior credit" in message or "insufficient" in message.lower():
                message = f"Wallet {self.fee_payer} has no {self.cluster} SOL. Fund it: python -m verify.wallet"
            raise SolanaUnavailable(f"Solana {method} failed: {message}")
        return body["result"]

    def balance(self) -> float:
        return self._rpc("getBalance", [self.fee_payer, {"commitment": "confirmed"}])["value"] / 1e9

    def send_memo(self, memo: str) -> MemoTransaction:
        import base64

        from solders.hash import Hash
        from solders.instruction import AccountMeta, Instruction
        from solders.message import Message
        from solders.pubkey import Pubkey
        from solders.transaction import Transaction

        blockhash = Hash.from_string(self._rpc("getLatestBlockhash", [{"commitment": "confirmed"}])["value"]["blockhash"])
        ix = Instruction(Pubkey.from_string(MEMO_PROGRAM_ID), memo.encode(),
                         [AccountMeta(self.keypair.pubkey(), is_signer=True, is_writable=False)])
        tx = Transaction([self.keypair], Message.new_with_blockhash([ix], self.keypair.pubkey(), blockhash), blockhash)
        signature = self._rpc("sendTransaction", [base64.b64encode(bytes(tx)).decode(),
                                                  {"encoding": "base64", "preflightCommitment": "confirmed"}])
        self._wait_confirmed(signature)
        return self.get_transaction(signature) or MemoTransaction(
            signature, memo, 0, int(time.time()), self.cluster, self.fee_payer)

    def _wait_confirmed(self, signature: str, timeout: float = 30) -> None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            status = self._rpc("getSignatureStatuses", [[signature]])["value"][0]
            if status and status.get("err"):
                raise SolanaUnavailable(f"Transaction {signature} failed: {status['err']}")
            if status and status.get("confirmationStatus") in ("confirmed", "finalized"):
                return
            time.sleep(0.4)
        raise SolanaUnavailable(f"Transaction {signature} not confirmed after {timeout:.0f}s")

    def get_transaction(self, signature: str) -> MemoTransaction | None:
        try:
            tx = self._rpc("getTransaction", [signature, {"encoding": "jsonParsed", "commitment": "confirmed",
                                                          "maxSupportedTransactionVersion": 0}])
        except SolanaUnavailable as e:
            if "Invalid param" in str(e) or "WrongSize" in str(e):
                return None  # not a valid signature
            raise
        if not tx:
            return None
        message = tx["transaction"]["message"]
        memo = next((ix.get("parsed") for ix in message["instructions"]
                     if ix.get("programId") == MEMO_PROGRAM_ID), None)
        if memo is None:
            return None
        return MemoTransaction(
            signature=signature,
            memo=memo,
            slot=tx["slot"],
            block_time=tx.get("blockTime") or 0,
            cluster=self.cluster,
            fee_payer=message["accountKeys"][0]["pubkey"],
        )


_client: SolanaClient | None = None


def keypair_path() -> Path | None:
    value = os.getenv("SOLANA_KEYPAIR_FILE")
    if not value:
        return None
    path = Path(value)
    return path if path.is_absolute() else Path(__file__).resolve().parent.parent / path


def get_client() -> SolanaClient:
    global _client
    if _client is None:
        cluster = os.getenv("SOLANA_CLUSTER", "devnet")
        path = keypair_path()
        if path:
            _client = RpcSolanaClient(path, cluster, os.getenv("SOLANA_RPC_URL"))
        else:
            _client = MockSolanaClient(cluster)
    return _client
