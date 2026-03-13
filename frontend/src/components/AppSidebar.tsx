import { type ReactNode } from "react";
import { NavLink, useLocation } from "react-router-dom";
import {
  Calculator,
  GitCompareArrows,
  House,
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
import { Tooltip, TooltipTrigger, TooltipContent } from "@/components/ui/tooltip";

const navItems = [
  { to: "/", icon: House, label: "Home" },
  { to: "/dashboard", icon: LayoutDashboard, label: "Dashboard" },
  { to: "/observatorio", icon: GitCompareArrows, label: "Observatorio" },
  { to: "/visualizador", icon: Table2, label: "Tabla de Precios" },
  { to: "/simulador", icon: Calculator, label: "Simulador" },
  { to: "/agente", icon: MessageSquare, label: "Agente IA" },
];

function SidebarTooltip({ label, show, children }: { label: string; show: boolean; children: ReactNode }) {
  if (!show) return <>{children}</>;
  return (
    <Tooltip>
      <TooltipTrigger asChild>{children}</TooltipTrigger>
      <TooltipContent side="right">{label}</TooltipContent>
    </Tooltip>
  );
}

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
      className={`fixed inset-y-0 left-0 z-30 flex flex-col border-r border-sidebar-border/95 bg-sidebar shadow-[10px_0_40px_rgba(2,6,23,0.18)] transition-all duration-300 ${
        collapsed ? "w-16" : "w-64"
      }`}
    >
      {/* Header / Logo */}
      <div
        className={`flex items-center border-b border-sidebar-border/90 py-5 ${
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
      <nav className="flex-1 space-y-1.5 px-2.5 py-5">
        {navItems.map((item) => {
          const isActive = location.pathname === item.to;
          const showBadge = item.to === "/dashboard" && alertCount > 0;

          const link = (
            <NavLink
              to={item.to}
              className={`sidebar-link ${
                collapsed ? "!px-0 justify-center" : ""
              } ${isActive ? "sidebar-link-active" : "sidebar-link-inactive"}`}
            >
              <span className="relative shrink-0">
                <item.icon className="h-[18px] w-[18px]" />
                {showBadge && (
                  <span className="absolute -top-1 -right-1 h-2 w-2 rounded-full bg-destructive animate-pulse" />
                )}
              </span>
              {!collapsed && (
                <span className="flex-1 flex items-center justify-between">
                  <span>{item.label}</span>
                  {showBadge && (
                    <span className="tabular-premium rounded-full border border-destructive/20 bg-destructive/12 px-1.5 py-0.5 text-[10px] font-semibold leading-none text-destructive min-w-[20px] text-center">
                      {alertCount}
                    </span>
                  )}
                </span>
              )}
            </NavLink>
          );

          return (
            <SidebarTooltip key={item.to} label={item.label} show={collapsed}>
              {link}
            </SidebarTooltip>
          );
        })}
      </nav>

      {/* Footer */}
      <div className={`border-t border-sidebar-border/90 ${collapsed ? "flex justify-center px-0 py-3" : "px-4 py-4"}`}>
        <SidebarTooltip label={theme === "dark" ? "Cambiar a modo claro" : "Cambiar a modo oscuro"} show={collapsed}>
          <button
            onClick={() => setTheme(theme === "dark" ? "light" : "dark")}
            className={`flex items-center gap-2 rounded-xl text-sidebar-foreground/65 hover:bg-sidebar-accent hover:text-sidebar-foreground transition-colors ${
              collapsed ? "h-9 w-9 justify-center" : "w-full px-3 py-2 text-xs"
            }`}
          >
            {theme === "dark" ? <Sun className="h-4 w-4 shrink-0" /> : <Moon className="h-4 w-4 shrink-0" />}
            {!collapsed && <span>{theme === "dark" ? "Modo claro" : "Modo oscuro"}</span>}
          </button>
        </SidebarTooltip>
        {!collapsed && (
          <p className="mt-2 px-3 text-[11px] uppercase tracking-[0.12em] text-sidebar-muted">Santander Boutique 2026</p>
        )}
      </div>

      {/* Botón toggle */}
      <SidebarTooltip label={collapsed ? "Expandir barra lateral" : "Contraer barra lateral"} show>
        <button
          onClick={onToggle}
          className="absolute -right-3 top-1/2 z-40 flex h-6 w-6 -translate-y-1/2 items-center justify-center rounded-full border border-sidebar-border bg-sidebar text-sidebar-foreground transition-colors hover:bg-sidebar-accent"
        >
          {collapsed ? <ChevronRight className="h-3 w-3" /> : <ChevronLeft className="h-3 w-3" />}
        </button>
      </SidebarTooltip>
    </aside>
  );
}
