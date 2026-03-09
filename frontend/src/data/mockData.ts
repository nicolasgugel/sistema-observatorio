export interface Product {
  id: string;
  sku: string;
  name: string;
  category: string;
  currentPrice: number;
  cost: number;
  margin: number;
  competitors: CompetitorPrice[];
  lastUpdated: string;
  status: "active" | "paused" | "scheduled";
}

export interface CompetitorPrice {
  competitor: string;
  price: number;
  diff: number; // percentage difference vs our price
  lastSeen: string;
}

export interface PriceUpdate {
  id: string;
  productId: string;
  productName: string;
  oldPrice: number;
  newPrice: number;
  reason: string;
  scheduledAt: string | null;
  appliedAt: string | null;
  status: "pending" | "applied" | "scheduled" | "cancelled";
  createdBy: string;
}

export interface KPI {
  label: string;
  value: string;
  change: number;
  trend: "up" | "down" | "neutral";
}

const competitors = ["Liverpool", "Palacio de Hierro", "El Puerto", "Amazon MX", "Mercado Libre"];

export const products: Product[] = [
  {
    id: "1", sku: "SB-BLZ-001", name: "Blazer Italiano Slim Fit", category: "Sacos",
    currentPrice: 8499, cost: 3200, margin: 62.3,
    competitors: [
      { competitor: "Liverpool", price: 8999, diff: 5.9, lastSeen: "2026-03-01" },
      { competitor: "Palacio de Hierro", price: 9250, diff: 8.8, lastSeen: "2026-03-01" },
      { competitor: "Amazon MX", price: 7899, diff: -7.1, lastSeen: "2026-02-28" },
    ],
    lastUpdated: "2026-03-01", status: "active",
  },
  {
    id: "2", sku: "SB-CAM-012", name: "Camisa Oxford Premium", category: "Camisas",
    currentPrice: 2299, cost: 680, margin: 70.4,
    competitors: [
      { competitor: "Liverpool", price: 2199, diff: -4.3, lastSeen: "2026-03-01" },
      { competitor: "El Puerto", price: 2450, diff: 6.6, lastSeen: "2026-02-27" },
      { competitor: "Mercado Libre", price: 1999, diff: -13.0, lastSeen: "2026-03-02" },
    ],
    lastUpdated: "2026-03-02", status: "active",
  },
  {
    id: "3", sku: "SB-ZAP-005", name: "Zapato Derby Piel", category: "Calzado",
    currentPrice: 5699, cost: 2100, margin: 63.2,
    competitors: [
      { competitor: "Palacio de Hierro", price: 6200, diff: 8.8, lastSeen: "2026-03-01" },
      { competitor: "Liverpool", price: 5499, diff: -3.5, lastSeen: "2026-02-28" },
    ],
    lastUpdated: "2026-02-28", status: "active",
  },
  {
    id: "4", sku: "SB-CIN-003", name: "Cinturón Cuero Italiano", category: "Accesorios",
    currentPrice: 1899, cost: 520, margin: 72.6,
    competitors: [
      { competitor: "Amazon MX", price: 1650, diff: -13.1, lastSeen: "2026-03-01" },
      { competitor: "Liverpool", price: 1999, diff: 5.3, lastSeen: "2026-03-02" },
      { competitor: "El Puerto", price: 1850, diff: -2.6, lastSeen: "2026-02-26" },
    ],
    lastUpdated: "2026-03-01", status: "scheduled",
  },
  {
    id: "5", sku: "SB-PAN-008", name: "Pantalón Chino Stretch", category: "Pantalones",
    currentPrice: 2799, cost: 890, margin: 68.2,
    competitors: [
      { competitor: "Liverpool", price: 2699, diff: -3.6, lastSeen: "2026-03-01" },
      { competitor: "Mercado Libre", price: 2399, diff: -14.3, lastSeen: "2026-03-02" },
      { competitor: "Palacio de Hierro", price: 3100, diff: 10.8, lastSeen: "2026-02-28" },
    ],
    lastUpdated: "2026-03-02", status: "active",
  },
  {
    id: "6", sku: "SB-COR-002", name: "Corbata Seda Jacquard", category: "Accesorios",
    currentPrice: 1299, cost: 320, margin: 75.4,
    competitors: [
      { competitor: "Palacio de Hierro", price: 1450, diff: 11.6, lastSeen: "2026-03-01" },
      { competitor: "Liverpool", price: 1199, diff: -7.7, lastSeen: "2026-02-28" },
    ],
    lastUpdated: "2026-02-28", status: "active",
  },
  {
    id: "7", sku: "SB-TRJ-001", name: "Traje Completo Lana Fría", category: "Sacos",
    currentPrice: 15999, cost: 5800, margin: 63.8,
    competitors: [
      { competitor: "Palacio de Hierro", price: 17500, diff: 9.4, lastSeen: "2026-03-01" },
      { competitor: "Liverpool", price: 14999, diff: -6.3, lastSeen: "2026-03-02" },
      { competitor: "Amazon MX", price: 13499, diff: -15.6, lastSeen: "2026-02-27" },
    ],
    lastUpdated: "2026-03-01", status: "active",
  },
  {
    id: "8", sku: "SB-POL-006", name: "Polo Piqué Algodón Egipcio", category: "Camisas",
    currentPrice: 1699, cost: 480, margin: 71.7,
    competitors: [
      { competitor: "Liverpool", price: 1599, diff: -5.9, lastSeen: "2026-03-01" },
      { competitor: "El Puerto", price: 1750, diff: 3.0, lastSeen: "2026-02-28" },
    ],
    lastUpdated: "2026-02-28", status: "paused",
  },
];

