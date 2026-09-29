// 로컬 개발 체인 전용 설정 (컴파일은 scripts/compile.mjs 사용)
module.exports = {
  solidity: "0.8.24",
  networks: { hardhat: { chainId: 31337, mining: { auto: true } } },
};
