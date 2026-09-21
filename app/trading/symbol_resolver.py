from __future__ import annotations

import re
from dataclasses import dataclass

_COMPACT_RE = re.compile(r"[^A-Z0-9]")
_SUFFIXES = frozenset(
    {
        "MICRO",
        "MINI",
        "CASH",
        "SPOT",
        "CENT",
        "PLUS",
        "PRO",
        "ECN",
        "RAW",
        "VIP",
        "STD",
        "SB",
        "FX",
        "M",
        "I",
        "C",
        "R",
        "P",
        "Z",
        "S",
        "E",
    }
)
_PRICE_TOLERANCE = 0.25
_TRADE_MODE_DISABLED = 0


@dataclass(frozen=True)
class BrokerSymbol:
    name: str
    description: str = ""
    path: str = ""
    visible: bool = True
    trade_mode: int = 4
    bid: float | None = None
    ask: float | None = None

    @property
    def mid(self) -> float | None:
        if self.bid and self.ask:
            return (self.bid + self.ask) / 2
        return self.bid or self.ask


@dataclass(frozen=True)
class Instrument:
    canonical: str
    aliases: tuple[str, ...]
    roots: tuple[str, ...]


@dataclass(frozen=True)
class SymbolResolution:
    instrument: str
    broker_symbol: str


INSTRUMENTS: tuple[Instrument, ...] = (
    Instrument("XAUUSD", ("GOLD", "XAU", "XAUUSD", "GOLDUSD"), ("XAUUSD", "GOLD")),
    Instrument("XAGUSD", ("SILVER", "XAG", "XAGUSD", "SILVERUSD"), ("XAGUSD", "SILVER")),
    Instrument("EURUSD", ("EURUSD",), ("EURUSD",)),
    Instrument("GBPUSD", ("GBPUSD",), ("GBPUSD",)),
    Instrument("USDJPY", ("USDJPY",), ("USDJPY",)),
    Instrument("USDCHF", ("USDCHF",), ("USDCHF",)),
    Instrument("AUDUSD", ("AUDUSD",), ("AUDUSD",)),
    Instrument("NZDUSD", ("NZDUSD",), ("NZDUSD",)),
    Instrument("USDCAD", ("USDCAD",), ("USDCAD",)),
    Instrument("EURGBP", ("EURGBP",), ("EURGBP",)),
    Instrument("EURJPY", ("EURJPY",), ("EURJPY",)),
    Instrument("GBPJPY", ("GBPJPY",), ("GBPJPY",)),
    Instrument(
        "NAS100",
        ("NAS100", "NASDAQ", "NASDAQ100", "US100", "USTEC", "USTECH", "NDX"),
        ("NAS100", "NASDAQ", "US100", "USTEC", "USTECH", "NDX"),
    ),
    Instrument(
        "US30",
        ("US30", "DJ30", "DOW", "WS30", "DJIA"),
        ("US30", "DJ30", "WS30", "DJIA", "DOW"),
    ),
    Instrument(
        "US500",
        ("US500", "SPX500", "SP500", "SPX"),
        ("US500", "SPX500", "SP500", "SPX"),
    ),
    Instrument(
        "GER40",
        ("GER40", "DE40", "DAX", "GER30", "DE30", "GDAXI"),
        ("GER40", "DE40", "DAX", "GER30", "DE30", "GDAXI"),
    ),
    Instrument("UK100", ("UK100", "FTSE"), ("UK100", "FTSE")),
    Instrument(
        "JP225",
        ("JP225", "JPN225", "NI225", "NKD"),
        ("JP225", "JPN225", "NI225", "NKD"),
    ),
    Instrument(
        "USOIL",
        ("USOIL", "WTI", "XTIUSD", "USOILCASH"),
        ("USOIL", "WTI", "XTIUSD"),
    ),
    Instrument(
        "UKOIL",
        ("UKOIL", "BRENT", "XBRUSD"),
        ("UKOIL", "BRENT", "XBRUSD"),
    ),
    Instrument("BTCUSD", ("BTC", "BTCUSD", "BITCOIN"), ("BTCUSD", "BITCOIN")),
    Instrument("ETHUSD", ("ETH", "ETHUSD", "ETHEREUM"), ("ETHUSD", "ETHEREUM")),
)


def compact_symbol(name: str) -> str:
    return _COMPACT_RE.sub("", name.upper())


def find_instrument(token: str | None) -> Instrument | None:
    if not token:
        return None
    key = compact_symbol(token)
    for instrument in INSTRUMENTS:
        names = {compact_symbol(instrument.canonical)}
        names.update(compact_symbol(alias) for alias in instrument.aliases)
        if key in names:
            return instrument
    return None


def family_names(token: str | None) -> set[str]:
    if not token:
        return set()
    instrument = find_instrument(token)
    if instrument is None:
        return {token.upper()}
    names = {instrument.canonical, *instrument.aliases}
    return {item.upper() for item in names}


def symbol_allowed(
    normalized: str | None,
    broker_symbol: str | None,
    allowed_symbols: list[str],
) -> bool:
    allowed = {item.upper() for item in allowed_symbols}
    if not allowed:
        return bool(normalized or broker_symbol)
    names = family_names(normalized)
    names.update(family_names(broker_symbol))
    if broker_symbol:
        names.add(broker_symbol.upper())
    if normalized:
        names.add(normalized.upper())
    return bool(names & allowed)


def resolve_broker_symbol(
    raw_symbol: str | None,
    normalized_symbol: str | None,
    catalog: list[BrokerSymbol],
    *,
    price_hint: float | None = None,
) -> SymbolResolution | None:
    instrument = find_instrument(raw_symbol) or find_instrument(normalized_symbol)
    if instrument is None:
        needle = normalized_symbol or raw_symbol
        if not needle:
            return None
        key = compact_symbol(needle)
        instrument = Instrument(key, (key,), (key,))
    pool = [
        item
        for item in catalog
        if item.trade_mode != _TRADE_MODE_DISABLED and _name_root(item.name, instrument) is not None
    ]
    if not pool:
        return None
    quoted = [item for item in pool if item.mid]
    if price_hint and quoted:
        close = [
            item
            for item in quoted
            if abs(item.mid - price_hint) / max(abs(price_hint), 1e-9) <= _PRICE_TOLERANCE
        ]
        if not close:
            return None
        pool = close
    chosen = max(pool, key=lambda item: _rank(item, instrument))
    return SymbolResolution(instrument=instrument.canonical, broker_symbol=chosen.name)


def _name_root(name: str, instrument: Instrument) -> str | None:
    compact = compact_symbol(name)
    roots = sorted((compact_symbol(root) for root in instrument.roots), key=len, reverse=True)
    for root in roots:
        if compact == root:
            return root
        if compact.startswith(root) and compact[len(root) :] in _SUFFIXES:
            return root
    return None


def _rank(item: BrokerSymbol, instrument: Instrument) -> tuple[bool, bool, bool, bool, int, str]:
    name = compact_symbol(item.name)
    root = _name_root(item.name, instrument) or ""
    canonical = compact_symbol(instrument.canonical)
    return (
        name == canonical,
        root == canonical,
        item.visible,
        item.trade_mode == 4,
        -len(name),
        name,
    )
