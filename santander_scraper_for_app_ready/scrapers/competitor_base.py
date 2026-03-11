"""
Base class para scrapers de competidores (product-driven).

Flujo:
1. Recibe `targets` - lista de productos unicos de Santander Boutique
   (model, capacity_gb, product_code, brand, device_type, product_family)
2. Scraping por categoria en el competidor
3. Fuzzy-match contra los targets
4. Devuelve list[PriceRow] solo para productos encontrados
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Optional

from rapidfuzz import fuzz

from models.price_row import PriceRow

_TIER_KEYWORDS = frozenset({
    "pro", "max", "plus", "air", "ultra", "mini", "lite",
    "fe", "fold", "flip", "e", "edge",
})

_ACCESSORY_KEYWORDS = (
    "funda", "carcasa", "cover", "case",
    "hub", "dock",
    "cable",
    "cargador", "charger",
    "soporte", "stand",
    "correa", "band",
    "auriculares", "earbuds", "earphone", "headphone",
    "templado", "screen protector",
    "protector",
)


class CompetitorBase:
    SOURCE_NAME = ""
    RETAILER = ""
    DATA_QUALITY_TIER = ""

    def __init__(self, targets: list[dict]):
        self.targets = targets

    async def scrape(self) -> list[PriceRow]:
        raise NotImplementedError

    # ------------------------------------------------------------------ #
    # Matching                                                           #
    # ------------------------------------------------------------------ #

    def _match_target(
        self,
        name: str,
        capacity_gb: Optional[int],
        threshold: int = 72,
        strict_variant: bool = False,
    ) -> Optional[dict]:
        name_norm = self._normalize(name)
        name_numbers = self._extract_model_numbers(name_norm)
        name_tiers = frozenset(t for t in name_norm.split() if t in _TIER_KEYWORDS)
        name_series = self._extract_galaxy_series(name_norm)
        name_silicon = self._extract_apple_silicon_signature(name)
        best_score = 0
        best_target = None

        for target in self.targets:
            t_cap = target.get("capacity_gb")
            if capacity_gb and t_cap and int(capacity_gb) != int(t_cap):
                continue

            target_norm = self._normalize(target["model"])
            score = fuzz.token_set_ratio(name_norm, target_norm)

            t_numbers = self._extract_model_numbers(target_norm)
            t_tiers = frozenset(t for t in target_norm.split() if t in _TIER_KEYWORDS)
            t_series = self._extract_galaxy_series(target_norm)
            t_silicon = self._extract_apple_silicon_signature(target["model"])

            if strict_variant:
                if name_numbers and t_numbers and name_numbers != t_numbers:
                    continue
                if name_tiers != t_tiers:
                    continue
                if name_series and t_series and name_series != t_series:
                    continue
                if name_silicon and t_silicon and name_silicon != t_silicon:
                    continue
            else:
                if name_numbers and t_numbers and name_numbers != t_numbers:
                    score = max(0, score - 50)
                if name_tiers != t_tiers:
                    score = max(0, score - 30)
                if name_series and t_series and name_series != t_series:
                    score = max(0, score - 40)
                if name_silicon and t_silicon and name_silicon != t_silicon:
                    score = max(0, score - 60)

            if score > best_score:
                best_score = score
                best_target = target

        if best_score >= threshold:
            return best_target
        return None

    # ------------------------------------------------------------------ #
    # DOM helpers                                                        #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _css_first(el, selector: str):
        results = el.css(selector)
        return results[0] if results else None

    @staticmethod
    def _el_text(el) -> str:
        return el.text.strip() if el is not None else ""

    @staticmethod
    def _el_attr(el, attr: str, default: str = "") -> str:
        if el is None:
            return default
        return el.attrib.get(attr, default)

    # ------------------------------------------------------------------ #
    # Normalizacion                                                      #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _is_accessory(name: str) -> bool:
        n = name.lower()
        return any(kw in n for kw in _ACCESSORY_KEYWORDS)

    @staticmethod
    def _strip_noise_numbers(text: str) -> str:
        """
        Elimina numeros que suelen pertenecer a especificaciones de marketing
        y no al identificador del modelo.
        """
        text = re.sub(r"\b20\d{2}\b", "", text)
        text = re.sub(r"\b\d+[-\s]*(?:gpu|cpu|core|n[uú]cleos?)\b", "", text, flags=re.I)
        text = re.sub(r"\b\d+[-\s]*(?:mpx?|mah|hz|w)\b", "", text, flags=re.I)
        text = re.sub(
            r"\b\d+\s*plus\s*(?=(?:ssd|ram|memoria(?:\s+unificada)?)\b)",
            "",
            text,
            flags=re.I,
        )
        text = re.sub(r"\b\d+\s*(?=ssd\b)", "", text, flags=re.I)
        text = re.sub(r"\b\d+\s*(?=ram\b)", "", text, flags=re.I)
        text = re.sub(
            r"\b\d+\s*(?=(?:de\s+)?memoria(?:\s+unificada)?)",
            "",
            text,
            flags=re.I,
        )
        text = re.sub(r"\b\d+\s*a\w*o\w*\b", "", text, flags=re.I)
        text = re.sub(r"\b\d+\s*(?:cm|mm)\b", "", text, flags=re.I)
        return text

    def _score_name_against_target(
        self,
        name: str,
        target: dict,
        capacity_gb: Optional[int] = None,
    ) -> int:
        name_norm = self._normalize(name)
        target_norm = self._normalize(target["model"])
        score = fuzz.token_set_ratio(name_norm, target_norm)
        name_silicon = self._extract_apple_silicon_signature(name)
        target_silicon = self._extract_apple_silicon_signature(target["model"])

        name_numbers = self._extract_model_numbers(self._strip_noise_numbers(name_norm))
        t_numbers = self._extract_model_numbers(self._strip_noise_numbers(target_norm))
        if name_numbers and t_numbers:
            if not t_numbers.issubset(name_numbers):
                score = max(0, score - 50)
            elif name_numbers != t_numbers:
                score = max(0, score - 10)

        name_tiers = frozenset(t for t in name_norm.split() if t in _TIER_KEYWORDS)
        t_tiers = frozenset(t for t in target_norm.split() if t in _TIER_KEYWORDS)
        if name_tiers != t_tiers:
            score = max(0, score - 30)

        name_series = self._extract_galaxy_series(name_norm)
        t_series = self._extract_galaxy_series(target_norm)
        if name_series and t_series and name_series != t_series:
            score = max(0, score - 40)

        if name_silicon and target_silicon and name_silicon != target_silicon:
            score = max(0, score - 60)

        t_cap = target.get("capacity_gb")
        if capacity_gb and t_cap and int(capacity_gb) != int(t_cap):
            score = max(0, score - 30)

        if re.search(r"\b(201\d|202[0-2])\b", name_norm):
            score = max(0, score - 40)

        return score

    @staticmethod
    def _normalize(name: str) -> str:
        name = name.lower()
        name = re.sub(r"^(apple|samsung)\s+", "", name)
        name = re.sub(r"\bgalaxy\s+book\b", "book", name)
        name = re.sub(r"\bwi[\s-]?fi\b", "wifi", name, flags=re.I)
        name = re.sub(r"\bwifi\s*(?:6e|6|7)\b", "wifi", name, flags=re.I)
        name = re.sub(r"\bwifi\s*\+\s*(?:cell(?:ular)?|celular)\b", "wifi cellular", name, flags=re.I)
        name = re.sub(r"\bwifi\s+y\s+redes\s+5g\b", "wifi cellular", name, flags=re.I)
        name = re.sub(r"\+\s*cell\b", " cellular ", name, flags=re.I)
        name = re.sub(r"\bcell\b", " cellular ", name, flags=re.I)
        name = re.sub(r"\bcelular\b", " cellular ", name, flags=re.I)
        name = re.sub(r"\bwifi\b", "wi fi", name, flags=re.I)
        name = re.sub(r"\d+\s*(gb|tb)", "", name, flags=re.I)
        name = re.sub(r"\b([a-z]+\d{1,2})\+", r"\1 plus ", name)
        name = re.sub(r"\b(\d+)e\b", r"\1 e", name)
        name = re.sub(r"\b(flip|fold)(\d)", r"\1 \2", name)
        name = re.sub(r"\bult\b", "ultra", name)
        name = re.sub(r"\b(?:ultra|super|liquid)\s+retina(?:\s+xdr)?\b", "", name, flags=re.I)
        name = re.sub(r"\bpromotion\b", "", name, flags=re.I)
        # Solo retirar referencias a chips Apple, no modelos Samsung Axx.
        name = re.sub(r"\bchip\s+[amn]\d{1,2}(?:\s+\w+)?\b", "", name, flags=re.I)
        name = re.sub(r"\ba\d{2}\s+(?:pro|bionic|max|ultra)\b", "", name, flags=re.I)
        name = re.sub(r"\d+[,.]\d+[-\s]*(?:pulgadas?|pulg|\")?", "", name, flags=re.I)
        name = re.sub(r'["\u2011\u2019\u2018\u2032\u2033\']+', "", name)
        name = re.sub(r"[,;:()\[\]]+", " ", name)
        name = re.sub(r"[-_/]+", " ", name)
        name = re.sub(r"\s+", " ", name).strip()
        return name

    @staticmethod
    def _extract_galaxy_series(name: str) -> Optional[str]:
        m = re.search(r"\bgalaxy\s+([asz])\s*\d{1,2}\b", name)
        if not m:
            m = re.search(r"\b([asz])\s*\d{1,2}\b", name)
        return m.group(1) if m else None

    @staticmethod
    def _extract_apple_silicon_signature(name: str) -> Optional[tuple[str, str]]:
        text = str(name or "").lower()
        if "mac" not in text:
            return None
        m = re.search(r"\b(?:chip\s+)?(m\d{1,2})(?:\s+(pro|max|ultra))?\b", text)
        if not m:
            return None
        generation = m.group(1)
        tier = m.group(2) or "base"
        return generation, tier

    @staticmethod
    def _extract_model_numbers(name: str) -> frozenset[str]:
        token_numbers = re.findall(r"\b[a-z]+(\d+)\b", name)
        standalone_numbers = [n for n in re.findall(r"\b\d+\b", name) if len(n) >= 2]
        numbers = token_numbers + standalone_numbers
        if re.search(r"\b5g\b", name):
            numbers = [n for n in numbers if n != "5"]
        return frozenset(numbers)

    @staticmethod
    def _parse_capacity(text: str) -> Optional[int]:
        if not text:
            return None
        matches = re.findall(r"(\d+)\s*(GB|TB)", text, re.I)
        if not matches:
            return None
        values = [
            (int(v) * 1024 if u.upper() == "TB" else int(v))
            for v, u in matches
        ]
        return max(values)

    @staticmethod
    def _clean_price(text: str) -> Optional[float]:
        if not text:
            return None
        text = str(text).strip()
        text = re.sub(r"[€$£\s/mes/mo]+", "", text, flags=re.I)
        if re.search(r"\d\.\d{3},\d", text):
            text = text.replace(".", "").replace(",", ".")
        elif "," in text and "." not in text:
            text = text.replace(",", ".")
        elif "," in text and "." in text:
            text = text.replace(",", "")
        try:
            return round(float(re.sub(r"[^\d.]", "", text)), 2)
        except (ValueError, TypeError):
            return None

    def _make_row(
        self,
        target: dict,
        offer_type: str,
        price_value: float,
        term_months: Optional[int],
        source_url: str,
        source_title: str = "",
        in_stock: bool = True,
        extra_offer_type: Optional[str] = None,
    ) -> PriceRow:
        is_monthly = offer_type in (
            "renting_no_insurance",
            "renting_with_insurance",
            "financing_max_term",
        )
        price_unit = "EUR/month" if is_monthly else "EUR"

        return PriceRow(
            retailer=self.RETAILER,
            retailer_slug=self.SOURCE_NAME,
            product_family=target.get("product_family", target.get("brand", "")),
            brand=target.get("brand", ""),
            device_type=target.get("device_type", ""),
            model=target.get("model", ""),
            capacity_gb=target.get("capacity_gb"),
            product_code=str(target.get("product_code", "") or ""),
            offer_type=offer_type,
            price_value=price_value,
            price_text=f"{price_value:.2f} EUR",
            price_unit=price_unit,
            term_months=term_months,
            in_stock=in_stock,
            data_quality_tier=self.DATA_QUALITY_TIER,
            extracted_at=datetime.now(timezone.utc).isoformat(),
            source_url=source_url,
            source_title=source_title or target.get("model", ""),
        )
