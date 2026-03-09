import appleMark from "@/assets/apple-mark.svg";
import samsungWordmark from "@/assets/samsung-wordmark.svg";
import { cn } from "@/lib/utils";

export type AppleSamsungBrand = "Samsung" | "Apple";
type BrandIdentitySize = "default" | "compact" | "logo_only";

const BRAND_META: Record<
  AppleSamsungBrand,
  {
    logo: string;
    alt: string;
    logoWrapClassName: string;
    compactLogoWrapClassName: string;
    logoOnlyWrapClassName: string;
    logoClassName?: string;
  }
> = {
  Samsung: {
    logo: samsungWordmark,
    alt: "Samsung",
    logoWrapClassName: "brand-identity-logo-wrap-samsung",
    compactLogoWrapClassName: "brand-identity-logo-wrap-samsung-compact",
    logoOnlyWrapClassName: "brand-identity-logo-wrap-samsung-logo-only",
  },
  Apple: {
    logo: appleMark,
    alt: "Apple",
    logoWrapClassName: "brand-identity-logo-wrap-apple",
    compactLogoWrapClassName: "brand-identity-logo-wrap-apple-compact",
    logoOnlyWrapClassName: "brand-identity-logo-wrap-apple-logo-only",
    logoClassName: "brand-identity-logo-apple",
  },
};

interface BrandIdentityProps {
  brand: AppleSamsungBrand;
  className?: string;
  labelClassName?: string;
  logoClassName?: string;
  hideLabel?: boolean;
  size?: BrandIdentitySize;
}

export default function BrandIdentity({
  brand,
  className,
  labelClassName,
  logoClassName,
  hideLabel = false,
  size = "default",
}: BrandIdentityProps) {
  const meta = BRAND_META[brand];
  const logoWrapClassName =
    size === "logo_only"
      ? meta.logoOnlyWrapClassName
      : size === "compact"
        ? meta.compactLogoWrapClassName
        : meta.logoWrapClassName;

  return (
    <span className={cn("brand-identity-inline", className)}>
      <span className={cn("brand-identity-logo-wrap", logoWrapClassName)}>
        <img
          src={meta.logo}
          alt={meta.alt}
          className={cn("brand-identity-logo", meta.logoClassName, logoClassName)}
          loading="lazy"
        />
      </span>
      {!hideLabel ? <span className={cn("brand-identity-label", labelClassName)}>{brand}</span> : null}
    </span>
  );
}
