"""
ParikkhaChain - Blockchain Interface
Handles Web3 connection and contract interactions
"""

from web3 import Web3
from web3.middleware import ExtraDataToPOAMiddleware
import contract_config as config


class BlockchainInterface:
    """Wrapper for Web3 blockchain interactions"""
    
    def __init__(self, provider_url=None):
        """Initialize Web3 connection"""
        self.provider_url = provider_url or config.BLOCKCHAIN_CONFIG['provider_url']
        
        # Connect to blockchain
        try:
            self.web3 = Web3(Web3.HTTPProvider(self.provider_url))
            
            # Add PoA middleware (needed for some testnets) - web3.py v6+
            self.web3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)
            
            # Check connection
            if not self.web3.is_connected():
                raise ConnectionError(f"Failed to connect to {self.provider_url}")
            
            print(f"✅ Connected to blockchain: {self.provider_url}")
            print(f"   Chain ID: {self.web3.eth.chain_id}")
            print(f"   Latest block: {self.web3.eth.block_number}")
            
        except Exception as e:
            print(f"❌ Failed to connect to blockchain: {e}")
            raise
        
        # Contract instances (will be loaded as needed)
        self.contracts = {}
    
    
    def get_accounts(self):
        """Get list of available accounts"""
        accounts = self.web3.eth.accounts
        print(f"\n📋 Available accounts: {len(accounts)}")
        for i, account in enumerate(accounts):
            balance = self.web3.eth.get_balance(account)
            balance_eth = self.web3.from_wei(balance, 'ether')
            print(f"   [{i}] {account} - {balance_eth:.4f} ETH")
        return accounts
    
    
    def load_contract(self, contract_name, address=None):
        """Load a deployed contract instance"""
        try:
            # Load ABI
            abi = config.load_abi(contract_name)
            
            # Get address
            if address is None:
                address = config.get_contract_address(contract_name)
            
            # Validate address
            if not self.web3.is_address(address):
                raise ValueError(f"Invalid contract address: {address}")
            
            # Convert to checksum address
            address = self.web3.to_checksum_address(address)
            
            # Create contract instance
            contract = self.web3.eth.contract(address=address, abi=abi)
            
            # Cache it
            self.contracts[contract_name] = contract
            
            print(f"✅ Loaded {contract_name} at {address}")
            return contract
            
        except Exception as e:
            print(f"❌ Failed to load {contract_name}: {e}")
            raise
    
    
    def get_contract(self, contract_name):
        """Get cached contract instance or load it"""
        if contract_name not in self.contracts:
            self.load_contract(contract_name)
        return self.contracts[contract_name]
    
    
    def deploy_contract(self, contract_name, constructor_args=None, deployer_account=None):
        """Deploy a smart contract"""
        try:
            print(f"\n🚀 Deploying {contract_name}...")
            
            # Load ABI
            abi = config.load_abi(contract_name)
            
            # Load bytecode (you'll need to add this to ABI files or compile)
            # For now, we'll assume deployment happens in Remix
            # This function will store the deployed address
            
            raise NotImplementedError(
                "Deployment from Python requires contract bytecode.\n"
                "For this project, deploy contracts in Remix, then update addresses.\n"
                "Use update_deployed_address() after deployment."
            )
            
        except Exception as e:
            print(f"❌ Deployment failed: {e}")
            raise
    
    
    def update_deployed_address(self, contract_name, address):
        """Update contract address after manual deployment in Remix"""
        # Validate address
        if not self.web3.is_address(address):
            raise ValueError(f"Invalid address: {address}")
        
        # Convert to checksum
        address = self.web3.to_checksum_address(address)
        
        # Update config
        config.update_contract_address(contract_name, address)
        
        # Load contract
        self.load_contract(contract_name, address)
        
        return address
    
    
    def send_transaction(self, contract_function, from_account, gas_limit=None):
        """Send a transaction to a contract function"""
        try:
            # Build transaction
            tx = contract_function.build_transaction({
                'from': self.web3.to_checksum_address(from_account),
                'gas': gas_limit or config.BLOCKCHAIN_CONFIG['gas_limit'],
                'gasPrice': config.BLOCKCHAIN_CONFIG['gas_price'],
                'nonce': self.web3.eth.get_transaction_count(from_account)
            })
            
            # For Remix/Ganache, accounts are unlocked, so we can send directly
            # For real networks, you'd need to sign with private key
            tx_hash = self.web3.eth.send_transaction(tx)
            
            # Wait for receipt
            print(f"   ⏳ Transaction sent: {tx_hash.hex()}")
            receipt = self.web3.eth.wait_for_transaction_receipt(tx_hash)
            
            if receipt['status'] == 1:
                print(f"   ✅ Transaction successful!")
                print(f"      Block: {receipt['blockNumber']}")
                print(f"      Gas used: {receipt['gasUsed']}")
                return receipt
            else:
                print(f"   ❌ Transaction failed!")
                return None
                
        except Exception as e:
            print(f"   ❌ Transaction error: {e}")
            raise
    
    
    def call_function(self, contract_function, from_account=None):
        """Call a view/pure function (no transaction needed)"""
        try:
            if from_account:
                result = contract_function.call({'from': from_account})
            else:
                result = contract_function.call()
            return result
        except Exception as e:
            print(f"   ❌ Function call error: {e}")
            raise
    
    
    def get_transaction_receipt(self, tx_hash):
        """Get transaction receipt"""
        return self.web3.eth.get_transaction_receipt(tx_hash)
    
    
    def get_block(self, block_number='latest'):
        """Get block information"""
        return self.web3.eth.get_block(block_number)
    
    
    def get_balance(self, address):
        """Get ETH balance of an address"""
        balance_wei = self.web3.eth.get_balance(address)
        balance_eth = self.web3.from_wei(balance_wei, 'ether')
        return balance_eth
    
    
    def get_events(self, contract_name, event_name, from_block=0, to_block='latest'):
        """Get past events from a contract"""
        contract = self.get_contract(contract_name)
        event_filter = getattr(contract.events, event_name).create_filter(
            fromBlock=from_block,
            toBlock=to_block
        )
        return event_filter.get_all_entries()