export const priceUpdates: PriceUpdate[] = [
  { id: "u1", productId: "2", productName: "Camisa Oxford Premium", oldPrice: 2399, newPrice: 2299, reason: "Competitividad vs Liverpool", scheduledAt: null, appliedAt: "2026-03-01T10:30:00", status: "applied", createdBy: "Ana García" },
  { id: "u2", productId: "4", productName: "Cinturón Cuero Italiano", oldPrice: 1899, newPrice: 1799, reason: "Match Amazon MX", scheduledAt: "2026-03-05T08:00:00", appliedAt: null, status: "scheduled", createdBy: "Carlos López" },
  { id: "u3", productId: "5", productName: "Pantalón Chino Stretch", oldPrice: 2799, newPrice: 2599, reason: "Promoción temporada", scheduledAt: "2026-03-10T00:00:00", appliedAt: null, status: "pending", createdBy: "Ana García" },
  { id: "u4", productId: "1", productName: "Blazer Italiano Slim Fit", oldPrice: 8299, newPrice: 8499, reason: "Ajuste margen", scheduledAt: null, appliedAt: "2026-02-25T14:00:00", status: "applied", createdBy: "Roberto Sánchez" },
  { id: "u5", productId: "7", productName: "Traje Completo Lana Fría", oldPrice: 15999, newPrice: 14999, reason: "Liquidación inventario", scheduledAt: null, appliedAt: null, status: "cancelled", createdBy: "Carlos López" },
];

export const kpis: KPI[] = [
  { label: "Precio Promedio", value: "$5,024", change: 2.3, trend: "up" },
  { label: "Margen Promedio", value: "68.5%", change: 1.1, trend: "up" },
  { label: "Productos Monitoreados", value: "8", change: 0, trend: "neutral" },
  { label: "Alertas Competencia", value: "5", change: -12, trend: "down" },
];

export const categoryData = [
  { category: "Sacos", avgPrice: 12249, avgMargin: 63, products: 2 },
  { category: "Camisas", avgPrice: 1999, avgMargin: 71, products: 2 },
  { category: "Calzado", avgPrice: 5699, avgMargin: 63.2, products: 1 },
  { category: "Accesorios", avgPrice: 1599, avgMargin: 74, products: 2 },
  { category: "Pantalones", avgPrice: 2799, avgMargin: 68.2, products: 1 },
];

export const priceHistoryData = [
  { month: "Oct", santander: 4800, liverpool: 4950, palacio: 5200, amazon: 4500 },
  { month: "Nov", santander: 4750, liverpool: 4900, palacio: 5100, amazon: 4400 },
  { month: "Dic", santander: 4600, liverpool: 4700, palacio: 4900, amazon: 4200 },
  { month: "Ene", santander: 4900, liverpool: 5000, palacio: 5300, amazon: 4600 },
  { month: "Feb", santander: 5024, liverpool: 4980, palacio: 5400, amazon: 4550 },
  { month: "Mar", santander: 5024, liverpool: 5050, palacio: 5350, amazon: 4650 },
];
