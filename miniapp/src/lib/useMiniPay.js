import { useEffect } from "react";
import { useAccount, useConnect } from "wagmi";

/** Detects MiniPay and auto-connects the injected wallet (MiniPay guideline:
 *  no "Connect Wallet" button). Also auto-connects any injected provider so
 *  the app is testable in a normal browser with MetaMask. */
export function useMiniPay() {
  const { address, isConnected } = useAccount();
  const { connect, connectors } = useConnect();

  const hasProvider = typeof window !== "undefined" && !!window.ethereum;
  const isMiniPay = hasProvider && !!window.ethereum.isMiniPay;

  useEffect(() => {
    if (hasProvider && !isConnected && connectors.length > 0) {
      connect({ connector: connectors[0] });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [hasProvider, isConnected]);

  return { address, isConnected, isMiniPay, hasProvider };
}