# Convenience functions for specific contracts

class RBACInterface(BlockchainInterface):
    """Wrapper for RBAC contract interactions"""
    
    def grant_role(self, address, role, from_account):
        """Grant a role to an address"""
        contract = self.get_contract("RBAC")
        role_num = config.ROLES[role] if isinstance(role, str) else role
        
        print(f"\n👤 Granting {config.get_role_name(role_num)} role to {address}")
        
        tx = contract.functions.grantRole(address, role_num)
        return self.send_transaction(tx, from_account)
    
    def get_role(self, address):
        """Get role of an address"""
        contract = self.get_contract("RBAC")
        role_num = contract.functions.getRole(address).call()
        role_name = config.get_role_name(role_num)
        print(f"   {address}: {role_name}")
        return role_num
    
    def has_role(self, address, role):
        """Check if address has a specific role"""
        contract = self.get_contract("RBAC")
        role_num = config.ROLES[role] if isinstance(role, str) else role
        return contract.functions.hasRoleBit(address, role_num).call()


class ExamInterface(BlockchainInterface):
    """Wrapper for ExamLifecycle contract interactions"""
    
    def create_exam(self, name, course_code, exam_date, from_account):
        """Create a new exam"""
        contract = self.get_contract("ExamLifecycle")
        
        print(f"\n📝 Creating exam: {name} ({course_code})")
        
        tx = contract.functions.createExam(name, course_code, exam_date)
        receipt = self.send_transaction(tx, from_account)
        
        if receipt:
            print(f"   ✅ Exam created successfully")
        
        return receipt
    
    def enroll_student(self, exam_id, student_address, from_account):
        """Enroll a student in an exam"""
        contract = self.get_contract("ExamLifecycle")
        
        print(f"\n👨‍🎓 Enrolling student {student_address} in exam {exam_id}")
        
        tx = contract.functions.enrollStudent(exam_id, student_address)
        return self.send_transaction(tx, from_account)
    
    def update_exam_state(self, exam_id, new_state, from_account):
        """Update exam state"""
        contract = self.get_contract("ExamLifecycle")
        state_num = config.EXAM_STATES[new_state] if isinstance(new_state, str) else new_state
        state_name = config.get_exam_state_name(state_num)
        
        print(f"\n🔄 Updating exam {exam_id} state to: {state_name}")
        
        tx = contract.functions.updateExamState(exam_id, state_num)
        return self.send_transaction(tx, from_account)
    
    def get_exam_details(self, exam_id):
        """Get exam details"""
        contract = self.get_contract("ExamLifecycle")
        details = contract.functions.getExamDetails(exam_id).call()
        
        print(f"\n📋 Exam {exam_id} Details:")
        print(f"   Name: {details[1]}")
        print(f"   Course: {details[2]}")
        print(f"   State: {config.get_exam_state_name(details[4])}")
        
        return details


