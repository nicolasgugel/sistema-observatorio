import { ReactNode, useState } from "react";
import AppSidebar from "./AppSidebar";
import GlobalAgentLauncher from "./agent/GlobalAgentLauncher";

export default function AppLayout({ children }: { children: ReactNode }) {
  const [collapsed, setCollapsed] = useState(false);

  return (
    <div className="min-h-screen bg-background">
      <AppSidebar collapsed={collapsed} onToggle={() => setCollapsed(!collapsed)} />
      <main className={`min-h-screen transition-all duration-300 ${collapsed ? "ml-16" : "ml-64"}`}>
        <div className="min-h-screen bg-[hsl(var(--ds-surface-container-low))] px-5 py-6 sm:px-8 sm:py-8 lg:px-10">
          {children}
        </div>
      </main>
      <GlobalAgentLauncher />
    </div>
  );
}
