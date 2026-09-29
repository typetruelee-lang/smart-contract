// solc-js(npm) 로 컴파일 — 네이티브 컴파일러 다운로드가 필요 없다.
import fs from "node:fs";
import path from "node:path";
import solc from "solc";

const src = fs.readFileSync(path.resolve("src/DocumentRegistry.sol"), "utf8");
const input = {
  language: "Solidity",
  sources: { "DocumentRegistry.sol": { content: src } },
  settings: { optimizer: { enabled: true, runs: 200 }, evmVersion: "paris", outputSelection: { "*": { "*": ["abi", "evm.bytecode.object"] } } },
};
const out = JSON.parse(solc.compile(JSON.stringify(input)));
const errors = (out.errors || []).filter((e) => e.severity === "error");
if (errors.length) { console.error(errors.map((e) => e.formattedMessage).join("\n")); process.exit(1); }
const c = out.contracts["DocumentRegistry.sol"].DocumentRegistry;
fs.mkdirSync("artifacts", { recursive: true });
fs.writeFileSync("artifacts/DocumentRegistry.json", JSON.stringify({ contractName: "DocumentRegistry", compiler: solc.version(), abi: c.abi, bytecode: "0x" + c.evm.bytecode.object }, null, 2));
console.log("compiled with", solc.version());
