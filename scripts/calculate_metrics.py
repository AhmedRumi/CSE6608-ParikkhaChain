"""
ParikkhaChain - Blockchain Metrics Calculator

Metrics:
  1. Throughput
       - Total transactions
       - Time elapsed (first block → last block timestamp)
       - Throughput = transactions / elapsed_seconds (tx/sec)

  2. Total Transaction Cost
       - Total gas used (sum of gasUsed across all transactions)
       - Cost in ETH = total_gas × gas_price_gwei / 1,000,000,000
       - Cost in USD = cost_eth × eth_price_usd

Usage:
  python scripts/calculate_metrics.py
"""

import sys
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent))

import contract_config as config
from blockchain_interface import BlockchainInterface

# ─── Configuration ────────────────────────────────────────────────────────────
# Set these to current real-world values for meaningful USD estimate.
# Ganache uses a dummy gas price so we set a realistic mainnet value here.
GAS_PRICE_GWEI = 20       # typical mainnet gas price in gwei
ETH_PRICE_USD  = 3000     # current ETH/USD price


def main():
    print("\n" + "="*65)
    print("  PARIKKHCHAIN — BLOCKCHAIN METRICS")
    print("="*65)

    config.load_addresses_from_file()
    bc  = BlockchainInterface()
    w3  = bc.web3

    latest_block = w3.eth.block_number

    print(f"\n  Chain ID     : {w3.eth.chain_id}")
    print(f"  Latest block : {latest_block}")

    if latest_block == 0:
        print("\n  ⚠️  No transactions found. Run the workflow first.")
        return

    # ── Collect all transactions ───────────────────────────────────────────
    print(f"\n  Scanning {latest_block} block(s)...", end="", flush=True)

    total_tx   = 0
    total_gas  = 0
    failed_tx  = 0

    first_timestamp = None
    last_timestamp  = None

    deploy_tx   = 0
    deploy_gas  = 0
    tx_gas_list = []

    for block_num in range(1, latest_block + 1):
        block = w3.eth.get_block(block_num, full_transactions=True)

        # Track timestamps
        if first_timestamp is None:
            first_timestamp = block.timestamp
        last_timestamp = block.timestamp

        for tx in block.transactions:
            receipt   = w3.eth.get_transaction_receipt(tx.hash)
            gas_used  = receipt.gasUsed
            # Contract deployment: tx.to is None or empty string
            is_deploy = (tx.to is None or tx.to == "" or
                         str(tx.get("to", "")).lower() in ("none", "", "0x"))

            total_tx  += 1
            total_gas += gas_used
            if receipt.status == 0:
                failed_tx += 1

            tx_gas_list.append((tx.hash.hex(), gas_used,
                                str(tx.to) if tx.to else "DEPLOY", is_deploy))

            if is_deploy:
                deploy_tx  += 1
                deploy_gas += gas_used

    print(" done.\n")

    # ── Metric 1: Throughput ───────────────────────────────────────────────
    first_dt  = datetime.fromtimestamp(first_timestamp)
    last_dt   = datetime.fromtimestamp(last_timestamp)
    elapsed_s = last_timestamp - first_timestamp

    if elapsed_s > 0:
        throughput = total_tx / elapsed_s
    else:
        throughput = float(total_tx)   # all in same second

    elapsed_str = str(last_dt - first_dt)   # HH:MM:SS format

    # ── Metric 2: Cost ────────────────────────────────────────────────────
    cost_eth = (total_gas * GAS_PRICE_GWEI) / 1_000_000_000
    cost_usd = cost_eth * ETH_PRICE_USD
    avg_gas  = total_gas // total_tx if total_tx > 0 else 0

    # ── Display ───────────────────────────────────────────────────────────
    # Workflow-only stats (exclude contract deployments)
    workflow_tx  = total_tx  - deploy_tx
    workflow_gas = total_gas - deploy_gas
    avg_wf_gas   = workflow_gas // workflow_tx if workflow_tx > 0 else 0

    # Per-contract gas breakdown
    from collections import defaultdict
    contract_gas = defaultdict(lambda: {"txs": 0, "gas": 0, "name": ""})

    contract_lookup = {
        v.lower(): k for k, v in config.CONTRACT_ADDRESSES.items() if v
    }

    for txh, gas, to, deploy in tx_gas_list:
        if deploy:
            key = "DEPLOY"
            contract_gas[key]["name"] = "Contract Deployments"
        else:
            to_lower = to.lower()
            name = contract_lookup.get(to_lower, to[:14]+"...")
            key = name
            contract_gas[key]["name"] = name
        contract_gas[key]["txs"]  += 1
        contract_gas[key]["gas"]  += gas

    print("\n  Gas breakdown by contract:")
    print(f"  {'Contract':<20} {'Txs':>5} {'Total Gas':>12} {'Avg Gas':>10} {'% of total':>10}")
    print(f"  {'─'*20} {'─'*5} {'─'*12} {'─'*10} {'─'*10}")
    for key, val in sorted(contract_gas.items(), key=lambda x: x[1]['gas'], reverse=True):
        pct = val['gas'] / total_gas * 100
        avg = val['gas'] // val['txs'] if val['txs'] else 0
        print(f"  {val['name']:<20} {val['txs']:>5} {val['gas']:>12,} {avg:>10,} {pct:>9.1f}%")

    print("\n  Top 5 heaviest individual transactions:")
    sorted_txs = sorted(tx_gas_list, key=lambda x: x[1], reverse=True)[:5]
    for txh, gas, to, deploy in sorted_txs:
        to_lower = to.lower()
        name = "DEPLOY" if deploy else contract_lookup.get(to_lower, to[:14]+"...")
        print(f"    {txh[:16]}...  gas={gas:>10,}  {name}")

    W = 57
    print("╔" + "═"*W + "╗")
    print("║" + " METRIC 1 — THROUGHPUT".center(W) + "║")
    print("╠" + "═"*W + "╣")
    print("║" + f"  Total transactions      : {total_tx}".ljust(W) + "║")
    print("║" + f"    Contract deployments  : {deploy_tx}".ljust(W) + "║")
    print("║" + f"    Workflow transactions : {workflow_tx}".ljust(W) + "║")
    print("║" + f"  Successful              : {total_tx - failed_tx}".ljust(W) + "║")
    print("║" + f"  Failed                  : {failed_tx}".ljust(W) + "║")
    print("╠" + "─"*W + "╣")
    print("║" + f"  First block time    : {first_dt.strftime('%Y-%m-%d %H:%M:%S')}".ljust(W) + "║")
    print("║" + f"  Last block time     : {last_dt.strftime('%Y-%m-%d %H:%M:%S')}".ljust(W) + "║")
    print("║" + f"  Elapsed time        : {elapsed_str}  ({elapsed_s}s)".ljust(W) + "║")
    print("╠" + "─"*W + "╣")
    if elapsed_s > 0:
        print("║" + f"  Throughput          : {throughput:.4f} tx/sec".ljust(W) + "║")
        print("║" + f"                        {throughput*60:.2f} tx/min".ljust(W) + "║")
    else:
        print("║" + f"  Throughput          : all {total_tx} tx in <1 second".ljust(W) + "║")
    # Cost calculations — full and workflow-only
    wf_cost_eth = (workflow_gas * GAS_PRICE_GWEI) / 1_000_000_000
    wf_cost_usd = wf_cost_eth * ETH_PRICE_USD

    print("╠" + "═"*W + "╣")
    print("║" + " METRIC 2 — TRANSACTION COST".center(W) + "║")
    print("╠" + "═"*W + "╣")
    print("║" + f"  Gas price (assumed)     : {GAS_PRICE_GWEI} gwei".ljust(W) + "║")
    print("║" + f"  ETH price (assumed)     : ${ETH_PRICE_USD:,}".ljust(W) + "║")
    print("╠" + "─"*W + "╣")
    print("║" + "  ALL transactions (incl. deployments):".ljust(W) + "║")
    print("║" + f"    Total gas             : {total_gas:,}".ljust(W) + "║")
    print("║" + f"    Cost in ETH           : {cost_eth:.8f} ETH".ljust(W) + "║")
    print("║" + f"    Cost in USD           : ${cost_usd:.4f}".ljust(W) + "║")
    print("╠" + "─"*W + "╣")
    print("║" + "  WORKFLOW only (excl. deployments):".ljust(W) + "║")
    print("║" + f"    Workflow gas          : {workflow_gas:,}".ljust(W) + "║")
    print("║" + f"    Avg gas per tx        : {avg_wf_gas:,}".ljust(W) + "║")
    print("║" + f"    Formula: {workflow_gas:,} × {GAS_PRICE_GWEI} ÷ 1,000,000,000".ljust(W) + "║")
    print("║" + f"    Cost in ETH           : {wf_cost_eth:.8f} ETH".ljust(W) + "║")
    print("║" + f"    Cost in USD           : ${wf_cost_usd:.4f}".ljust(W) + "║")
    print("║" + f"    Avg cost per tx       : ${wf_cost_usd/workflow_tx:.6f}".ljust(W) + "║")
    print("╚" + "═"*W + "╝")

    print(f"\n  ⚠️  Note: Gas price ({GAS_PRICE_GWEI} gwei) and ETH price")
    print(f"     (${ETH_PRICE_USD}) are assumed mainnet values.")
    print(f"     Edit GAS_PRICE_GWEI and ETH_PRICE_USD at the top of")
    print(f"     this script to use current real-world values.")
    print()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n⚠️  Cancelled")
    except Exception as e:
        print(f"\n❌ {e}")
        import traceback
        traceback.print_exc()