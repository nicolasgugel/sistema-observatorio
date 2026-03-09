import { Brand } from "@/lib/observatorio-api";
import BrandIdentity from "./BrandIdentity";

interface BrandSegmentedControlProps {
  value: Brand;
  onChange: (brand: Brand) => void;
}

const OPTIONS: { value: Brand; label: string }[] = [
  { value: "Samsung", label: "Samsung" },
  { value: "Apple",   label: "Apple" },
];

const OPTION_W = 130; // wide enough for Samsung wordmark (w-14 = 56px) + some padding
const PAD = 4;

export default function BrandSegmentedControl({ value, onChange }: BrandSegmentedControlProps) {
  const activeIndex = OPTIONS.findIndex((o) => o.value === value);

  return (
    <div
      role="group"
      aria-label="Selección de marca"
      style={{
        position: "relative",
        display: "grid",
        gridTemplateColumns: `${OPTION_W}px ${OPTION_W}px`,
        padding: PAD,
        borderRadius: 9999,
        background: "hsl(var(--muted))",
        boxShadow: "inset 0 1px 2px hsl(var(--border) / 0.5)",
        width: OPTION_W * 2 + PAD * 2,
      }}
    >
      {/* Sliding indicator */}
      <span
        aria-hidden
        style={{
          position: "absolute",
          top: PAD,
          bottom: PAD,
          left: activeIndex === 0 ? PAD : PAD + OPTION_W,
          width: OPTION_W,
          borderRadius: 9999,
          background: "hsl(var(--background))",
          boxShadow: "0 1px 5px hsl(var(--foreground) / 0.09), 0 0 0 1px hsl(var(--border) / 0.3)",
          transition: "left 180ms cubic-bezier(0.4, 0, 0.2, 1)",
          pointerEvents: "none",
        }}
      />

      {OPTIONS.map((opt) => {
        const isActive = opt.value === value;
        return (
          <button
            key={opt.value}
            type="button"
            onClick={() => onChange(opt.value)}
            aria-pressed={isActive}
            style={{
              position: "relative",
              zIndex: 1,
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              gap: 8,
              padding: "7px 0",
              border: "none",
              background: "transparent",
              cursor: "pointer",
              userSelect: "none",
              opacity: isActive ? 1 : 0.5,
              transition: "opacity 180ms ease",
            }}
          >
            <BrandIdentity
              brand={opt.value as "Samsung" | "Apple"}
              size="logo_only"
              hideLabel
            />
          </button>
        );
      })}
    </div>
  );
}
