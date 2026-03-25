import { ThemeProvider } from "@/context/ThemeContext";
import { Toaster } from "@/components/ui/toaster";
import { Toaster as Sonner } from "@/components/ui/sonner";
import { TooltipProvider } from "@/components/ui/tooltip";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Navigate, Route, Routes, useLocation } from "react-router-dom";
import AppLayout from "@/components/AppLayout";
import { AgentConsoleProvider } from "@/components/agent/AgentConsoleContext";
import HomePage from "@/pages/HomePage";
import DashboardPage from "@/pages/DashboardPage";
import ComparadorPage from "@/pages/ComparadorPage";
import VisualizadorPage from "@/pages/VisualizadorPage";
import SimuladorPage from "@/pages/SimuladorPage";
import AgentePage from "@/pages/AgentePage";
import NotFound from "./pages/NotFound";
import { AlertProvider } from "@/context/AlertContext";

const queryClient = new QueryClient();

function AnimatedRoutes() {
  const location = useLocation();
  return (
    <div key={location.pathname} className="animate-page-enter">
      <Routes location={location}>
        <Route path="/" element={<HomePage />} />
        <Route path="/dashboard" element={<DashboardPage />} />
        <Route path="/observatorio" element={<ComparadorPage />} />
        <Route path="/actualizador" element={<Navigate to="/dashboard" replace />} />
        <Route path="/visualizador" element={<VisualizadorPage />} />
        <Route path="/simulador" element={<SimuladorPage />} />
        <Route path="/agente" element={<AgentePage />} />
        <Route path="*" element={<NotFound />} />
      </Routes>
    </div>
  );
}

const App = () => (
  <ThemeProvider>
    <AlertProvider>
      <QueryClientProvider client={queryClient}>
        <TooltipProvider>
          <Toaster />
          <Sonner />
          <BrowserRouter>
            <AgentConsoleProvider>
              <AppLayout>
                <AnimatedRoutes />
              </AppLayout>
            </AgentConsoleProvider>
          </BrowserRouter>
        </TooltipProvider>
      </QueryClientProvider>
    </AlertProvider>
  </ThemeProvider>
);

export default App;
