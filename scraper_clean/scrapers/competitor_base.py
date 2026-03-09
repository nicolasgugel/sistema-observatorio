"""
Base class para scrapers de competidores (product-driven).

Flujo:
1. Recibe `targets` — lista de productos únicos de Santander Boutique
   (model, capacity_gb, product_code, brand, device_type, product_family)
2. Scraping por categoría en el competidor
3. Fuzzy-match contra los targets
4. Devuelve list[PriceRow] sólo para productos encontrados
"""
from __future__ import annotations
import re
from datetime import datetime, timezone
from typing import Optional

from rapidfuzz import fuzz

from models.price_row import PriceRow

# Palabras clave que identifican el tier/variante del modelo.
# Si difieren entre el producto del retailer y el target, se aplica penalización.
_TIER_KEYWORDS = frozenset({
    "pro", "max", "plus", "air", "ultra", "mini", "lite",
    "fe", "fold", "flip", "e",
})


class CompetitorBase:
    SOURCE_NAME = ""   # slug del competidor, e.g. "grover"
    RETAILER = ""      # nombre legible, e.g. "Grover"
    DATA_QUALITY_TIER = ""  # e.g. "grover_adapter_live"

    def __init__(self, targets: list[dict]):
        """
        targets: lista de dicts con keys:
          model, capacity_gb, product_code, brand, device_type, product_family
        Cada entrada es un producto ÚNICO de Santander (sin duplicar offer_type).
        """
        self.targets = targets

    async def scrape(self) -> list[PriceRow]:
        raise NotImplementedError

    # ------------------------------------------------------------------ #
    # Matching                                                             #
    # ------------------------------------------------------------------ #

    def _match_target(
        self,
        name: str,
        capacity_gb: Optional[int],
        threshold: int = 72,
        strict_variant: bool = False,
    ) -> Optional[dict]:
        """
        Busca el target de Santander que mejor se corresponde con el producto
        del competidor (name + capacity_gb).

        Estrategia:
        1. Filtrar por capacity_gb (si está disponible en ambos)
        2. Fuzzy match por nombre normalizado
        3. Retorna el target con mayor score si supera el threshold

        strict_variant=True:
        - Exige coincidencia exacta de serie (numeros) si ambos la tienen.
        - Exige coincidencia exacta de tier (pro/max/plus/...).
        """
        name_norm = self._normalize(name)
        name_numbers = self._extract_model_numbers(name_norm)
        name_tiers = frozenset(t for t in name_norm.split() if t in _TIER_KEYWORDS)
        name_series = self._extract_galaxy_series(name_norm)
        best_score = 0
        best_target = None

        for target in self.targets:
            t_cap = target.get("capacity_gb")

            # Filtro estricto de capacidad si ambos tienen valor
            if capacity_gb and t_cap:
                if int(capacity_gb) != int(t_cap):
                    continue

            target_norm = self._normalize(target["model"])
            score = fuzz.token_set_ratio(name_norm, target_norm)

            # Penalizar si los números del modelo difieren (ej. iPhone 17 vs 16)
            t_numbers = self._extract_model_numbers(target_norm)
            t_tiers = frozenset(t for t in target_norm.split() if t in _TIER_KEYWORDS)
            t_series = self._extract_galaxy_series(target_norm)

            if strict_variant:
                # En modo estricto descartamos cruces entre series/tier.
                if name_numbers and t_numbers and name_numbers != t_numbers:
                    continue
                if name_tiers != t_tiers:
                    continue
                if name_series and t_series and name_series != t_series:
                    continue
            else:
                # Penalizar cruces de serie (ej. iPhone 17 vs 16).
                if name_numbers and t_numbers and name_numbers != t_numbers:
                    score = max(0, score - 50)
                # Penalizar cruces de tier (Pro/Max/Plus/Air/Ultra).
                if name_tiers != t_tiers:
                    score = max(0, score - 30)
                if name_series and t_series and name_series != t_series:
                    score = max(0, score - 40)

            if score > best_score:
                best_score = score
                best_target = target

        if best_score >= threshold:
            return best_target
        return None

    # ------------------------------------------------------------------ #
    # Helpers de DOM (Scrapling 0.4 — Selector no tiene css_first)        #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _css_first(el, selector: str):
        """Equivalente a css_first: devuelve el primer match de CSS o None."""
        results = el.css(selector)
        return results[0] if results else None

    @staticmethod
    def _el_text(el) -> str:
        """Devuelve el texto de un elemento o cadena vacía si es None."""
        return el.text.strip() if el is not None else ""

    @staticmethod
    def _el_attr(el, attr: str, default: str = "") -> str:
        """Devuelve el atributo de un elemento o default si es None."""
        if el is None:
            return default
        return el.attrib.get(attr, default)

    # ------------------------------------------------------------------ #
    # Helpers de normalización                                             #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _normalize(name: str) -> str:
        """Normaliza un nombre de producto para comparación fuzzy."""
        name = name.lower()
        # Eliminar marca inicial
        name = re.sub(r"^(apple|samsung)\s+", "", name)
        # Eliminar especificaciones de almacenamiento (se comparan por separado)
        name = re.sub(r"\d+\s*(gb|tb)", "", name, flags=re.I)
        # Normalizar variantes compactas de modelo (S26+ -> S26 plus, 16e -> 16 e)
        name = name.replace("+", " plus ")
        name = re.sub(r"\b(\d+)e\b", r"\1 e", name)
        # Separar sufijos numéricos pegados a variante: Flip7→Flip 7, Fold7→Fold 7
        name = re.sub(r"\b(flip|fold)(\d)", r"\1 \2", name)
        # Eliminar comillas tipográficas y caracteres especiales
        name = re.sub(r'["\u2011\u2019\u2018\u2032\u2033\'"″′]+', "", name)
        # Normalizar puntuación y espacios
        name = re.sub(r"[-_/]+", " ", name)
        name = re.sub(r"\s+", " ", name).strip()
        return name

    @staticmethod
    def _extract_galaxy_series(name: str) -> Optional[str]:
        """
        Detecta la familia Samsung Galaxy cuando aparece en el nombre:
        - a26 -> 'a'
        - s25 ultra -> 's'
        - z fold -> 'z'
        """
        m = re.search(r"\bgalaxy\s+([asz])\s*\d{1,2}\b", name)
        if not m:
            m = re.search(r"\b([asz])\s*\d{1,2}\b", name)
        return m.group(1) if m else None

    @staticmethod
    def _extract_model_numbers(name: str) -> frozenset[str]:
        """
        Extrae tokens numericos relevantes del modelo.
        Ignora el '5' de '5g' para no romper matching entre
        nombres que incluyen u omiten el sufijo de red.
        """
        numbers = re.findall(r"\d+", name)
        if re.search(r"\b5g\b", name):
            numbers = [n for n in numbers if n != "5"]
        return frozenset(numbers)

    @staticmethod
    def _parse_capacity(text: str) -> Optional[int]:
        """Extrae la capacidad en GB de un texto (p.ej. '256 GB', '1 TB').

        Toma el valor MÁS GRANDE para evitar confundir RAM con almacenamiento
        cuando el título incluye ambos (ej. '128 GB, 6 GB RAM' → 128).
        """
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
        """
        Extrae precio numérico de texto:
        - '1.299,00 €' → 1299.0
        - '29,99/mes' → 29.99
        - '€1299' → 1299.0
        """
        if not text:
            return None
        text = str(text).strip()
        # Quitar símbolo de moneda y texto no numérico al final
        text = re.sub(r"[€$£\s/mes/mo]+", "", text, flags=re.I)
        # Formato europeo: 1.299,00 → 1299.00
        if re.search(r"\d\.\d{3},\d", text):
            text = text.replace(".", "").replace(",", ".")
        elif "," in text and "." not in text:
            text = text.replace(",", ".")
        elif "," in text and "." in text:
            # Puede ser 1,299.00 (US) o 1.299,00 (EU) → ya manejado arriba
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
        """Construye un PriceRow a partir de un target y los datos del competidor."""
        is_monthly = offer_type in ("renting_no_insurance", "renting_with_insurance", "financing_max_term")
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