class HashRegistryInterface(BlockchainInterface):
    """Wrapper for HashRegistry contract interactions"""
    
    def register_script(self, exam_id, student_address, student_name,
                       student_id, course_code, from_account):
        """Register a script from topsheet"""
        contract = self.get_contract("HashRegistry")
        
        print(f"\n📄 Registering script for {student_name} ({student_id})")
        
        tx = contract.functions.registerScriptFromTopsheet(
            exam_id, student_address, student_name, student_id, course_code
        )
        return self.send_transaction(tx, from_account)
    
    def get_anonymous_details(self, script_id):
        """Get anonymous script details"""
        contract = self.get_contract("HashRegistry")
        details = contract.functions.getAnonymousScriptDetails(script_id).call()
        
        print(f"\n🎭 Anonymous details for {script_id}:")
        print(f"   Exam ID: {details[0]}")
        print(f"   Hash: {details[1][:20]}...")
        
        return details
    
    def reveal_student(self, script_id, from_account):
        """Reveal student identity (admin only)"""
        contract = self.get_contract("HashRegistry")
        details = contract.functions.revealStudent(script_id).call({'from': from_account})
        
        print(f"\n👤 Revealed identity for {script_id}:")
        print(f"   Student: {details[1]}")
        print(f"   ID: {details[2]}")
        print(f"   Course: {details[3]}")
        
        return details


class ResultAuditInterface(BlockchainInterface):
    """Wrapper for ResultAudit contract interactions"""
    
    def submit_marks(self, script_id, marks_obtained, total_marks=50, from_account=None):
        """Submit marks for a script"""
        contract = self.get_contract("ResultAudit")
        
        print(f"\n📊 Submitting marks for {script_id}: {marks_obtained}/50")
        
        tx = contract.functions.submitMarks(script_id, marks_obtained)
        return self.send_transaction(tx, from_account)
    
    def submit_scrutiny(self, script_id, new_marks, reason, from_account):
        """Submit scrutiny update"""
        contract = self.get_contract("ResultAudit")
        
        print(f"\n🔍 Scrutiny for {script_id}: {new_marks}")
        print(f"   Reason: {reason}")
        
        tx = contract.functions.submitScrutiny(script_id, new_marks, reason)
        return self.send_transaction(tx, from_account)
    
    def finalize_results(self, exam_id, from_account):
        """Finalize exam results"""
        contract = self.get_contract("ResultAudit")
        
        print(f"\n✅ Finalizing results for exam {exam_id}")
        
        tx = contract.functions.finalizeExamResults(exam_id)
        return self.send_transaction(tx, from_account)
    
    def get_marks(self, script_id):
        """Get marks for a script"""
        contract = self.get_contract("ResultAudit")
        marks = contract.functions.getMarks(script_id).call()
        
        print(f"\n📈 Marks for {script_id}:")
        print(f"   Obtained: {marks[0]}/{marks[1]}")
        print(f"   Status: {config.get_grade_status_name(marks[2])}")
        
        return marks
    
    def get_audit_trail(self, script_id, from_account):
        """Get complete audit trail"""
        contract = self.get_contract("ResultAudit")
        trail = contract.functions.getAuditTrail(script_id).call({'from': from_account})
        
        print(f"\n📜 Audit trail for {script_id}:")
        for i, entry in enumerate(trail):
            print(f"   [{i+1}] {entry[6]}: {entry[1]} → {entry[2]}")
            print(f"       Reason: {entry[4]}")
        
        return trail


if __name__ == "__main__":
    # Test connection
    print("\n" + "="*60)
    print("🔗 BLOCKCHAIN INTERFACE TEST")
    print("="*60)
    
    try:
        # Initialize
        blockchain = BlockchainInterface()
        
        # Get accounts
        blockchain.get_accounts()
        
        print("\n✅ Blockchain interface ready!")
        
    except Exception as e:
        print(f"\n❌ Interface test failed: {e}")