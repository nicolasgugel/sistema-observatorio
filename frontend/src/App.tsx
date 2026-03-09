import { ThemeProvider } from "@/context/ThemeContext";
import { Toaster } from "@/components/ui/toaster";
import { Toaster as Sonner } from "@/components/ui/sonner";
import { TooltipProvider } from "@/components/ui/tooltip";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Routes, Route, useLocation } from "react-router-dom";
import AppLayout from "@/components/AppLayout";
import HomePage from "@/pages/HomePage";
import DashboardPage from "@/pages/DashboardPage";
import ComparadorPage from "@/pages/ComparadorPage";
import ActualizadorPage from "@/pages/ActualizadorPage";
import VisualizadorPage from "@/pages/VisualizadorPage";
import AgentePage from "@/pages/AgentePage";
import NotFound from "./pages/NotFound";
import { AlertProvider } from "@/context/AlertContext";

const queryClient = new QueryClient();

function AnimatedRoutes() {
  const location = useLocation();
  return (
    <div key={location.pathname} className="animate-fade-in">
      <Routes location={location}>
        <Route path="/" element={<HomePage />} />
        <Route path="/dashboard" element={<DashboardPage />} />
        <Route path="/observatorio" element={<ComparadorPage />} />
        <Route path="/actualizador" element={<ActualizadorPage />} />
        <Route path="/visualizador" element={<VisualizadorPage />} />
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
            <AppLayout>
              <AnimatedRoutes />
            </AppLayout>
          </BrowserRouter>
        </TooltipProvider>
      </QueryClientProvider>
    </AlertProvider>
  </ThemeProvider>
);

export default App;
