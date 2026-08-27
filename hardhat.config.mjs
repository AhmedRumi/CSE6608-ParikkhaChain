import { defineConfig } from "hardhat/config";
import hardhatEthers from "@nomicfoundation/hardhat-ethers";

const config = defineConfig({
  plugins: [hardhatEthers],
  solidity: {
    // IMPORTANT: keep solc at 0.8.19 (Paris EVM) — do NOT bump to 0.8.20+.
    // solc 0.8.20+ defaults to the Shanghai/Cancun EVM and emits the PUSH0
    // (0x5f) opcode, which Ganache v7.x (EthereumJS) does not support. Any
    // call into such bytecode fails with `invalid opcode` ("missing revert
    // data" in the frontend). 0.8.19 targets the Paris EVM and runs on
    // Ganache at http://127.0.0.1:8545.
    // Optimizer runs is 1 (not 200): Ganache enforces the EIP-170 code-size
    // limit (24576 bytes), and ResultAudit with runs:200 is 24902 bytes and
    // cannot be deployed. runs:1 shrinks it to ~24491 bytes so it fits.
    version: "0.8.19",
    settings: {
      evmVersion: "paris",
      optimizer: { enabled: true, runs: 1 },
    },
  },
  defaultNetwork: "localhost",
  networks: {
    hardhat: {
      type: "edr-simulated",
      chainId: 1337,
    },
    localhost: {
      type: "http",
      chainId: 1337,
      url: "http://127.0.0.1:8545",
    },
  },
  paths: {
    sources: "./contracts",
    tests: "./test",
    cache: "./cache",
    artifacts: "./artifacts",
  },
  mocha: {
    timeout: 20000,
  },
});

export default config;
