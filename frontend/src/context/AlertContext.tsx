import { createContext, useContext, useState, ReactNode } from "react";

interface AlertContextValue {
  alertCount: number;
  setAlertCount: (n: number) => void;
}

const AlertContext = createContext<AlertContextValue>({ alertCount: 0, setAlertCount: () => {} });

export function AlertProvider({ children }: { children: ReactNode }) {
  const [alertCount, setAlertCount] = useState(0);
  return <AlertContext.Provider value={{ alertCount, setAlertCount }}>{children}</AlertContext.Provider>;
}

export function useAlertCount() {
  return useContext(AlertContext);
}
