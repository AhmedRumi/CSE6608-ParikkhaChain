"""
ParikkhaChain - Contract Deployment Helper
Reads parikkhchain_config.json for account layout.
Prompts for Remix-deployed contract addresses, saves them,
then verifies connectivity.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import contract_config as config
from blockchain_interface import BlockchainInterface

PROJECT_ROOT = Path(__file__).parent.parent
CONFIG_FILE  = PROJECT_ROOT / "parikkhchain_config.json"


def load_setup_config():
    if not CONFIG_FILE.exists():
        print("⚠️  parikkhchain_config.json not found.")
        print("   Run: python scripts/setup_config.py first.")
        return None
    with open(CONFIG_FILE) as f:
        return json.load(f)


def header(title):
    print(f"\n{'='*65}\n  {title}\n{'='*65}")


def main():
    header("PARIKKHCHAIN — CONTRACT DEPLOYMENT HELPER")

    # ── Connect ──────────────────────────────────────────────────────────
    try:
        blockchain = BlockchainInterface()
    except Exception as e:
        print(f"\n❌ Cannot connect to blockchain: {e}")
        print("   Make sure Ganache is running on http://127.0.0.1:8545")
        return

    accounts = blockchain.get_accounts()

    # ── Load setup config ─────────────────────────────────────────────────
    cfg = load_setup_config()

    if cfg:
        layout = cfg["account_layout"]
        total  = layout["total_needed"]
        if len(accounts) < total:
            print(f"\n⚠️  Config requires {total} accounts but Ganache has {len(accounts)}.")
            print(f"   Restart Ganache with enough accounts.")
            return

        print(f"\n👥 Account layout from config:")
        print(f"   [0]  Admin")
        for e in cfg["examiners"]:
            print(f"   [{e['account_index']}]  Examiner    — {e['name']}"
                  f"  ({accounts[e['account_index']]})")
        for s in cfg["scrutinizers"]:
            print(f"   [{s['account_index']}]  Scrutinizer — {s['name']}"
                  f"  ({accounts[s['account_index']]})")
        for st in cfg["students"]:
            print(f"   [{st['account_index']}]  Student     — {st['name']}"
                  f"  ({accounts[st['account_index']]})")
    else:
        print(f"\n📋 Ganache accounts:")
        for i, a in enumerate(accounts[:10]):
            print(f"   [{i}] {a}")

    # ── Deployment instructions ───────────────────────────────────────────
    print(f"\n📝 DEPLOYMENT ORDER in Remix (use External HTTP Provider → 127.0.0.1:8545):")
    print(f"   Deploy FROM account [0] (Admin): {accounts[0]}")
    print(f"\n   1. RBAC.sol              — no constructor args")
    print(f"   2. ExamLifecycle.sol     — constructor arg: RBAC address")
    print(f"   3. HashRegistry.sol      — constructor args: RBAC, ExamLifecycle")
    print(f"   4. ResultAudit.sol       — constructor args: RBAC, ExamLifecycle, HashRegistry")

    input(f"\nPress Enter when all 4 contracts are deployed in Remix...\n")

    # ── Collect addresses ─────────────────────────────────────────────────
    print(f"Paste each deployed contract address (from Remix):\n")

    contract_names = ["RBAC", "ExamLifecycle", "HashRegistry", "ResultAudit"]
    addresses      = {}

    for name in contract_names:
        while True:
            addr = input(f"  {name} address: ").strip()
            if addr.startswith("0x") and len(addr) == 42:
                addresses[name] = addr
                break
            print(f"   ⚠️  Invalid address — must be 0x followed by 40 hex chars")

    # ── Save addresses ────────────────────────────────────────────────────
    for name, addr in addresses.items():
        try:
            blockchain.update_deployed_address(name, addr)
        except Exception as e:
            print(f"⚠️  {name}: {e}")

    config.save_addresses_to_file()
    print(f"\n💾 Addresses saved to deployed_addresses.json")

    # ── Test connectivity ─────────────────────────────────────────────────
    print(f"\n🧪 Testing contract connectivity...")
    all_ok = True
    for name in contract_names:
        try:
            blockchain.get_contract(name)
            print(f"   ✅ {name}")
        except Exception as e:
            print(f"   ❌ {name}: {e}")
            all_ok = False

    if all_ok:
        print(f"\n🎉 All contracts accessible!")
    else:
        print(f"\n⚠️  Some contracts failed — check addresses and ABI files")
        return

    # ── Show assignment summary ───────────────────────────────────────────
    if cfg:
        print(f"\n📋 Exam assignments (will be applied by workflow):")

        # Build a combined people list (examiners + scrutinizers) for safe lookup
        all_people = cfg.get("examiners", []) + cfg.get("scrutinizers", [])

        for i, exam in enumerate(cfg["exams"]):
            ex_indices = cfg["exam_examiner_map"].get(str(i), [])
            sc_indices = cfg["exam_scrutinizer_map"].get(str(i), [])

            ex_names = []
            for j in ex_indices:
                if j < len(cfg.get("examiners", [])):
                    ex_names.append(cfg["examiners"][j]["name"])
                elif j < len(all_people):
                    ex_names.append(all_people[j]["name"])

            sc_names = []
            for j in sc_indices:
                if j < len(cfg.get("scrutinizers", [])):
                    sc_names.append(cfg["scrutinizers"][j]["name"])
                elif j < len(all_people):
                    sc_names.append(all_people[j]["name"])

            print(f"\n   {exam['name']}:")
            print(f"      Examiners:    {', '.join(ex_names) or 'none'}")
            print(f"      Scrutinizers: {', '.join(sc_names) or 'none'}")

    print(f"\n📋 Next steps:")
    print(f"   python scripts/generate_mock_data.py")
    print(f"   python scripts/run_workflow_demo.py\n")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n⚠️  Cancelled")
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()