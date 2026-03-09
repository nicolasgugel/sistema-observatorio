import { ReactNode, useState } from "react";
import AppSidebar from "./AppSidebar";

export default function AppLayout({ children }: { children: ReactNode }) {
  const [collapsed, setCollapsed] = useState(false);

  return (
    <div className="min-h-screen bg-background">
      <AppSidebar collapsed={collapsed} onToggle={() => setCollapsed(!collapsed)} />
      <main className={`min-h-screen transition-all duration-300 ${collapsed ? "ml-16" : "ml-64"}`}>
        <div className="p-8">
          {children}
        </div>
      </main>
    </div>
  );
}
