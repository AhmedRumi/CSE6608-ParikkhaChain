/**
 * Auto-deploy script for ParikkhaChain contracts (ESM, Hardhat 3).
 *
 * Deploys the 5 contracts to Ganache (http://127.0.0.1:8545) in dependency
 * order, chains their constructor arguments, wires RBAC -> ResultAudit /
 * Rescrutiny, and writes the fresh addresses into:
 *   - <project>/deployed_addresses.json              (consumed by blockchain scripts)
 *   - <project>/frontend/src/config/deployed_addresses.json (consumed by Vite build)
 *
 * Usage:
 *   npx hardhat run scripts/deploy.js --network localhost
 *
 * NOTE: Ganache must already be running on http://127.0.0.1:8545 with
 * deterministic accounts. If you restarted Ganache, re-grant roles and
 * re-enroll students via the UI after deploy.
 */
import fs from "fs";
import path from "path";
import { fileURLToPath } from "url";
import { network } from "hardhat";
import { ethers } from "ethers";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const PROJECT_ROOT = path.resolve(__dirname, "..");
const FRONTEND_CONFIG_DIR = path.join(PROJECT_ROOT, "frontend", "src", "config");

async function main() {
  // Create a fresh network connection to the selected network
  const connection = await network.connect();
  const { ethers: hhEthers } = connection;

  console.log("\n================ ParikkhaChain — auto-deploy ================\n");

  const [deployer] = await hhEthers.getSigners();
  const balance = await hhEthers.provider.getBalance(deployer.address);
  console.log(`Deployer: ${deployer.address}`);
  console.log(`Balance:  ${ethers.formatEther(balance)} ETH\n`);

  // ── 1. RBAC (no constructor args) ────────────────────────────────
  const RBAC = await hhEthers.getContractFactory("RBAC");
  const rbac = await RBAC.deploy();
  await rbac.waitForDeployment();
  const rbacAddr = await rbac.getAddress();
  console.log(`RBAC deployed:            ${rbacAddr}`);

  // ── 2. ExamLifecycle (constructor: RBAC) ───────────────────────────
  const ExamLifecycle = await hhEthers.getContractFactory("ExamLifecycle");
  const exam = await ExamLifecycle.deploy(rbacAddr);
  await exam.waitForDeployment();
  const examAddr = await exam.getAddress();
  console.log(`ExamLifecycle deployed:   ${examAddr}`);

  // ── 3. HashRegistry (constructor: RBAC, ExamLifecycle) ───────────
  const HashRegistry = await hhEthers.getContractFactory("HashRegistry");
  const hashReg = await HashRegistry.deploy(rbacAddr, examAddr);
  await hashReg.waitForDeployment();
  const hashAddr = await hashReg.getAddress();
  console.log(`HashRegistry deployed:    ${hashAddr}`);

  // ── 4. ResultAudit (constructor: RBAC, ExamLifecycle, HashRegistry) ─
  const ResultAudit = await hhEthers.getContractFactory("ResultAudit");
  const resultAudit = await ResultAudit.deploy(rbacAddr, examAddr, hashAddr);
  await resultAudit.waitForDeployment();
  const resultAddr = await resultAudit.getAddress();
  console.log(`ResultAudit deployed:     ${resultAddr}`);

  // ── 5. Rescrutiny (constructor: RBAC, ExamLifecycle, HashRegistry, ResultAudit) ─
  const Rescrutiny = await hhEthers.getContractFactory("Rescrutiny");
  const rescrutiny = await Rescrutiny.deploy(rbacAddr, examAddr, hashAddr, resultAddr);
  await rescrutiny.waitForDeployment();
  const scrutAddr = await rescrutiny.getAddress();
  console.log(`Rescrutiny deployed:      ${scrutAddr}\n`);

  // ── Wire RBAC whitelists (anonymity + rescrutiny trust) ───────────
  console.log("Linking ResultAudit + Rescrutiny into RBAC...");
  const txRA = await rbac.setResultAudit(resultAddr);
  await txRA.wait();
  console.log(`   ResultAudit whitelisted: ${await rbac.getResultAuditAddress()}`);

  const txRS = await rbac.setRescrutiny(scrutAddr);
  await txRS.wait();
  console.log(`   Rescrutiny whitelisted:  ${await rbac.getRescrutinyAddress()}\n`);

  // ── Save addresses ────────────────────────────────────────────────
  const addresses = {
    RBAC: rbacAddr,
    ExamLifecycle: examAddr,
    HashRegistry: hashAddr,
    ResultAudit: resultAddr,
    Rescrutiny: scrutAddr,
  };

  const rootJson = path.join(PROJECT_ROOT, "deployed_addresses.json");
  fs.writeFileSync(rootJson, JSON.stringify(addresses, null, 2));
  console.log(`Saved root:          ${rootJson}`);

  fs.mkdirSync(FRONTEND_CONFIG_DIR, { recursive: true });
  const frontendJson = path.join(FRONTEND_CONFIG_DIR, "deployed_addresses.json");
  fs.writeFileSync(frontendJson, JSON.stringify(addresses, null, 2));
  console.log(`Saved frontend:      ${frontendJson}\n`);

  console.log("🎉 Deployment complete. Contracts are live.\n" +
              "   Next: grant roles (ADMIN/EXAMINER/SCRUTINIZER/STUDENT) via UI,\n" +
              "   create a term, then a term exam — createTermExam now expects\n" +
              "   (uint256, string, string, uint256, uint256[] sectionTotals).\n");
}

main()
  .then(() => process.exit(0))
  .catch((err) => {
    console.error("❌ Deployment failed:", err);
    process.exit(1);
  });
