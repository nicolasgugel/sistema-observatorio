import { useEffect, useMemo, useState } from "react";

import appleMark from "@/assets/apple-mark.svg";
import samsungWordmark from "@/assets/samsung-wordmark.svg";
import santanderLogo from "@/assets/santander-logo.png";

const RETAILER_LOGOS: Record<string, string[]> = {
  "Santander Boutique": [santanderLogo],
  Amazon: [],
  "Apple Oficial": [appleMark],
  "Apple Store": [appleMark],
  Movistar: [],
  Rentik: ["https://www.rentik.com/favicon.ico"],
  "Samsung Oficial": [samsungWordmark],
  "Samsung Store": [samsungWordmark],
  "Media Markt": [],
  MediaMarkt: [],
  "El Corte Ingles": [],
  "El Corte Inglés": [],
  Grover: [],
  Qonexa: ["https://qonexa.com/favicon.ico"],
};

const RETAILER_DOMAINS: Record<string, string> = {
  "Santander Boutique": "bancosantander.es",
  Amazon: "amazon.es",
  "Apple Oficial": "apple.com",
  "Apple Store": "apple.com",
  Movistar: "movistar.es",
  Rentik: "rentik.com",
  "Samsung Oficial": "samsung.com",
  "Samsung Store": "samsung.com",
  "Media Markt": "mediamarkt.es",
  MediaMarkt: "mediamarkt.es",
  "El Corte Ingles": "elcorteingles.es",
  "El Corte Inglés": "elcorteingles.es",
  Grover: "grover.com",
  Qonexa: "qonexa.com",
};

interface RetailerLogoProps {
  retailer: string;
  className?: string;
}

export default function RetailerLogo({ retailer, className }: RetailerLogoProps) {
  const candidates = useMemo(() => retailerLogoCandidates(retailer), [retailer]);
  const [index, setIndex] = useState(0);

  useEffect(() => {
    setIndex(0);
  }, [retailer]);

  const src = candidates[index];
  const sizeClass = className ?? "h-5 w-5";

  if (!src) {
    return (
      <span
        className={`logo-surface inline-flex items-center justify-center text-[10px] font-semibold text-muted-foreground ${sizeClass}`}
      >
        {(retailer || "?").slice(0, 1).toUpperCase()}
      </span>
    );
  }

  return (
    <span className={`logo-surface ${sizeClass}`}>
      <img
        src={src}
        alt={retailer}
        className="logo-image h-full w-full object-contain p-1"
        loading="lazy"
        onError={() => {
          setIndex((current) => (current < candidates.length - 1 ? current + 1 : current));
        }}
      />
    </span>
  );
}

function retailerLogoCandidates(retailer: string): string[] {
  const explicit = RETAILER_LOGOS[retailer] ?? [];
  const domain = RETAILER_DOMAINS[retailer];
  const dynamic = domain
    ? [
        `https://icons.duckduckgo.com/ip3/${domain}.ico`,
        `https://www.google.com/s2/favicons?sz=64&domain_url=${encodeURIComponent(`https://${domain}`)}`,
      ]
    : [];
  return Array.from(new Set([...explicit, ...dynamic]));
}
