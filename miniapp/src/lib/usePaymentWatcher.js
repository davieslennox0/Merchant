import { useEffect, useRef } from "react";
import { erc20Abi, formatUnits } from "viem";
import { usePublicClient, useWatchContractEvent } from "wagmi";
import { TOKENS } from "./wagmi";
import { matchTransferToInvoice } from "./invoices";

const BACKFILL_BLOCKS = 5000n; // ~2.5h of Celo Sepolia blocks
const [CUSD, USDC] = TOKENS;

/** Watches cUSD + USDC Transfer events to the merchant's address and
 *  auto-marks matching pending invoices paid. Also backfills recent blocks on
 *  mount so payments made while the app was closed are still detected. */
export function usePaymentWatcher(address, onSettled) {
  const publicClient = usePublicClient();
  const settledRef = useRef(onSettled);
  settledRef.current = onSettled;

  const handleLogs = (token) => (logs) => {
    for (const log of logs) {
      const amount = Number(formatUnits(log.args.value ?? 0n, token.decimals));
      const settled = matchTransferToInvoice(amount, log.transactionHash, token.symbol);
      if (settled) settledRef.current?.(settled);
    }
  };

  const watcher = (token) => ({
    address: token.address,
    abi: erc20Abi,
    eventName: "Transfer",
    args: address ? { to: address } : undefined,
    enabled: !!address,
    poll: true,
    pollingInterval: 8000,
    onLogs: handleLogs(token),
    onError: () => {}, // free RPC hiccups: next poll retries
  });

  useWatchContractEvent(watcher(CUSD));
  useWatchContractEvent(watcher(USDC));

  useEffect(() => {
    if (!address || !publicClient) return;
    let cancelled = false;
    (async () => {
      try {
        const latest = await publicClient.getBlockNumber();
        const from = latest > BACKFILL_BLOCKS ? latest - BACKFILL_BLOCKS : 0n;
        for (const token of TOKENS) {
          const logs = await publicClient.getContractEvents({
            address: token.address,
            abi: erc20Abi,
            eventName: "Transfer",
            args: { to: address },
            fromBlock: from,
            toBlock: latest,
          });
          if (cancelled) return;
          handleLogs(token)(logs);
        }
      } catch {
        // backfill is best-effort; the live watchers still run
      }
    })();
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [address, publicClient]);
}
