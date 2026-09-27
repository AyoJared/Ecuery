"""Check (and try to fund) the backend's Solana wallet.

Run from backend/:
    python -m verify.wallet            # address, cluster, balance
    python -m verify.wallet --airdrop  # also request 1 devnet SOL from the public faucet
    python -m verify.wallet --new      # create solana_keypair.json if it doesn't exist
"""

import argparse
import json
import sys
from pathlib import Path

from dotenv import load_dotenv

BACKEND = Path(__file__).resolve().parent.parent
load_dotenv(BACKEND / ".env.local")

from .solana_client import RpcSolanaClient, SolanaUnavailable, get_client, keypair_path  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--airdrop", action="store_true", help="request 1 SOL from the devnet faucet")
    parser.add_argument("--new", action="store_true", help="create backend/solana_keypair.json")
    args = parser.parse_args()

    if args.new:
        path = BACKEND / "solana_keypair.json"
        if path.exists():
            sys.exit(f"{path} already exists; not overwriting it.")
        from solders.keypair import Keypair
        path.write_text(json.dumps(list(bytes(Keypair()))))
        print(f"created {path}. Add SOLANA_KEYPAIR_FILE=\"solana_keypair.json\" to .env.local")
        return

    client = get_client()
    if not isinstance(client, RpcSolanaClient):
        sys.exit(f"SOLANA_KEYPAIR_FILE is not set (currently {keypair_path()}), so the backend uses the mock.")

    print(f"cluster: {client.cluster}\nwallet:  {client.fee_payer}")
    try:
        if args.airdrop:
            sig = client._rpc("requestAirdrop", [client.fee_payer, 1_000_000_000])
            client._wait_confirmed(sig)
            print("airdrop: +1 SOL")
        balance = client.balance()
    except SolanaUnavailable as e:
        print(f"error:   {e}")
        balance = None
    if balance is not None:
        print(f"balance: {balance} SOL (~{int(balance / 0.000005):,} memos)")
    if not balance:
        print(f"\nFund it at https://faucet.solana.com: choose Devnet, paste {client.fee_payer}, and confirm.")


if __name__ == "__main__":
    main()
