import { network } from "hardhat";
import fs from "fs";
import path from "path";

const connection = await network.connect();
const { ethers: hhEthers } = connection;

const PROJECT_ROOT = path.resolve("./");
const addresses = JSON.parse(
  fs.readFileSync(path.join(PROJECT_ROOT, "deployed_addresses.json"), "utf8")
);

const rbac = await hhEthers.getContractAt("RBAC", addresses.RBAC);

const admin = await rbac.admin();
console.log("RBAC.admin():", admin);

// Check roleBits (bitmask)
const roleBits = await rbac.roleBits(admin);
console.log("roleBits for admin:", Number(roleBits));
console.log("  ADMIN bit (1)?", Number(roleBits) & 1 ? "YES" : "NO");
console.log("  hasRole ADMIN?", await rbac.hasRole(admin, 1));

// The frontend connects via metamask using ganache acc0
// which should be the admin. Let me also check the first few accounts
const accounts = await hhEthers.getSigners();
for (let i = 0; i < 3; i++) {
  const rb = await rbac.roleBits(accounts[i].address);
  console.log(`  [${i}] ${accounts[i].address}: roleBits=${Number(rb)}`);
}
