import json
import math
from typing import Dict, List, Tuple, Optional
from datamodel import OrderDepth, TradingState, Order, Trade


class Trader:

    TTE_AT_T0_DAYS = 4
    DAYS_PER_YEAR = 252.0

    POSITION_LIMITS = {
        "HYDROGEL_PACK": 200,
        "VELVETFRUIT_EXTRACT": 200,
        "VEV_4000": 300, "VEV_4500": 300, "VEV_5000": 300, "VEV_5100": 300,
        "VEV_5200": 300, "VEV_5300": 300, "VEV_5400": 300, "VEV_5500": 300,
        "VEV_6000": 300, "VEV_6500": 300,
    }

    ACTIVE_STRIKES = [5000, 5100, 5200, 5300, 5400, 5500]

    CP_WEIGHTS = {
        "VELVETFRUIT_EXTRACT": {
            "Mark 01": +2.5,    # smart maker (504 trades, +2.8 PnL/unit)
            "Mark 14": +2.0,    # smart maker (647 trades, +2.3 PnL/unit)
            "Mark 55": -2.0,    # main fish (1198 trades, -2.4 PnL/unit)
            "Mark 49": -1.0,    # small fish (sells only)
            "Mark 67": +1.0,    # directional buyer (small follow)
            "Mark 22": -1.2,    # informed seller / mild fade overlay from teammate evidence
        },     }
    # Per-tick decay of the CP signal. 0.9985 -> half-life ~460 ticks
    # (signal from a single trade fades by ~95% over ~2000 ticks).
    CP_DECAY = 0.9985
    # Hard cap on |cp_signal| per asset. Prevents flurry of fish prints
    # from over-skewing fair beyond what the data supports.
    CP_FAIR_MAX = {
        "VELVETFRUIT_EXTRACT": 5.0,  # smaller asset, smaller cap
    }

    # Small voucher-IV overlay inspired by teammate 506279, but restricted to the
    # core rich strikes only. We intentionally keep amplitudes much smaller than
    # his pooled signal to avoid disturbing the already-working 5400/5500 complex.
    CP_VOUCHER_CORE_STRIKES = {5100, 5200, 5300}
    CP_WEIGHTS_VOUCHER = {
        "Mark 01": +0.0004,
        "Mark 14": +0.0003,
        "Mark 22": +0.0004,
        "Mark 38": -0.0006,
    }
    CP_VOUCHER_DECAY = 0.9985
    CP_VOUCHER_IV_MAX = 0.0012

    # v19: rolling z-score overlay on linear assets. Streaming EMA-based
    # mean/variance estimator (no buffer in memory). When |z| crosses Z_IN
    # we begin to set a mean-reversion target_pos; the magnitude scales
    # linearly to Z_FULL, where it caps at MAX_TARGET (in position units).
    # Z_ALPHA tuned so the EMA's "effective N" approximates the backtest
    # window (1500-2000 ticks).
    # v22: HYDROGEL z-score entry dropped — the new engine has its own
    # anchor/regime logic. VELVETFRUIT z-score overlay unchanged.
    ZSCORE_PARAMS = {
        "VELVETFRUIT_EXTRACT":{"z_alpha": 0.0013, "z_in": 2.0, "z_full": 3.0,
                               "max_target": 80, "warmup": 500},
    }

    # v19: per-strike IV bias applied to BS sigma when computing voucher
    # fair value. NEGATIVE bias = price option lower than market IV-EMA
    # implies = lean SHORT vol. POSITIVE = lean long.
    #
    # SCALE NOTE: this code uses ANNUALIZED IV (sigma per √year) — typical
    # market IVs in the data are 0.21–0.25. So a -0.01 bias = -1% IV shift,
    # which on K=5300 changes BS-fair by ~$1.2 (meaningful).
    #
    # Calibration based on:
    #   - per-strike short-vol carry edge: K=5200/5300 most rich vs realized
    #   - smile residual analysis: K=5400 persistently cheapest (-135 bps in
    #     annualized IV vs the rest of the smile). So 5400 gets near-neutral
    #     bias even though we're "heavy short" elsewhere — it's already cheap.
    # Aggregate stance is "heavy short vol" with K=5400 nearly neutral.
    IV_BIAS = {
        5000: -0.010,
        5100: -0.015,
        5200: -0.018,    # rich
        5300: -0.020,    # richest
        5400: -0.006,    # still short, but less aggressive to improve price capture
        5500: -0.012,    # slightly less aggressive to improve price capture
    }



    # v27: early-fill restraint for the core short-vol strikes that saturate
    # too quickly (5200/5300). The idea is not to reduce final inventory,
    # but to delay the first 150-180 shorts so the average sale price rises.
    # This is inventory-phase based, not timestamp-based, to avoid fragile
    # backtester dependencies.
    PHASED_VOUCHER_AGGR = {
        5200: {"threshold": -180, "bias_relax": 0.004, "take_extra": 0.30,
               "width_extra": 0.45, "mm_mult": 0.72},
        5300: {"threshold": -160, "bias_relax": 0.004, "take_extra": 0.25,
               "width_extra": 0.40, "mm_mult": 0.75},
        # 5500 also saturates very early and almost all fills print at 7.
        # Mild early-phase relaxation aims to preserve the -300 short, but at
        # a slightly better average sale price by not dumping inventory too fast.
        5500: {"threshold": -180, "bias_relax": 0.003, "take_extra": 0.20,
               "width_extra": 0.35, "mm_mult": 0.75},
    }

    # v31: direct price-capture floors for sticky buyers on the richest short-vol
    # strikes. These are NOT fair shifts; they only prevent us from offering too
    # cheaply while inventory is still shallow. Rationale from fills:
    # - 5300 saturates at -300 extremely early with most size sold at 57
    # - 5400 now sells out but almost all size prints at 20 despite persistent
    #   Mark 01 / Mark 14 demand across the day
    # We therefore require a minimum ask while short inventory is still below
    # a threshold. Once the threshold is reached, normal behavior resumes.
    PHASED_QUOTE_FLOORS = {
        5300: {"threshold": -140, "ask_floor": 58},
    }

    DELTA_PARAMS = {
        # v22: HYDROGEL_PACK entry removed — replaced by HYDROGEL_PARAMS
        # (see below). VELVETFRUIT params unchanged.
        # VELVETFRUIT: v11 params unchanged. mt_risk_aversion=0 means
        # MT triggers off raw fair (no inventory bias on triggers); MM
        # skew (ra=0.05) handles inventory clearing alone.
        "VELVETFRUIT_EXTRACT": {
            "ema_alpha": 0.06,
            "risk_aversion": 0.05,
            "mt_risk_aversion": 0.0,
            "take_edge": 1.0, "spread_half": 1.5,
            "base_sz": 30, "max_sz": 50,
            "anchor": 0.0, "anchor_w": 0.0,
            # v13: realized-volatility scaling
            "vol_alpha_fast": 0.05,
            "vol_alpha_slow": 0.005,
            "vol_ratio_threshold": 1.5,
            "vol_size_floor": 0.5,
        },
    }

    # ====== v22: NEW HYDROGEL_PACK PARAMETERS ======
    # Ported from the standalone hydrogel-only bot (494461 v9). The engine
    # is a wide-spread MM with regime detection; see _run_hydrogel for
    # how each parameter feeds in.
    HYDROGEL_PARAMS = {
        # ---- EMAs / decays ----
        "mid_ema_alpha":    0.10,    # mid microprice EMA (used as soft reference)
        "anchor_alpha":     0.0025,  # very-slow drift anchor (replaces static 9991)
        "fast_trend_alpha": 0.30,    # per-tick return EMA, fast
        "slow_trend_alpha": 0.08,    # per-tick return EMA, slow
        "flow_decay":       0.70,    # tape uptick/downtick bias decay
        "cp_decay":         0.72,    # counterparty signal decay (much faster than v19's 0.9985)

        # ---- Quote width / sizes ----
        "base_half":         5.8,    # base half-spread (vs v19's 1.5 — much wider, defensive)
        "base_size":         14,     # default MM size on each side
        "strong_size":       22,     # leaning into a directional alpha
        "repair_size":       28,     # reducing inventory away from a hard band
        "emergency_size":    34,     # past POS_EMERGENCY
        "max_take":          14,     # per-tick taker volume cap

        # ---- Inventory bands ----
        "pos_soft":          90,     # extra skew kicks in
        "pos_hard":          135,    # one-sided MM enforced
        "pos_emergency":     170,    # repair mode, take + emergency size
        "inv_skew":          0.060,  # linear inventory penalty on reservation
        "extra_inv_skew":    0.095,  # nonlinear penalty applied above pos_soft

        # ---- Fill blocks (don't requote into smart CPs immediately) ----
        "buy_block_ticks":   4,
        "sell_block_ticks":  4,
        "fill_cooldown":     1,
    }

    OPTIONS_PARAMS = {
        # ---- IV EMA ----
        "iv_alpha": 0.02,
        "iv_min": 0.05,
        "iv_max": 1.5,
        "fallback_sigma": 0.21,

        # ---- Trading thresholds (IV-space) ----
        "iv_band_take": 0.005,
        "iv_band_mm":   0.010,

        # ---- Absolute floors/caps ----
        "min_take_edge": 0.5,
        "min_mm_spread_half": 0.5,
        "min_fair_for_mm": 1.0,

        # ---- Sizing ----
        "mm_size": 20,
        "mt_max_size": 30,

        # ---- Inventory ----
        "risk_aversion": 0.03,
        "r": 0.0,

        # ---- Asymmetric MM (v5) ----
        # When book is this tight or tighter AND |pos| crosses the threshold,
        # suppress the side of MM that would push us further from neutral.
        # Wide-book vouchers can capture inside-touch spread regardless of pos
        # so they keep symmetric MM.
        "tight_book_max": 2,
        "asymmetric_pos_threshold": 30,

        # ---- v14: Voucher trend detection ----
        # When |VELVETFRUIT_trend × delta| > threshold, widen voucher quotes
        # and reduce MM size (defensive against stale-quote adverse selection
        # during sharp underlying moves). Delta-weighted means deep-ITM gets
        # bigger defenses, OTM barely activates.
        "voucher_trend_threshold": 0.5,
        "voucher_trend_max_width": 1.5,
        "voucher_trend_size_floor": 0.5,
        "voucher_trend_width_scale": 0.5,
    }

    # Per-voucher overrides. Any key listed in OPTIONS_PARAMS can be overridden.
    # Empirics from the day-2 backtest:
    #   strike  avg_book_spread  vega@21%   role                       asym_thr
    #   4000    ~21              ~0.5       deep ITM, parity-arb       20 (tight)
    #   4500    ~17              ~10        deep ITM, parity-arb       20 (tight)
    #   5000    6.23             87         wide-book MM               60 (loose)
    #   5100    4.44            194         wide-book MM               50
    #   5200    2.98            298         medium MM                  40
    #   5300    2.17            319         tight MM                   30
    #   5400    1.42            245         tight MM                   30
    #   5500    1.17            136         tight MM                   30
    #
    # asymmetric_pos_threshold rationale: tight thresholds where each unit
    # of inventory costs a real hedge but each fill captures little spread
    # (deep-ITM). Loose thresholds where spread per fill is meaningful and
    # hedge cost per unit is modest (ATM/wide-book).
    VOUCHER_OVERRIDES = {
        4000: {"mm_size": 30, "asymmetric_pos_threshold": 20},
        4500: {"mm_size": 30, "asymmetric_pos_threshold": 20},
        5000: {"mm_size": 40, "iv_band_take": 0.008, "asymmetric_pos_threshold": 60},  # v10: 30→40
        5100: {"mm_size": 50, "mt_max_size": 45, "iv_band_take": 0.0045, "risk_aversion": 0.020, "asymmetric_pos_threshold": 120},  # v10: 25→35
        5200: {"mm_size": 30,                        "asymmetric_pos_threshold": 40},  # v10: 20→30
        5300: {"mm_size": 20,                        "asymmetric_pos_threshold": 30},
        5400: {"mm_size": 24, "mt_max_size": 30, "iv_band_take": 0.0040, "iv_band_mm": 0.012, "risk_aversion": 0.020, "asymmetric_pos_threshold": 120},
        5500: {"mm_size": 12, "iv_band_take": 0.0055, "iv_band_mm": 0.012, "risk_aversion": 0.040, "asymmetric_pos_threshold": 30},
    }

    HEDGE_BUDGET = 180

    # v15: stub quote params — when defensive logic suppresses normal MM,
    # post a small wide order so we always have a resting bid and ask.
    # STUB_OFFSET ticks from touch, STUB_SIZE units, applied to all products.
    STUB_OFFSET = 3
    STUB_SIZE = 4

    # v19: round 4 hedges ALL traded vouchers (active strikes 5000-5500).
    # Previously {4000, 4500} were excluded as parity-arb plays — but those
    # strikes are no longer active.
    HEDGE_EXCLUDED_STRIKES: set = set()

    # ====== INIT / MEMORY ======

    def __init__(self) -> None:
        self.memory = self._fresh_memory()

    def _fresh_memory(self) -> dict:
        return {
            # v22: HYDROGEL_PACK schema rewritten for the new standalone
            # mean-reversion engine. Signals are namespaced under this dict
            # so they don't collide with the v19 top-level cp_signal/etc.
            "HYDROGEL_PACK": {
                "mid_ema": None,
                "anchor_ema": None,
                "last_mid": None,
                "fast_trend": 0.0,
                "slow_trend": 0.0,
                "cp_signal": 0.0,
                "flow_bias": 0.0,
                "history": [],
                "buy_block": 0,
                "sell_block": 0,
                "reentry": 0,
                "last_buy_fill_mid": None,
                "last_sell_fill_mid": None,
                "mode": "CALM_MM",
            },
            "VELVETFRUIT_EXTRACT": {"ema": None, "last_mid": None,
                                    "trend_ema": 0.0,
                                    "rv_fast": 0.0, "rv_slow": 0.0, "rv_count": 0,
                                    "z_mean": None, "z_var": 0.0, "z_count": 0},
            "last_S": None,
            "vouchers": {str(K): {"iv_ema": None, "iv_count": 0}
                          for K in self.ACTIVE_STRIKES},
            # v19: per-asset CP signal — accumulated, decayed each tick.
            # v22: HYDROGEL_PACK entry no longer needed here (its CP signal
            # lives inside memory["HYDROGEL_PACK"]["cp_signal"]).
            "cp_signal": {"VELVETFRUIT_EXTRACT": 0.0},
            "cp_voucher_iv": 0.0,
        }

    def decode_memory(self, state: TradingState) -> None:
        if not state.traderData:
            return
        try:
            data = json.loads(state.traderData)
            for k in self.memory:
                if k in data:
                    self.memory[k] = data[k]
            # Repair vouchers dict in case of schema drift
            if "vouchers" not in self.memory or not isinstance(self.memory["vouchers"], dict):
                self.memory["vouchers"] = {}
            for K in self.ACTIVE_STRIKES:
                self.memory["vouchers"].setdefault(str(K), {"iv_ema": None, "iv_count": 0})
            # v22: Repair HYDROGEL fields for the new engine schema
            h = self.memory.setdefault("HYDROGEL_PACK", {})
            h.setdefault("mid_ema", None)
            h.setdefault("anchor_ema", None)
            h.setdefault("last_mid", None)
            h.setdefault("fast_trend", 0.0)
            h.setdefault("slow_trend", 0.0)
            h.setdefault("cp_signal", 0.0)
            h.setdefault("flow_bias", 0.0)
            if not isinstance(h.get("history"), list):
                h["history"] = []
            h.setdefault("buy_block", 0)
            h.setdefault("sell_block", 0)
            h.setdefault("reentry", 0)
            h.setdefault("last_buy_fill_mid", None)
            h.setdefault("last_sell_fill_mid", None)
            h.setdefault("mode", "CALM_MM")
            # Strip stale v19 HYDROGEL keys to keep traderData lean
            for stale in ("ema", "trend_ema", "run_away",
                          "rv_fast", "rv_slow", "rv_count",
                          "z_mean", "z_var", "z_count"):
                h.pop(stale, None)
            # Repair VELVETFRUIT fields
            v = self.memory.setdefault("VELVETFRUIT_EXTRACT", {})
            v.setdefault("ema", None)
            v.setdefault("last_mid", None)
            v.setdefault("trend_ema", 0.0)
            v.setdefault("rv_fast", 0.0)
            v.setdefault("rv_slow", 0.0)
            v.setdefault("rv_count", 0)
            v.setdefault("z_mean", None); v.setdefault("z_var", 0.0); v.setdefault("z_count", 0)
            # v19/v22: cp_signal dict repair (only VELVETFRUIT now;
            # HYDROGEL_PACK's CP signal lives under memory["HYDROGEL_PACK"]).
            cp = self.memory.setdefault("cp_signal", {})
            cp.setdefault("VELVETFRUIT_EXTRACT", 0.0)
            # Strip stale HYDROGEL_PACK key if a v19 traderData blob comes in
            cp.pop("HYDROGEL_PACK", None)
            self.memory.setdefault("cp_voucher_iv", 0.0)
        except Exception:
            pass

    def encode_memory(self) -> str:
        # v22: keep HYDROGEL history bounded to 60 ticks before serializing
        # so traderData doesn't grow unbounded across the day.
        h = self.memory.get("HYDROGEL_PACK")
        if isinstance(h, dict):
            hist = h.get("history")
            if isinstance(hist, list) and len(hist) > 60:
                h["history"] = hist[-60:]
        return json.dumps(self.memory, separators=(",", ":"))

    # ====== BLACK-SCHOLES ======

    @staticmethod
    def norm_cdf(x: float) -> float:
        return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))

    @staticmethod
    def norm_pdf(x: float) -> float:
        return math.exp(-0.5 * x * x) / math.sqrt(2.0 * math.pi)

    @staticmethod
    def bs_call(S: float, K: float, T: float, sigma: float, r: float = 0.0) -> float:
        if T <= 0 or sigma <= 0:
            return max(0.0, S - K)
        if S <= 0:
            return 0.0
        d1 = (math.log(S / K) + (r + 0.5 * sigma * sigma) * T) / (sigma * math.sqrt(T))
        d2 = d1 - sigma * math.sqrt(T)
        return S * Trader.norm_cdf(d1) - K * math.exp(-r * T) * Trader.norm_cdf(d2)

    @staticmethod
    def bs_vega(S: float, K: float, T: float, sigma: float, r: float = 0.0) -> float:
        if T <= 0 or sigma <= 0:
            return 0.0
        d1 = (math.log(S / K) + (r + 0.5 * sigma * sigma) * T) / (sigma * math.sqrt(T))
        return S * Trader.norm_pdf(d1) * math.sqrt(T)

    @staticmethod
    def bs_delta(S: float, K: float, T: float, sigma: float, r: float = 0.0) -> float:
        if T <= 0 or sigma <= 0:
            return 1.0 if S > K else 0.0
        d1 = (math.log(S / K) + (r + 0.5 * sigma * sigma) * T) / (sigma * math.sqrt(T))
        return Trader.norm_cdf(d1)

    @staticmethod
    def implied_vol(price: float, S: float, K: float, T: float,
                    r: float = 0.0, x0: float = 0.21) -> Optional[float]:
        intrinsic = max(0.0, S - K)
        if price <= intrinsic + 1e-6 or price >= S - 1e-6:
            return None
        sigma = x0 if 0.05 < x0 < 1.5 else 0.21
        for _ in range(40):
            p = Trader.bs_call(S, K, T, sigma, r)
            v = Trader.bs_vega(S, K, T, sigma, r)
            if v < 1e-8:
                return None
            diff = p - price
            if abs(diff) < 1e-5:
                return sigma
            sigma -= diff / v
            if sigma <= 1e-4:
                sigma = 1e-4
            elif sigma >= 5.0:
                sigma = 5.0
        return sigma

    # ====== TIME ======

    def compute_tte_years(self, state: TradingState) -> float:
        """v17: Static TTE — no timestamp dependency, no intraday decay tracking.
        TTE_AT_T0_DAYS is set at submission time to match the current day's
        time-to-expiration. Within-day TTE decay is small relative to BS
        sensitivity and is washed out by IV-EMA adaptation."""
        return self.TTE_AT_T0_DAYS / self.DAYS_PER_YEAR

    # ====== ORDER BOOK HELPERS ======

    @staticmethod
    def best_bid(d: OrderDepth) -> Optional[int]:
        return max(d.buy_orders.keys()) if d.buy_orders else None

    @staticmethod
    def best_ask(d: OrderDepth) -> Optional[int]:
        return min(d.sell_orders.keys()) if d.sell_orders else None

    @staticmethod
    def compute_mid(d: OrderDepth) -> Optional[float]:
        bb = Trader.best_bid(d); ba = Trader.best_ask(d)
        if bb is None or ba is None:
            return None
        return (bb + ba) / 2.0

    @staticmethod
    def compute_micro(d: OrderDepth) -> Optional[float]:
        bb = Trader.best_bid(d); ba = Trader.best_ask(d)
        if bb is None or ba is None:
            return None
        bv = d.buy_orders[bb]; av = abs(d.sell_orders[ba])
        tot = bv + av
        if tot <= 0:
            return (bb + ba) / 2.0
        return (bb * av + ba * bv) / tot

    # ====== PER-VOUCHER PARAMS ======

    def voucher_params(self, K: int) -> dict:
        """OPTIONS_PARAMS merged with any per-voucher overrides."""
        p = dict(self.OPTIONS_PARAMS)
        p.update(self.VOUCHER_OVERRIDES.get(K, {}))
        return p

    # ====== PER-VOUCHER IV EMA ======

    def update_iv_ema(self, K: int, iv_now: Optional[float]) -> Optional[float]:
        """Update per-voucher IV EMA from current observation. Returns the EMA after update."""
        params = self.voucher_params(K)
        state = self.memory["vouchers"].setdefault(str(K), {"iv_ema": None, "iv_count": 0})

        if iv_now is None:
            return state["iv_ema"]
        if iv_now < params["iv_min"] or iv_now > params["iv_max"]:
            return state["iv_ema"]

        if state["iv_ema"] is None or state["iv_count"] == 0:
            state["iv_ema"] = iv_now
        else:
            a = params["iv_alpha"]
            state["iv_ema"] = a * iv_now + (1.0 - a) * state["iv_ema"]
        state["iv_count"] += 1
        return state["iv_ema"]

    # ====== ARBITRAGE ======

    def _arb(self, product: str, depth: OrderDepth, pos: int,
             limit: int) -> Tuple[List[Order], int, int, int]:
        orders: List[Order] = []
        buy_used = sell_used = 0
        bb = self.best_bid(depth); ba = self.best_ask(depth)
        if bb is None or ba is None or bb < ba:
            return orders, pos, buy_used, sell_used
        bv = depth.buy_orders[bb]; av = abs(depth.sell_orders[ba])
        cross = min(bv, av)
        safe = min(cross, limit - pos, limit + pos)
        if safe > 0:
            orders.append(Order(product, ba, safe))
            orders.append(Order(product, bb, -safe))
            buy_used = safe; sell_used = safe
        return orders, pos, buy_used, sell_used

    # ====== DELTA-1 ENGINES ======
    #
    # HYDROGEL uses Lorenzo's defensive logic (_run_hydrogel below).
    # VELVETFRUIT uses the v11 simple MM (_run_velvetfruit below).
    # Dispatched here so the caller in run() doesn't need to know which.

    def _vol_size_mult(self, product: str, move: float) -> float:
        """v13: realized-volatility scaling for MM size.
        Updates fast and slow squared-move EMAs for the product, then returns a
        size multiplier in [vol_size_floor, 1.0]. 1.0 = no scaling. Only scales
        down when fast_rv exceeds slow_rv by a factor (vol_ratio_threshold)."""
        params = self.DELTA_PARAMS[product]
        m = self.memory[product]

        move_sq = move * move
        fast_a = params["vol_alpha_fast"]
        slow_a = params["vol_alpha_slow"]
        rv_fast = fast_a * move_sq + (1.0 - fast_a) * m.get("rv_fast", 0.0)
        rv_slow = slow_a * move_sq + (1.0 - slow_a) * m.get("rv_slow", 0.0)
        m["rv_fast"] = rv_fast
        m["rv_slow"] = rv_slow
        m["rv_count"] = int(m.get("rv_count", 0)) + 1

        # Warmup: don't scale until both EMAs have converged enough
        if m["rv_count"] < 100 or rv_slow < 1e-3:
            return 1.0

        threshold = params["vol_ratio_threshold"]
        floor = params["vol_size_floor"]
        vol_ratio = math.sqrt(rv_fast / rv_slow)
        if vol_ratio > threshold:
            return max(floor, threshold / vol_ratio)
        return 1.0

    def _add_stubs(self, product: str, orders: List[Order],
                   pos: int, buy_used: int, sell_used: int,
                   limit: int, bb: int, ba: int) -> None:
        """v15: ensure we always quote a resting bid and ask. Mutates `orders`
        in place. Posts wide, small stubs only on the side(s) where no resting
        order already exists. 1-unit capacity buffer prevents boundary rejections."""
        # A "resting" bid is one that doesn't immediately cross — bid price < ba.
        # Anything at or above ba is a market-take that won't sit in the book.
        has_resting_bid = any(o.quantity > 0 and o.price < ba for o in orders)
        has_resting_ask = any(o.quantity < 0 and o.price > bb for o in orders)

        # Capacity with 1-unit safety buffer (so post-execution position
        # cannot equal ±limit, which we observed Prosperity rejecting).
        remaining_buy = max(0, (limit - pos) - buy_used - 1)
        remaining_sell = max(0, (limit + pos) - sell_used - 1)

        if not has_resting_bid and remaining_buy >= self.STUB_SIZE:
            stub_px = bb - self.STUB_OFFSET
            if stub_px >= 1:
                orders.append(Order(product, stub_px, self.STUB_SIZE))

        if not has_resting_ask and remaining_sell >= self.STUB_SIZE:
            stub_px = ba + self.STUB_OFFSET
            orders.append(Order(product, stub_px, -self.STUB_SIZE))

    def _run_delta_asset(self, product: str, state: TradingState,
                         target_pos: int = 0) -> List[Order]:
        if product == "HYDROGEL_PACK":
            return self._run_hydrogel(state)
        return self._run_velvetfruit(state, target_pos)

    # ====== ROUND 4: COUNTERPARTY-AWARE TRADE PROCESSING (v19: LIVE) ======
    #
    # In Round 4 the engine populates `Trade.buyer` and `Trade.seller` with
    # actual UserIds instead of None. `state.market_trades[symbol]` lists all
    # public trades that printed since the last tick; `state.own_trades[symbol]`
    # lists our own fills with the counterparty named.
    #
    # v19 LIVE behaviour: for each linear asset, maintain a per-asset signal
    # that exponentially decays each tick. For each market trade observed,
    # add the corresponding signed weight from CP_WEIGHTS (positive = follow,
    # negative = fade). The accumulated signal is added directly to the fair
    # value in _run_hydrogel and _run_velvetfruit, capped per asset.

    def _process_trades(self, state: TradingState) -> None:
        """v19: counterparty-aware fair-value adjustment.

        Step 1: decay last tick's signal toward zero.
        Step 2: for each market trade, add weighted directional signal:
                  - weight > 0  -> "smart"; buy pushes signal up, sell down
                  - weight < 0  -> "fish";  buy pushes signal down, sell up
                (the latter falls out naturally because we always use
                 +w on buyer side, -w on seller side.)
        Step 3: cap absolute value per asset.
        """
        cp = self.memory.setdefault("cp_signal", {})

        # 1) decay
        for prod in self.CP_WEIGHTS.keys():
            cp[prod] = cp.get(prod, 0.0) * self.CP_DECAY

        # 2) accumulate from new trades
        market_trades = getattr(state, "market_trades", {}) or {}
        for prod, weights in self.CP_WEIGHTS.items():
            trades = market_trades.get(prod, []) or []
            for t in trades:
                # Defensive — `buyer` / `seller` may be None if engine
                # didn't populate them on a particular trade.
                buyer = getattr(t, "buyer", None)
                seller = getattr(t, "seller", None)
                if buyer is not None and buyer in weights:
                    cp[prod] += weights[buyer]
                if seller is not None and seller in weights:
                    cp[prod] -= weights[seller]

        # 3) cap
        for prod in self.CP_WEIGHTS.keys():
            cap = self.CP_FAIR_MAX.get(prod, 1e9)
            v = cp[prod]
            if v > cap: cp[prod] = cap
            elif v < -cap: cp[prod] = -cap

        # 4) small pooled voucher-IV signal on the core strikes only
        cur_voucher_cp = float(self.memory.get("cp_voucher_iv", 0.0)) * self.CP_VOUCHER_DECAY
        for K in self.CP_VOUCHER_CORE_STRIKES:
            prod = f"VEV_{K}"
            for t in market_trades.get(prod, []) or []:
                buyer = getattr(t, "buyer", None)
                seller = getattr(t, "seller", None)
                if buyer is not None and buyer in self.CP_WEIGHTS_VOUCHER:
                    cur_voucher_cp += self.CP_WEIGHTS_VOUCHER[buyer]
                if seller is not None and seller in self.CP_WEIGHTS_VOUCHER:
                    cur_voucher_cp -= self.CP_WEIGHTS_VOUCHER[seller]
        if cur_voucher_cp > self.CP_VOUCHER_IV_MAX:
            cur_voucher_cp = self.CP_VOUCHER_IV_MAX
        elif cur_voucher_cp < -self.CP_VOUCHER_IV_MAX:
            cur_voucher_cp = -self.CP_VOUCHER_IV_MAX
        self.memory["cp_voucher_iv"] = cur_voucher_cp

    def _cp_adjust(self, product: str) -> float:
        """Convenience: read the current CP fair-value adjustment."""
        return float(self.memory.get("cp_signal", {}).get(product, 0.0))

    def _cp_voucher_iv(self) -> float:
        return float(self.memory.get("cp_voucher_iv", 0.0))

    # ====== Z-SCORE OVERLAY (streaming EMA mean/var) ======
    #
    # Maintains per-asset EMA mean and EMA variance with a single-step
    # Welford-style update. No buffer in memory (just two floats per asset),
    # so it's cheap and the JSON traderData stays small.
    #
    # Returns a target_pos (signed integer) based on |z|:
    #     |z| < z_in   -> 0
    #     z_in <= |z| <= z_full -> linearly scale to ±max_target
    #     |z| > z_full -> ±max_target  (capped)
    # Sign is opposite to z (mean-reversion).

    def _zscore_target(self, product: str, mid: float) -> int:
        params = self.ZSCORE_PARAMS.get(product)
        if params is None:
            return 0
        m = self.memory[product]
        a = params["z_alpha"]
        prev_mean = m.get("z_mean")
        if prev_mean is None:
            m["z_mean"] = mid
            m["z_var"] = 0.0
            m["z_count"] = 1
            return 0

        # Welford-style EMA update for mean+variance
        delta = mid - prev_mean
        new_mean = prev_mean + a * delta
        # Standard EMA-variance update (preserves stationarity)
        new_var = (1.0 - a) * (m.get("z_var", 0.0) + a * delta * delta)
        m["z_mean"] = new_mean
        m["z_var"] = new_var
        m["z_count"] = int(m.get("z_count", 0)) + 1

        # Need warmup before trusting the variance estimate
        if m["z_count"] < params["warmup"]:
            return 0
        std = math.sqrt(max(new_var, 1e-9))
        if std < 0.5:
            return 0
        z = (mid - new_mean) / std
        z_in, z_full, max_t = params["z_in"], params["z_full"], params["max_target"]
        az = abs(z)
        if az < z_in:
            return 0
        scale = min(1.0, (az - z_in) / max(z_full - z_in, 1e-9))
        target_mag = int(round(max_t * scale))
        return -target_mag if z > 0 else target_mag

    # ------ HYDROGEL: v22 standalone book-driven mean-reversion engine ------
    #
    # Replaces v19's run_away/anchor-9991 engine. This engine treats HYDROGEL
    # as a wide-spread MM with:
    #   - drifting anchor EMA (no static price assumption)
    #   - microprice + L1 imbalance alpha
    #   - washout / blowoff regime detection on a 30-tick mid history
    #   - mode machine with 7 states; quote-and-fade rather than chase trend
    #   - per-side fill blocks when filled by smart counterparties (Mark 14/01/22)
    #
    # All engine state lives under memory["HYDROGEL_PACK"] to avoid colliding
    # with the v19 top-level cp_signal dict (which now belongs to VELVETFRUIT).

    def _hyd_update_fill_blocks(self, state: TradingState, mid: float) -> None:
        """Decay the per-side fill blocks each tick, then bump them when our
        recent fills came from smart counterparties — the next tick's quote
        on that side is suppressed for buy_block_ticks/sell_block_ticks."""
        p = self.HYDROGEL_PARAMS
        h = self.memory["HYDROGEL_PACK"]
        buy_block = max(0, int(h.get("buy_block", 0)) - 1)
        sell_block = max(0, int(h.get("sell_block", 0)) - 1)
        reentry = max(0, int(h.get("reentry", 0)) - 1)

        own = getattr(state, "own_trades", None)
        if isinstance(own, dict):
            trades = own.get("HYDROGEL_PACK") or []
            if isinstance(trades, list):
                for t in trades:
                    # Only react to fills that printed on this tick
                    if getattr(t, "timestamp", state.timestamp) != state.timestamp:
                        continue
                    buyer = getattr(t, "buyer", None)
                    seller = getattr(t, "seller", None)
                    cp = (seller if buyer == "SUBMISSION"
                          else buyer if seller == "SUBMISSION"
                          else None)
                    if buyer == "SUBMISSION":
                        h["last_buy_fill_mid"] = mid
                        reentry = max(reentry, p["fill_cooldown"])
                        if cp in ("Mark 14", "Mark 01", "Mark 22"):
                            buy_block = max(buy_block, p["buy_block_ticks"])
                    elif seller == "SUBMISSION":
                        h["last_sell_fill_mid"] = mid
                        reentry = max(reentry, p["fill_cooldown"])
                        if cp in ("Mark 14", "Mark 01", "Mark 22"):
                            sell_block = max(sell_block, p["sell_block_ticks"])

        # Adverse-fill safety: if the market moved past our last fill, throttle
        # adding more on that side for a few ticks.
        last_buy_fill_mid = h.get("last_buy_fill_mid")
        last_sell_fill_mid = h.get("last_sell_fill_mid")
        if last_buy_fill_mid is not None and mid < float(last_buy_fill_mid) - 1.0:
            buy_block = max(buy_block, 3)
        if last_sell_fill_mid is not None and mid > float(last_sell_fill_mid) + 1.0:
            sell_block = max(sell_block, 3)

        h["buy_block"] = buy_block
        h["sell_block"] = sell_block
        h["reentry"] = reentry

    def _hyd_update_tape_overlay(self, state: TradingState, mid: float) -> None:
        """Update HYDROGEL's local CP and tape-flow signals.

        cp_signal is dominated by Mark 22 (-0.85 per print), with very small
        weights on Mark 14/38. flow_bias is a simple uptick/downtick aggregator.
        Both are bounded to [-3, 3] and decayed each tick."""
        p = self.HYDROGEL_PARAMS
        h = self.memory["HYDROGEL_PACK"]
        cp = float(h.get("cp_signal", 0.0)) * p["cp_decay"]
        flow = float(h.get("flow_bias", 0.0)) * p["flow_decay"]

        mkt = getattr(state, "market_trades", None)
        if isinstance(mkt, dict):
            trades = mkt.get("HYDROGEL_PACK") or []
            if isinstance(trades, list):
                for t in trades:
                    buyer = getattr(t, "buyer", None)
                    seller = getattr(t, "seller", None)
                    price = getattr(t, "price", mid) or mid
                    qty = getattr(t, "quantity", 0) or 0
                    try:
                        qty = abs(int(qty))
                    except Exception:
                        qty = 0
                    w = min(2.0, max(1.0, qty / 4.0))

                    # Tape direction: aggressive prints relative to mid
                    if price >= mid:
                        flow += 0.18 * w
                    elif price <= mid:
                        flow -= 0.18 * w

                    # Counterparty overlay: Mark 22 is the dominant signal
                    if buyer == "Mark 22":
                        cp -= 0.85 * w     # Mark 22 buying -> fade -> push fair down
                    elif seller == "Mark 22":
                        cp += 0.85 * w     # Mark 22 selling -> fade -> push fair up
                    elif buyer == "Mark 14":
                        cp += 0.12 * w
                    elif seller == "Mark 14":
                        cp -= 0.08 * w
                    elif buyer == "Mark 38":
                        cp += 0.03 * w
                    elif seller == "Mark 38":
                        cp -= 0.03 * w

        h["cp_signal"] = max(-3.0, min(3.0, cp))
        h["flow_bias"] = max(-3.0, min(3.0, flow))

    def _hyd_choose_mode(
        self, pos: int, gap: float, ret1: float, ret5: float,
        fast_trend: float, slow_trend: float,
        washout: bool, blowoff: bool, cp: float, flow: float,
    ) -> str:
        """Return one of:
            CALM_MM, BULL_REVERSAL, BEAR_REVERSAL,
            PRESSURE_UP, PRESSURE_DOWN, REPAIR_SHORT, REPAIR_LONG.
        Mode dictates size/skew/take-permission downstream."""
        p = self.HYDROGEL_PARAMS
        pressure_up = (fast_trend - slow_trend) > 0.9 and ret1 >= 0 and gap >= 2
        pressure_down = (fast_trend - slow_trend) < -0.9 and ret1 <= 0 and gap <= -2

        if pos <= -p["pos_emergency"] and (pressure_up or washout or ret5 > 6):
            return "REPAIR_SHORT"
        if pos >= p["pos_emergency"] and (pressure_down or blowoff or ret5 < -6):
            return "REPAIR_LONG"
        if washout:
            return "BULL_REVERSAL"
        if blowoff:
            return "BEAR_REVERSAL"
        if pos < -p["pos_hard"] and (pressure_up or cp > 0.6 or flow > 0.8):
            return "REPAIR_SHORT"
        if pos > p["pos_hard"] and (pressure_down or cp < -0.6 or flow < -0.8):
            return "REPAIR_LONG"
        if pressure_up and pos < 0:
            return "PRESSURE_UP"
        if pressure_down and pos > 0:
            return "PRESSURE_DOWN"
        return "CALM_MM"

    def _run_hydrogel(self, state: TradingState) -> List[Order]:
        product = "HYDROGEL_PACK"
        depth = state.order_depths[product]
        p = self.HYDROGEL_PARAMS
        limit = self.POSITION_LIMITS[product]
        h = self.memory["HYDROGEL_PACK"]

        bb = self.best_bid(depth); ba = self.best_ask(depth)
        if bb is None or ba is None:
            return []

        start_pos = int(state.position.get(product, 0))
        work_pos = start_pos
        orders: List[Order] = []
        buy_used = 0
        sell_used = 0

        # 1. Cross-book arb (kept from v19 — free money when the book crosses).
        arb_orders, arb_pos, arb_buy_used, arb_sell_used = self._arb(
            product, depth, start_pos, limit
        )
        if arb_orders:
            orders.extend(arb_orders)
            buy_used += arb_buy_used
            sell_used += arb_sell_used
            # arb shifts the effective position both up and down equally,
            # so work_pos is unchanged. start_pos remains the reference.

        # 2. Microprice / mid / L1 imbalance
        micro = self.compute_micro(depth) or (bb + ba) / 2.0
        mid = (bb + ba) / 2.0
        spread = float(ba - bb)
        bb_q = depth.buy_orders.get(bb, 0)
        ba_q = abs(depth.sell_orders.get(ba, 0))
        imb = 0.0
        if bb_q + ba_q > 0:
            imb = (bb_q - ba_q) / (bb_q + ba_q)
        micro_shift = micro - mid

        # 3. Mid EMA (soft reference) and drifting anchor
        prev_mid_ema = h.get("mid_ema")
        if prev_mid_ema is None:
            prev_mid_ema = mid
        mid_ema = p["mid_ema_alpha"] * mid + (1.0 - p["mid_ema_alpha"]) * float(prev_mid_ema)
        h["mid_ema"] = mid_ema

        prev_anchor = h.get("anchor_ema")
        if prev_anchor is None:
            prev_anchor = mid
        anchor = p["anchor_alpha"] * mid + (1.0 - p["anchor_alpha"]) * float(prev_anchor)
        h["anchor_ema"] = anchor

        # 4. Returns and trend EMAs
        last_mid = h.get("last_mid")
        if last_mid is None:
            last_mid = mid
        ret1 = mid - float(last_mid)
        h["last_mid"] = mid

        hist = h.get("history")
        if not isinstance(hist, list):
            hist = []
        hist.append(mid)
        hist = hist[-60:]
        h["history"] = hist

        ret5 = 0.0
        if len(hist) >= 6:
            ret5 = mid - float(hist[-6])
        recent30 = hist[-30:] if len(hist) >= 30 else hist[:]
        washout = len(recent30) >= 20 and mid <= min(recent30) and ret5 <= -8.0
        blowoff = len(recent30) >= 20 and mid >= max(recent30) and ret5 >= 8.0

        fast_prev = float(h.get("fast_trend", 0.0))
        slow_prev = float(h.get("slow_trend", 0.0))
        fast_trend = p["fast_trend_alpha"] * ret1 + (1.0 - p["fast_trend_alpha"]) * fast_prev
        slow_trend = p["slow_trend_alpha"] * ret1 + (1.0 - p["slow_trend_alpha"]) * slow_prev
        h["fast_trend"] = fast_trend
        h["slow_trend"] = slow_trend

        # 5. Update fill blocks and tape overlay (must come after mid is known)
        self._hyd_update_fill_blocks(state, mid)
        self._hyd_update_tape_overlay(state, mid)
        cp = float(h.get("cp_signal", 0.0))
        flow = float(h.get("flow_bias", 0.0))
        buy_block = int(h.get("buy_block", 0))
        sell_block = int(h.get("sell_block", 0))
        reentry = int(h.get("reentry", 0))

        # 6. Alpha (signed price-ahead estimate, in price units)
        anchor_dev = mid - anchor
        alpha = (
            9.0 * imb
            + 1.0 * micro_shift
            - 0.22 * ret1
            - 0.09 * anchor_dev
            + 0.35 * cp
            + 0.22 * flow
        )
        if washout:
            alpha += 2.2 + 0.10 * abs(ret5)
        if blowoff:
            alpha -= 2.0 + 0.08 * abs(ret5)

        # 7. Mode selection
        mode = self._hyd_choose_mode(
            start_pos, anchor_dev, ret1, ret5,
            fast_trend, slow_trend, washout, blowoff, cp, flow,
        )
        h["mode"] = mode

        # ---- helpers that respect remaining capacity ----
        def remaining_buy() -> int:
            return max(0, limit - start_pos - buy_used)

        def remaining_sell() -> int:
            return max(0, limit + start_pos - sell_used)

        def place_buy(price: int, qty: int, update_work_pos: bool = True) -> int:
            nonlocal buy_used, work_pos
            qty = min(qty, remaining_buy())
            if qty <= 0:
                return 0
            orders.append(Order(product, price, qty))
            buy_used += qty
            if update_work_pos:
                work_pos += qty
            return qty

        def place_sell(price: int, qty: int, update_work_pos: bool = True) -> int:
            nonlocal sell_used, work_pos
            qty = min(qty, remaining_sell())
            if qty <= 0:
                return 0
            orders.append(Order(product, price, -qty))
            sell_used += qty
            if update_work_pos:
                work_pos -= qty
            return qty

        # 8. Mode-driven sizing / skew / permissions
        extra_skew = 0.0
        bid_bias = 0
        ask_bias = 0
        mm_buy = p["base_size"]
        mm_sell = p["base_size"]
        allow_bid = buy_block == 0 and reentry == 0
        allow_ask = sell_block == 0 and reentry == 0
        take_buy = False
        take_sell = False

        if mode == "BULL_REVERSAL":
            allow_ask = False if start_pos <= 0 else allow_ask
            mm_buy = p["strong_size"]
            mm_sell = max(0, p["base_size"] // 2)
            bid_bias += 2
            ask_bias += 2
            take_buy = start_pos < -20 or washout
        elif mode == "BEAR_REVERSAL":
            allow_bid = False if start_pos >= 0 else allow_bid
            mm_sell = p["strong_size"]
            mm_buy = max(0, p["base_size"] // 2)
            ask_bias -= 2
            bid_bias -= 2
            take_sell = start_pos > 20 or blowoff
        elif mode == "PRESSURE_UP":
            allow_ask = False if start_pos < 0 else allow_ask
            mm_buy = p["repair_size"] if start_pos < 0 else p["base_size"]
            mm_sell = max(0, p["base_size"] // 2)
            bid_bias += 2
            ask_bias += 2
            take_buy = start_pos < -40
            extra_skew += 1.2
        elif mode == "PRESSURE_DOWN":
            allow_bid = False if start_pos > 0 else allow_bid
            mm_sell = p["repair_size"] if start_pos > 0 else p["base_size"]
            mm_buy = max(0, p["base_size"] // 2)
            ask_bias -= 2
            bid_bias -= 2
            take_sell = start_pos > 40
            extra_skew += 1.2
        elif mode == "REPAIR_SHORT":
            allow_ask = False
            mm_buy = (p["emergency_size"]
                      if start_pos <= -p["pos_emergency"]
                      else p["repair_size"])
            mm_sell = 0
            bid_bias += 3
            ask_bias += 3
            take_buy = True
            extra_skew += 2.2
        elif mode == "REPAIR_LONG":
            allow_bid = False
            mm_sell = (p["emergency_size"]
                       if start_pos >= p["pos_emergency"]
                       else p["repair_size"])
            mm_buy = 0
            ask_bias -= 3
            bid_bias -= 3
            take_sell = True
            extra_skew += 2.2
        else:  # CALM_MM
            if alpha > 1.2:
                bid_bias += 1
                ask_bias += 1
                mm_buy = p["strong_size"]
                mm_sell = max(6, p["base_size"] - 4)
            elif alpha < -1.2:
                ask_bias -= 1
                bid_bias -= 1
                mm_sell = p["strong_size"]
                mm_buy = max(6, p["base_size"] - 4)

        # 9. Persistent inventory mismatch — start throttling earlier
        if start_pos > p["pos_soft"]:
            mm_buy = min(mm_buy, max(0, 145 - start_pos))
            bid_bias -= 1
            extra_skew += 0.6
            if mode in ("PRESSURE_DOWN", "REPAIR_LONG", "BEAR_REVERSAL"):
                allow_bid = False
        if start_pos < -p["pos_soft"]:
            mm_sell = min(mm_sell, max(0, 145 + start_pos))
            ask_bias += 1
            extra_skew += 0.6
            if mode in ("PRESSURE_UP", "REPAIR_SHORT", "BULL_REVERSAL"):
                allow_ask = False

        if start_pos > p["pos_hard"]:
            allow_bid = False
            mm_buy = 0
            mm_sell = max(mm_sell, p["repair_size"])
            take_sell = True
        if start_pos < -p["pos_hard"]:
            allow_ask = False
            mm_sell = 0
            mm_buy = max(mm_buy, p["repair_size"])
            take_buy = True

        # 10. Reservation price with nonlinear inventory penalty
        extra_pos = max(0, abs(work_pos) - p["pos_soft"])
        skew = work_pos * p["inv_skew"]
        if work_pos > 0:
            skew += extra_pos * p["extra_inv_skew"]
        elif work_pos < 0:
            skew -= extra_pos * p["extra_inv_skew"]
        reservation = mid + alpha - skew

        half = max(4.4, p["base_half"] + 0.10 * max(0.0, spread - 16.0) + extra_skew)
        raw_bid = int(round(reservation - half))
        raw_ask = int(round(reservation + half))
        bid_px = max(bb + bid_bias, raw_bid)
        ask_px = min(ba + ask_bias, raw_ask)

        # Stay passive unless book is very wide / we need queue priority
        if bid_px >= ba:
            bid_px = ba - 1
        if ask_px <= bb:
            ask_px = bb + 1
        if bid_px >= ask_px:
            bid_px = ask_px - 1

        # Step in for queue priority when alpha is meaningfully directional
        if allow_bid and alpha > 0.8 and bid_px + 1 < ask_px:
            bid_px += 1
        if allow_ask and alpha < -0.8 and ask_px - 1 > bid_px:
            ask_px -= 1

        # 11. Takers — only on stale quotes / emergency repair
        if take_buy and remaining_buy() > 0:
            threshold = reservation - 5.8
            for ask in sorted(depth.sell_orders.keys()):
                if ask > threshold:
                    break
                avail = abs(depth.sell_orders[ask])
                qty = min(avail, p["max_take"], remaining_buy())
                if qty <= 0:
                    break
                place_buy(ask, qty)
                if buy_used >= p["max_take"]:
                    break
        if take_sell and remaining_sell() > 0:
            threshold = reservation + 5.8
            for bid in sorted(depth.buy_orders.keys(), reverse=True):
                if bid < threshold:
                    break
                avail = depth.buy_orders[bid]
                qty = min(avail, p["max_take"], remaining_sell())
                if qty <= 0:
                    break
                place_sell(bid, qty)
                if sell_used >= p["max_take"]:
                    break

        # 12. Resting MM quotes (with size doubling on big alpha)
        if allow_bid and mm_buy > 0:
            place_buy(bid_px, mm_buy, update_work_pos=False)
            if (alpha > 2.0 and bid_px - 1 >= 1
                    and remaining_buy() >= max(4, mm_buy // 2)):
                place_buy(bid_px - 1, max(4, mm_buy // 2), update_work_pos=False)

        if allow_ask and mm_sell > 0:
            place_sell(ask_px, mm_sell, update_work_pos=False)
            if (alpha < -2.0 and ask_px + 1 > bid_px
                    and remaining_sell() >= max(4, mm_sell // 2)):
                place_sell(ask_px + 1, max(4, mm_sell // 2), update_work_pos=False)

        # 13. v15: ensure resting bid/ask presence in case all defenses
        # suppressed both quotes. _add_stubs respects existing orders and
        # only fills in gaps.
        self._add_stubs(product, orders, start_pos, buy_used, sell_used,
                        limit, bb, ba)

        return orders


    # ------ VELVETFRUIT: v11 simple MM ------
    #
    # No close mode, no trend tracking, no inventory-aware MT (mt_ra=0).
    # Just the v11-style microprice EMA fair, plain MT, MM with skew that
    # already handles inventory clearing through quote placement.

    def _run_velvetfruit(self, state: TradingState, target_pos: int = 0) -> List[Order]:
        product = "VELVETFRUIT_EXTRACT"
        depth = state.order_depths[product]
        params = self.DELTA_PARAMS[product]
        limit = self.POSITION_LIMITS[product]
        pos = state.position.get(product, 0)

        bb = self.best_bid(depth); ba = self.best_ask(depth)
        if bb is None or ba is None:
            return []

        # 1. Arb
        orders, pos, buy_used, sell_used = self._arb(product, depth, pos, limit)

        # 2. Microprice + EMA
        micro = self.compute_micro(depth) or (bb + ba) / 2.0
        mid = (bb + ba) / 2.0
        prev_ema = self.memory[product]["ema"]
        if prev_ema is None:
            prev_ema = micro
        ema = params["ema_alpha"] * micro + (1.0 - params["ema_alpha"]) * prev_ema
        self.memory[product]["ema"] = ema

        last_mid = self.memory[product]["last_mid"]
        if last_mid is None:
            last_mid = mid
        move = mid - last_mid
        self.memory[product]["last_mid"] = mid

        # v14: Track trend_ema on VELVETFRUIT (read by voucher engine for
        # underlying-trend defenses). Same alpha as Lorenzo's HYDROGEL trend.
        prev_trend = float(self.memory[product].get("trend_ema", 0.0))
        trend_ema = 0.18 * move + 0.82 * prev_trend
        self.memory[product]["trend_ema"] = trend_ema

        # v13: realized-volatility size multiplier
        vol_size_mult = self._vol_size_mult(product, move)

        # 3. Fair value (anchor_w=0 means anchor doesn't contribute)
        anchor_w = params["anchor_w"]
        nonanchor = 1.0 - anchor_w
        ema_w = 0.6875 * nonanchor
        mic_w = 0.3125 * nonanchor
        fair = ema_w * ema + mic_w * micro + anchor_w * params["anchor"] - 0.12 * move

        # v19: counterparty signal (Mark 55 fish, Mark 01/14 smart, etc.)
        fair += self._cp_adjust(product)

        # v19: z-score target ADDS to the voucher hedge target. Cap the sum
        # at ±70% of position limit so we always have headroom to MM.
        z_target = self._zscore_target(product, mid)
        combined_target = target_pos + z_target
        cap = int(round(0.70 * limit))
        if combined_target > cap: combined_target = cap
        elif combined_target < -cap: combined_target = -cap
        target_pos = combined_target

        # 4. Plain MT (mt_risk_aversion=0 → triggers off raw fair)
        take_edge = params["take_edge"]
        mt_ra = params.get("mt_risk_aversion", 0.0)
        mt_skew = (pos - target_pos) * mt_ra
        mt_reservation = fair - mt_skew

        for ask_px in sorted(depth.sell_orders.keys()):
            if ask_px > mt_reservation - take_edge:
                break
            vol_avail = abs(depth.sell_orders[ask_px])
            cap = (limit - pos) - buy_used
            qty = min(vol_avail, cap, params["max_sz"])
            if qty > 0:
                orders.append(Order(product, ask_px, qty))
                pos += qty; buy_used += qty

        for bid_px in sorted(depth.buy_orders.keys(), reverse=True):
            if bid_px < mt_reservation + take_edge:
                break
            vol_avail = depth.buy_orders[bid_px]
            cap = (limit + pos) - sell_used
            qty = min(vol_avail, cap, params["max_sz"])
            if qty > 0:
                orders.append(Order(product, bid_px, -qty))
                pos -= qty; sell_used += qty

        # 5. MM with hedge-target-aware skew
        deviation = pos - target_pos
        skew = deviation * params["risk_aversion"]
        reservation = fair - skew

        raw_bid = int(round(reservation - params["spread_half"]))
        raw_ask = int(round(reservation + params["spread_half"]))
        bid_px = min(raw_bid, bb + 1)
        ask_px = max(raw_ask, ba - 1)
        if bid_px >= ask_px:
            bid_px = ask_px - 1

        inv_ratio = abs(deviation) / limit
        shrink = max(0.4, 1.0 - 0.55 * inv_ratio)
        base_sz = max(8, int(round(params["base_sz"] * shrink * vol_size_mult)))

        mm_buy = max(0, min(base_sz, (limit - pos) - buy_used))
        mm_sell = max(0, min(base_sz, (limit + pos) - sell_used))
        if mm_buy > 0:
            orders.append(Order(product, bid_px, mm_buy))
        if mm_sell > 0:
            orders.append(Order(product, ask_px, -mm_sell))

        # v15: ensure resting bid/ask presence (no-op when normal MM fires)
        self._add_stubs(product, orders, pos, buy_used, sell_used, limit, bb, ba)

        return orders

    # ====== VOUCHER ENGINE (per-voucher EMA-IV + adaptive spread) ======

    def _run_voucher(self, state: TradingState, product: str,
                     S: float, T: float) -> List[Order]:
        depth = state.order_depths[product]
        K = float(product.split('_')[1])
        params = self.voucher_params(int(K))   # merged defaults + overrides
        limit = self.POSITION_LIMITS[product]
        pos = state.position.get(product, 0)

        bb = self.best_bid(depth); ba = self.best_ask(depth)
        if bb is None or ba is None:
            return []
        book_spread = ba - bb

        # 1. Compute current market mid + IV, update per-voucher EMA
        mid_now = (bb + ba) / 2.0
        last_ema = self.memory["vouchers"].get(str(int(K)), {}).get("iv_ema")
        x0 = last_ema if (last_ema is not None) else params["fallback_sigma"]
        iv_now = self.implied_vol(mid_now, S, K, T, x0=x0)
        sigma = self.update_iv_ema(int(K), iv_now)
        if sigma is None:
            sigma = params["fallback_sigma"]

        # v19: per-strike IV bias. Negative bias prices the option lower than
        # market IV-EMA implies → we systematically lean SHORT vol on rich
        # strikes (5200/5300 most aggressive), neutral-ish on the relatively
        # cheap K=5400. Bias applied only to fair-value pricing here; the
        # IV-EMA itself continues to track the unbiased market.
        sigma_for_pricing = sigma + self.IV_BIAS.get(int(K), 0.0)

        if int(K) in self.CP_VOUCHER_CORE_STRIKES:
            cp_iv = self._cp_voucher_iv()
            if int(K) == 5100:
                sigma_for_pricing += cp_iv
            else:
                sigma_for_pricing += 0.5 * cp_iv

        phase_cfg = self.PHASED_VOUCHER_AGGR.get(int(K))
        phase_active = phase_cfg is not None and pos > phase_cfg["threshold"]
        if phase_active:
            sigma_for_pricing += phase_cfg["bias_relax"]

        floor_cfg = self.PHASED_QUOTE_FLOORS.get(int(K))
        floor_active = floor_cfg is not None and pos > floor_cfg["threshold"]
        ask_floor = floor_cfg["ask_floor"] if floor_active else None

        if sigma_for_pricing < params["iv_min"]:
            sigma_for_pricing = params["iv_min"]

        # 2. Fair value + vega for threshold scaling
        fair = self.bs_call(S, K, T, sigma_for_pricing, params["r"])
        vega = self.bs_vega(S, K, T, sigma_for_pricing, params["r"])
        intrinsic = max(0.0, S - K)
        if fair < intrinsic:
            fair = intrinsic

        # v14: Underlying trend defense — if VELVETFRUIT is trending and
        # the voucher has nontrivial delta, our MM quotes can become stale
        # and adversely-selected. Widen quotes and shrink size proportional
        # to |S_trend × delta|.
        S_trend = float(self.memory.get("VELVETFRUIT_EXTRACT", {}).get("trend_ema", 0.0))
        delta_k = self.bs_delta(S, K, T, sigma)
        trend_signal = abs(S_trend * delta_k)
        v_thr = params["voucher_trend_threshold"]
        if trend_signal > v_thr:
            voucher_extra_width = min(
                params["voucher_trend_max_width"],
                (trend_signal - v_thr) * params["voucher_trend_width_scale"],
            )
            voucher_size_mult = max(
                params["voucher_trend_size_floor"],
                v_thr / trend_signal,
            )
        else:
            voucher_extra_width = 0.0
            voucher_size_mult = 1.0

        # 3. Take threshold (price units): max(absolute floor, vega * iv_band)
        # MT also gets pickier when underlying is trending (require more edge)
        take_edge = max(params["min_take_edge"], vega * params["iv_band_take"]) + voucher_extra_width
        if phase_active:
            take_edge += phase_cfg["take_extra"]

        # 4. ADAPTIVE MM half-spread:
        #    - target = vega * iv_band_mm
        #    - cap = (book_spread - 1) / 2, i.e., the largest half-spread that
        #      still places our raw_bid > bb and raw_ask < ba (inside the book).
        #    - floor = min_mm_spread_half (so we don't quote zero-spread).
        #    For a 1-tick book, cap collapses to floor (we'll join touch).
        mm_target = vega * params["iv_band_mm"]
        mm_cap = max(params["min_mm_spread_half"], (book_spread - 1) / 2.0)
        spread_half = max(params["min_mm_spread_half"], min(mm_target, mm_cap))
        # v14: trend-defense additionally widens MM (composes with adaptive spread)
        spread_half += voucher_extra_width
        if phase_active:
            spread_half += phase_cfg["width_extra"]

        # 5. Arb (cross-book)
        orders, pos, buy_used, sell_used = self._arb(product, depth, pos, limit)

        # 6. Market-take buys
        for ask_px in sorted(depth.sell_orders.keys()):
            if ask_px > fair - take_edge:
                break
            vol_avail = abs(depth.sell_orders[ask_px])
            cap = (limit - pos) - buy_used
            qty = min(vol_avail, cap, params["mt_max_size"])
            if qty > 0:
                orders.append(Order(product, ask_px, qty))
                pos += qty; buy_used += qty

        # 7. Market-take sells
        for bid_px in sorted(depth.buy_orders.keys(), reverse=True):
            if bid_px < fair + take_edge:
                break
            if ask_floor is not None and bid_px < ask_floor:
                break
            vol_avail = depth.buy_orders[bid_px]
            cap = (limit + pos) - sell_used
            qty = min(vol_avail, cap, params["mt_max_size"])
            if qty > 0:
                orders.append(Order(product, bid_px, -qty))
                pos -= qty; sell_used += qty

        # 8. Skip MM on near-zero options
        if fair < params["min_fair_for_mm"]:
            self._add_stubs(product, orders, pos, buy_used, sell_used, limit, bb, ba)
            return orders

        # 9. Market make with skew
        skew = pos * params["risk_aversion"]
        # On tight books, cap |skew| so it can't push our quote across the spread.
        # max-allowed offset = book_half - 0.5; for 1-tick book this is 0 (no skew).
        # Wider books are unaffected — clipping handles them via min/max(bb+1, ba-1).
        tight_max = params.get("tight_book_max", 2)
        if book_spread <= tight_max:
            skew_cap = max(0.0, book_spread / 2.0 - 0.5)
            skew = max(-skew_cap, min(skew_cap, skew))
        reservation = fair - skew
        raw_bid = int(round(reservation - spread_half))
        raw_ask = int(round(reservation + spread_half))
        bid_px = min(raw_bid, bb + 1)
        ask_px = max(raw_ask, ba - 1)
        if ask_floor is not None:
            ask_px = max(ask_px, ask_floor)
        if bid_px >= ask_px:
            bid_px = ask_px - 1
        if bid_px < 1 or ask_px < 2:
            self._add_stubs(product, orders, pos, buy_used, sell_used, limit, bb, ba)
            return orders

        # Inventory shrink — if we've drifted long/short, smaller MM size
        inv_ratio = abs(pos) / limit
        shrink = max(0.3, 1.0 - 0.7 * inv_ratio)
        # v14: trend defense also reduces size when underlying is trending
        mm_size = max(3, int(round(params["mm_size"] * shrink * voucher_size_mult * (phase_cfg["mm_mult"] if phase_active else 1.0))))

        mm_buy = max(0, min(mm_size, (limit - pos) - buy_used))
        mm_sell = max(0, min(mm_size, (limit + pos) - sell_used))

        # ---- Asymmetric MM (v6: position-only trigger, per-voucher threshold) ----
        # When inventory crosses this voucher's threshold, drop the side that
        # would push us further from neutral. Threshold is a property of the
        # voucher's economics (hedge_cost_per_unit / spread_per_fill),
        # NOT of the current book width — so no book_spread gate here.
        asym_thr = params.get("asymmetric_pos_threshold", 30)
        if abs(pos) >= asym_thr:
            if pos > 0:
                mm_buy = 0       # long: stop adding, only post the ask
            else:
                mm_sell = 0      # short: stop adding, only post the bid

        if mm_buy > 0:
            orders.append(Order(product, bid_px, mm_buy))
        if mm_sell > 0:
            orders.append(Order(product, ask_px, -mm_sell))

        # v15: stubs on whichever side asymmetric MM (or anything else) suppressed
        self._add_stubs(product, orders, pos, buy_used, sell_used, limit, bb, ba)

        return orders

    # ====== MAIN ======

    def run(self, state: TradingState) -> Tuple[Dict[str, List[Order]], int, str]:
        self.decode_memory(state)

        # v18 (Round 4): counterparty-aware trade analysis hook. No-op for now —
        # only present so we can flesh it out without restructuring run().
        self._process_trades(state)

        T = self.compute_tte_years(state)
        result: Dict[str, List[Order]] = {}

        # 1. Underlying mid
        S: Optional[float] = None
        if "VELVETFRUIT_EXTRACT" in state.order_depths:
            S = self.compute_mid(state.order_depths["VELVETFRUIT_EXTRACT"])
        if S is None:
            S = self.memory.get("last_S")
        if S is not None:
            self.memory["last_S"] = S

        # 2. HYDROGEL — independent
        if "HYDROGEL_PACK" in state.order_depths:
            ords = self._run_delta_asset("HYDROGEL_PACK", state, target_pos=0)
            if ords:
                result["HYDROGEL_PACK"] = ords

        # 3. Vouchers — each updates its own IV EMA, prices off it
        hedge_target = 0
        if S is not None and T > 0:
            for K in self.ACTIVE_STRIKES:
                prod = f"VEV_{K}"
                if prod in state.order_depths:
                    ords = self._run_voucher(state, prod, S, T)
                    if ords:
                        result[prod] = ords

            # 4. Voucher net delta -> VELVETFRUIT hedge target.
            #    Deep-ITM strikes (HEDGE_EXCLUDED_STRIKES) are skipped — their
            #    positions run unhedged.
            net_delta = 0.0
            for K in self.ACTIVE_STRIKES:
                if K in self.HEDGE_EXCLUDED_STRIKES:
                    continue
                pos_k = state.position.get(f"VEV_{K}", 0)
                if pos_k == 0:
                    continue
                v_state = self.memory["vouchers"].get(str(K), {})
                sigma_k = v_state.get("iv_ema") or self.OPTIONS_PARAMS["fallback_sigma"]
                d_k = self.bs_delta(S, float(K), T, sigma_k)
                net_delta += pos_k * d_k
            hedge_target = -int(round(net_delta))
            hedge_target = max(-self.HEDGE_BUDGET, min(self.HEDGE_BUDGET, hedge_target))

        # 5. VELVETFRUIT runs LAST so the hedge target is known
        if "VELVETFRUIT_EXTRACT" in state.order_depths:
            ords = self._run_delta_asset("VELVETFRUIT_EXTRACT", state,
                                         target_pos=hedge_target)
            if ords:
                result["VELVETFRUIT_EXTRACT"] = ords

        return result, 0, self.encode_memory()