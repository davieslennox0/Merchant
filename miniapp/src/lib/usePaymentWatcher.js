import { useEffect, useRef } from "react";
import { erc20Abi, formatUnits } from "viem";
import { usePublicClient, useWatchContractEvent } from "wagmi";
import { CUSD_TESTNET } from "./wagmi";
import { matchTransferToInvoice } from "./invoices";

const BACKFILL_BLOCKS = 5000n; // ~2.5h of Celo Sepolia blocks

/** Watches cUSD Transfer events to the merchant's address and auto-marks
 *  matching pending invoices paid. Also backfills recent blocks on mount so
 *  payments made while the app was closed are still detected. */
export function usePaymentWatcher(address, onSettled) {
  const publicClient = usePublicClient();
  const settledRef = useRef(onSettled);
  settledRef.current = onSettled;

  const handleLogs = (logs) => {
    for (const log of logs) {
      const amount = Number(formatUnits(log.args.value ?? 0n, 18));
      const settled = matchTransferToInvoice(amount, log.transactionHash);
      if (settled) settledRef.current?.(settled);
    }
  };

  useWatchContractEvent({
    address: CUSD_TESTNET,
    abi: erc20Abi,
    eventName: "Transfer",
    args: address ? { to: address } : undefined,
    enabled: !!address,
    poll: true,
    pollingInterval: 8000,
    onLogs: handleLogs,
    onError: () => {}, // free RPC hiccups: next poll retries
  });

  useEffect(() => {
    if (!address || !publicClient) return;
    let cancelled = false;
    (async () => {
      try {
        const latest = await publicClient.getBlockNumber();
        const from = latest > BACKFILL_BLOCKS ? latest - BACKFILL_BLOCKS : 0n;
        const logs = await publicClient.getContractEvents({
          address: CUSD_TESTNET,
          abi: erc20Abi,
          eventName: "Transfer",
          args: { to: address },
          fromBlock: from,
          toBlock: latest,
        });
        if (!cancelled) handleLogs(logs);
      } catch {
        // backfill is best-effort; the live watcher still runs
      }
    })();
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [address, publicClient]);
}
