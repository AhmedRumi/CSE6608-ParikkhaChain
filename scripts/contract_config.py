"""
ParikkhaChain - Contract Configuration
Manages contract addresses, ABIs, and blockchain connection settings
"""

import json
import os
from pathlib import Path

# Project root directory
PROJECT_ROOT = Path(__file__).parent.parent
ABI_DIR = PROJECT_ROOT / "abi"

# Blockchain connection settings
# Using Remix VM (local) - update this for testnet/mainnet
BLOCKCHAIN_CONFIG = {
    "provider_url": "http://127.0.0.1:8545",  # Ganache or local node
    "chain_id": 1337,  # Ganache default
    "gas_limit": 3000000,
    "gas_price": 20000000000  # 20 gwei
}

# Contract addresses (will be populated after deployment)
# These are placeholders - update after deploying contracts
CONTRACT_ADDRESSES = {
    "RBAC": "",
    "ExamLifecycle": "",
    "HashRegistry": "",
    "ResultAudit": ""
}

# Account addresses (update with your Remix/Ganache accounts)
ACCOUNTS = {
    "admin": "",           # Deploy from this account
    "examiner": "",        # Will be granted EXAMINER role
    "scrutinizer": "",     # Will be granted SCRUTINIZER role
    "student1": "",        # Will be granted STUDENT role
    "student2": "",
    "student3": "",
    "student4": ""
}

# Role enums (matching RBAC.sol)
ROLES = {
    "NONE": 0,
    "ADMIN": 1,
    "EXAMINER": 2,
    "SCRUTINIZER": 3,
    "STUDENT": 4
}
# ROLES = {
#     "ADMIN":       1,   # bit 0
#     "EXAMINER":    2,   # bit 1
#     "SCRUTINIZER": 4,   # bit 2  ← changed from 3 to 4
#     "STUDENT":     8,   # bit 3  ← changed from 4 to 8
# }
# Exam states (matching ExamLifecycle.sol)
EXAM_STATES = {
    "CREATED": 0,
    "ACTIVE": 1,
    "EVALUATION": 2,
    "SCRUTINY": 3,
    "COMPLETED": 4
}

# Grade status (matching ResultAudit.sol)
GRADE_STATUS = {
    "NOT_SUBMITTED": 0,
    "SUBMITTED": 1,
    "UNDER_SCRUTINY": 2,
    "SCRUTINIZED": 3,
    "FINALIZED": 4
}


def load_abi(contract_name):
    """Load ABI for a specific contract"""
    abi_path = ABI_DIR / f"{contract_name}.json"
    
    if not abi_path.exists():
        raise FileNotFoundError(
            f"ABI file not found: {abi_path}\n"
            f"Please copy the ABI from Remix and save it to {abi_path}"
        )
    
    with open(abi_path, 'r') as f:
        return json.load(f)


def get_contract_address(contract_name):
    """Get deployed contract address"""
    address = CONTRACT_ADDRESSES.get(contract_name)
    if not address or address == "":
        raise ValueError(
            f"Contract address not set for {contract_name}.\n"
            f"Please deploy the contract first or update CONTRACT_ADDRESSES."
        )
    return address


def update_contract_address(contract_name, address):
    """Update contract address after deployment"""
    CONTRACT_ADDRESSES[contract_name] = address
    print(f"✅ {contract_name} address updated: {address}")


def save_addresses_to_file(filename="deployed_addresses.json"):
    """Save deployed contract addresses to a file"""
    filepath = PROJECT_ROOT / filename
    with open(filepath, 'w') as f:
        json.dump(CONTRACT_ADDRESSES, f, indent=2)
    print(f"✅ Contract addresses saved to {filepath}")


def load_addresses_from_file(filename="deployed_addresses.json"):
    """Load previously deployed contract addresses"""
    filepath = PROJECT_ROOT / filename
    
    if not filepath.exists():
        print(f"⚠️  No saved addresses file found at {filepath}")
        return False
    
    with open(filepath, 'r') as f:
        saved_addresses = json.load(f)
    
    for contract, address in saved_addresses.items():
        CONTRACT_ADDRESSES[contract] = address
    
    print("✅ Loaded contract addresses from file:")
    for contract, address in CONTRACT_ADDRESSES.items():
        if address:
            print(f"   {contract}: {address}")
    
    return True


# def get_role_name(role_number):
#     """Convert role number to name"""
#     for name, num in ROLES.items():
#         if num == role_number:
#             return name
#     return "UNKNOWN"
def get_role_name(role_num):
    if role_num == 0: return "NONE"
    names = []
    if role_num & 1: names.append("ADMIN")
    if role_num & 2: names.append("EXAMINER")
    if role_num & 4: names.append("SCRUTINIZER")
    if role_num & 8: names.append("STUDENT")
    return "+".join(names) if names else "UNKNOWN"


def get_exam_state_name(state_number):
    """Convert exam state number to name"""
    for name, num in EXAM_STATES.items():
        if num == state_number:
            return name
    return "UNKNOWN"


def get_grade_status_name(status_number):
    """Convert grade status number to name"""
    for name, num in GRADE_STATUS.items():
        if num == status_number:
            return name
    return "UNKNOWN"


def display_config():
    """Display current configuration"""
    print("\n" + "="*60)
    print("📋 PARIKKHCHAIN CONFIGURATION")
    print("="*60)
    
    print("\n🔗 Blockchain Settings:")
    print(f"   Provider: {BLOCKCHAIN_CONFIG['provider_url']}")
    print(f"   Chain ID: {BLOCKCHAIN_CONFIG['chain_id']}")
    print(f"   Gas Limit: {BLOCKCHAIN_CONFIG['gas_limit']}")
    
    print("\n📜 Contract Addresses:")
    for contract, address in CONTRACT_ADDRESSES.items():
        status = "✅" if address else "❌"
        print(f"   {status} {contract}: {address or 'Not deployed'}")
    
    print("\n👥 Accounts:")
    for role, address in ACCOUNTS.items():
        status = "✅" if address else "❌"
        print(f"   {status} {role}: {address or 'Not set'}")
    
    print("\n" + "="*60 + "\n")


if __name__ == "__main__":
    # Display configuration when run directly
    display_config()
    
    # Try to load saved addresses
    load_addresses_from_file()