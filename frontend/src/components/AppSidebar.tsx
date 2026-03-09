import { NavLink, useLocation } from "react-router-dom";
import {
  GitCompareArrows,
  House,
  RefreshCw,
  Table2,
  LayoutDashboard,
  MessageSquare,
  ChevronLeft,
  ChevronRight,
  Moon,
  Sun,
} from "lucide-react";
import { useTheme } from "@/context/ThemeContext";
import santanderLogo from "@/assets/santander-logo.png";
import { useAlertCount } from "@/context/AlertContext";

const navItems = [
  { to: "/", icon: House, label: "Home" },
  { to: "/dashboard", icon: LayoutDashboard, label: "Dashboard" },
  { to: "/observatorio", icon: GitCompareArrows, label: "Observatorio" },
  { to: "/actualizador", icon: RefreshCw, label: "Actualizacion diaria" },
  { to: "/visualizador", icon: Table2, label: "Tabla de Precios" },
  { to: "/agente", icon: MessageSquare, label: "Agente IA" },
];

interface AppSidebarProps {
  collapsed: boolean;
  onToggle: () => void;
}

export default function AppSidebar({ collapsed, onToggle }: AppSidebarProps) {
  const location = useLocation();
  const { theme, setTheme } = useTheme();
  const { alertCount } = useAlertCount();

  return (
    <aside
      className={`fixed inset-y-0 left-0 z-30 flex flex-col bg-sidebar border-r border-sidebar-border transition-all duration-300 ${
        collapsed ? "w-16" : "w-64"
      }`}
    >
      {/* Header / Logo */}
      <div
        className={`flex items-center border-b border-sidebar-border py-5 ${
          collapsed ? "justify-center px-0" : "px-6"
        }`}
      >
        {collapsed ? (
          <svg xmlns="http://www.w3.org/2000/svg" width="32" height="32" viewBox="0 0 64 64" aria-label="Santander">
            <path d="M32.93 3.057c-1.64.782-3.4 3.54-3.4 7.376 0 10.244 11.623 15.236 11.623 24.214 0 0 .037 5.327-2.868 6.445v-2.123c0-6.482-12.59-14.454-12.59-21.57v-2.794c-1.64.782-3.4 3.614-3.4 7.413 0 9.797 11.623 14.23 11.623 24.214 0 0 0 4.172-2.57 5.513.075-.224.075-.484.075-.708 0-.447-.075-.82-.075-.82-.26-4.582-12.182-15.98-12.182-19.558C8.68 33.53 0 38.782 0 45.264 0 53.944 14.23 60.9 31.74 60.9c.112 0 .186.075.298 0C49.732 60.873 64 53.646 64 44.93c0-6.482-8.01-12.033-19.334-14.38.335-.857.335-1.602.335-1.602 0-8.12-12.07-16.02-12.07-23.097z" fill="#EC0000"/>
          </svg>
        ) : (
          <img src={santanderLogo} alt="Santander" className="h-7 w-auto" />
        )}
      </div>

      {/* Nav */}
      <nav className="flex-1 px-2 py-4 space-y-1">
        {navItems.map((item) => {
          const isActive = location.pathname === item.to;
          const showBadge = item.to === "/dashboard" && alertCount > 0;
          return (
            <NavLink
              key={item.to}
              to={item.to}
              title={collapsed ? item.label : undefined}
              className={`sidebar-link ${
                collapsed ? "!px-0 justify-center" : ""
              } ${isActive ? "sidebar-link-active" : "sidebar-link-inactive"}`}
            >
              <span className="relative shrink-0">
                <item.icon className="h-4.5 w-4.5" />
                {showBadge && (
                  <span className="absolute -top-1 -right-1 h-2 w-2 rounded-full bg-destructive animate-pulse" />
                )}
              </span>
              {!collapsed && (
                <span className="flex-1 flex items-center justify-between">
                  {item.label}
                  {showBadge && (
                    <span className="text-[10px] font-bold tabular-nums bg-destructive text-destructive-foreground rounded-full px-1.5 py-0.5 leading-none min-w-[18px] text-center">
                      {alertCount}
                    </span>
                  )}
                </span>
              )}
            </NavLink>
          );
        })}
      </nav>

      {/* Footer */}
      <div className={`border-t border-sidebar-border ${collapsed ? "px-0 py-3 flex justify-center" : "px-4 py-4"}`}>
        <button
          onClick={() => setTheme(theme === "dark" ? "light" : "dark")}
          title={theme === "dark" ? "Cambiar a modo claro" : "Cambiar a modo oscuro"}
          className={`flex items-center gap-2 rounded-lg text-sidebar-foreground/60 hover:text-sidebar-foreground hover:bg-sidebar-accent transition-colors ${
            collapsed ? "h-9 w-9 justify-center" : "w-full px-3 py-2 text-xs"
          }`}
        >
          {theme === "dark" ? <Sun className="h-4 w-4 shrink-0" /> : <Moon className="h-4 w-4 shrink-0" />}
          {!collapsed && <span>{theme === "dark" ? "Modo claro" : "Modo oscuro"}</span>}
        </button>
        {!collapsed && (
          <p className="text-[11px] text-sidebar-muted mt-2 px-3">Santander Boutique (c) 2026</p>
        )}
      </div>

      {/* Botón toggle */}
      <button
        onClick={onToggle}
        className="absolute -right-3 top-1/2 -translate-y-1/2 z-40 flex h-6 w-6 items-center justify-center rounded-full bg-sidebar border border-sidebar-border text-sidebar-foreground hover:bg-sidebar-accent transition-colors"
        title={collapsed ? "Expandir barra lateral" : "Contraer barra lateral"}
      >
        {collapsed ? (
          <ChevronRight className="h-3 w-3" />
        ) : (
          <ChevronLeft className="h-3 w-3" />
        )}
      </button>
    </aside>
  );
}
