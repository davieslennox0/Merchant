import { http, createConfig } from "wagmi";
import { celoSepolia } from "wagmi/chains";
import { injected } from "wagmi/connectors";

// Canonical cUSD (Mento Dollar) on Celo Sepolia — verified on-chain:
// symbol() == "cUSD", decimals() == 18.
// https://docs.celo.org/contracts/token-contracts
export const CUSD_TESTNET = "0xEF4d55D6dE8e8d73232827Cd1e9b2F2dBb45bC80";

// Celo Agentic Payments & DeFAI hackathon attribution tag, assigned at
// registration and locked to github.com/davieslennox0/Merchant.
export const ATTRIBUTION_TAG = "celo_64d533d628d1";

export const CHAIN = celoSepolia;

export const config = createConfig({
  chains: [celoSepolia],
  connectors: [injected()],
  transports: {
    [celoSepolia.id]: http("https://forno.celo-sepolia.celo-testnet.org"),
  },
});
