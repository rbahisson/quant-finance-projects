import json
import math
from typing import Dict, List, Tuple, Optional
from datamodel import OrderDepth, TradingState, Order


class Trader:
    """
    Round 3 - v17: Timestamp-free production version

    Changes vs v15
    --------------
    Removed all dependency on state.timestamp for robustness against any
    timestamp scale or behavior in the production environment.

    What's removed:
    - close_mode: Lorenzo's timestamp-based late-day flattening (was firing
      on day_frac >= 0.80/0.90/0.95). Replaced by relying on run_away
      defenses for risk management. Day-2 backtest impact: HYDROGEL might
      come in $1k–2k lower than v15 because the late-day flatten gain is gone.
    - day_offset / prev_ts: timestamp-based day boundary tracking
    - Intraday TTE decay: TTE is now static at TTE_AT_T0_DAYS

    What's kept:
    - run_away counter and trend_ema: trigger on price action, not time —
      so they fire on actual market conditions, robust to any day length
    - All other defenses: vol-scaling, voucher trend defense, asymmetric MM,
      stub quotes, mean-reversion biased hedge logic etc.

    Configuration before submitting:
    - TTE_AT_T0_DAYS: must match the round/day at submission time

    Inherited from v15
    ------------------
    HYDROGEL: Lorenzo's run_away/trend_ema defenses + vol-scaling
    VELVETFRUIT: simple MM
    Vouchers: per-voucher EMA-IV + asymmetric MM + voucher trend defense
    Stub quotes for always-on liquidity provision
    """

    # ====== CONFIG ======

    TTE_AT_T0_DAYS = 5             # set per environment (5 live, 6 day-2 backtest, 8 from day-0)
    DAYS_PER_YEAR = 252.0

    POSITION_LIMITS = {
        "HYDROGEL_PACK": 200,
        "VELVETFRUIT_EXTRACT": 200,
        "VEV_4000": 300, "VEV_4500": 300, "VEV_5000": 300, "VEV_5100": 300,
        "VEV_5200": 300, "VEV_5300": 300, "VEV_5400": 300, "VEV_5500": 300,
        "VEV_6000": 300, "VEV_6500": 300,
    }

    # Strikes the voucher engine actively trades.
    # 6000/6500 dropped — $0/$1 books, no real liquidity.
    # 4000/4500 added back in v5 — deep-ITM, traded as parity-arb plays.
    ACTIVE_STRIKES = [4000, 4500, 5000, 5100, 5200, 5300, 5400, 5500]

    DELTA_PARAMS = {
        # HYDROGEL: Lorenzo's params. No adaptive anchor (static 9991),
        # no inventory-aware MT (Lorenzo uses run_away + close_mode instead).
        "HYDROGEL_PACK": {
            "ema_alpha": 0.06,
            "risk_aversion": 0.015,
            "take_edge": 1.0,
            "spread_half": 1.5,
            "base_sz": 40, "max_sz": 60,
            "anchor": 9991.0,
            "anchor_w": 0.20,
            # v13: realized-volatility scaling for MM size
            "vol_alpha_fast": 0.05,        # ~20 tick EMA
            "vol_alpha_slow": 0.005,       # ~200 tick EMA
            "vol_ratio_threshold": 1.5,    # scale below this ratio = no effect
            "vol_size_floor": 0.5,         # bounded reduction
        },
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
        5100: {"mm_size": 35,                        "asymmetric_pos_threshold": 50},  # v10: 25→35
        5200: {"mm_size": 30,                        "asymmetric_pos_threshold": 40},  # v10: 20→30
        5300: {"mm_size": 20,                        "asymmetric_pos_threshold": 30},
        5400: {"mm_size": 15,                        "asymmetric_pos_threshold": 30},
        5500: {"mm_size": 12,                        "asymmetric_pos_threshold": 30},
    }

    HEDGE_BUDGET = 120

    # v15: stub quote params — when defensive logic suppresses normal MM,
    # post a small wide order so we always have a resting bid and ask.
    # STUB_OFFSET ticks from touch, STUB_SIZE units, applied to all products.
    STUB_OFFSET = 3
    STUB_SIZE = 4

    # Strikes whose positions are NOT counted toward the cross-product delta
    # hedge target. Deep-ITM vouchers behave like delta-1 underlying exposure;
    # hedging them via VELVETFRUIT trades $1 of voucher edge for ~$1 of
    # VELVETFRUIT mean-reversion edge, so it's better to leave them unhedged
    # and accept the bounded directional risk.
    HEDGE_EXCLUDED_STRIKES = {4000, 4500}

    # ====== INIT / MEMORY ======

    def __init__(self) -> None:
        self.memory = self._fresh_memory()

    def _fresh_memory(self) -> dict:
        return {
            # HYDROGEL needs trend_ema and run_away for Lorenzo's logic.
            # v13 adds rv_fast / rv_slow / rv_count for vol-scaled MM sizing.
            "HYDROGEL_PACK": {"ema": None, "last_mid": None,
                              "trend_ema": 0.0, "run_away": 0,
                              "rv_fast": 0.0, "rv_slow": 0.0, "rv_count": 0},
            "VELVETFRUIT_EXTRACT": {"ema": None, "last_mid": None,
                                    "trend_ema": 0.0,
                                    "rv_fast": 0.0, "rv_slow": 0.0, "rv_count": 0},
            "last_S": None,
            "vouchers": {str(K): {"iv_ema": None, "iv_count": 0}
                          for K in self.ACTIVE_STRIKES},
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
            # Repair HYDROGEL fields
            h = self.memory.setdefault("HYDROGEL_PACK", {})
            h.setdefault("ema", None)
            h.setdefault("last_mid", None)
            h.setdefault("trend_ema", 0.0)
            h.setdefault("run_away", 0)
            h.setdefault("rv_fast", 0.0)
            h.setdefault("rv_slow", 0.0)
            h.setdefault("rv_count", 0)
            # Repair VELVETFRUIT fields
            v = self.memory.setdefault("VELVETFRUIT_EXTRACT", {})
            v.setdefault("ema", None)
            v.setdefault("last_mid", None)
            v.setdefault("trend_ema", 0.0)
            v.setdefault("rv_fast", 0.0)
            v.setdefault("rv_slow", 0.0)
            v.setdefault("rv_count", 0)
        except Exception:
            pass

    def encode_memory(self) -> str:
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

    # ------ HYDROGEL: Lorenzo's defensive engine ------
    #
    # Static anchor (9991), trend EMA, run-away detection, close mode with
    # progressive flattening, late-stretch forced inventory compression,
    # one-sided-flatten when persistently trending against us.

    def _run_hydrogel(self, state: TradingState) -> List[Order]:
        product = "HYDROGEL_PACK"
        depth = state.order_depths[product]
        params = self.DELTA_PARAMS[product]
        limit = self.POSITION_LIMITS[product]
        pos = state.position.get(product, 0)

        bb = self.best_bid(depth); ba = self.best_ask(depth)
        if bb is None or ba is None:
            return []

        # 1. Cross-book arb
        orders, pos, buy_used, sell_used = self._arb(product, depth, pos, limit)

        # 2. Microprice + EMA
        micro = self.compute_micro(depth) or (bb + ba) / 2.0
        mid = (bb + ba) / 2.0
        prev_ema = self.memory[product]["ema"]
        if prev_ema is None:
            prev_ema = micro
        ema = params["ema_alpha"] * micro + (1.0 - params["ema_alpha"]) * prev_ema
        self.memory[product]["ema"] = ema

        # 3. Move + trend EMA
        last_mid = self.memory[product]["last_mid"]
        if last_mid is None:
            last_mid = mid
        move = mid - last_mid
        self.memory[product]["last_mid"] = mid

        prev_trend = float(self.memory[product].get("trend_ema", 0.0))
        trend_ema = 0.18 * move + 0.82 * prev_trend
        self.memory[product]["trend_ema"] = trend_ema

        # v13: realized-volatility-based size multiplier (composes with Lorenzo's size_mult)
        vol_size_mult = self._vol_size_mult(product, move)

        # 4. Fair value (static anchor + small mean-revert kicker via -0.12*move)
        anchor_w = params["anchor_w"]
        nonanchor = 1.0 - anchor_w
        ema_w = 0.6875 * nonanchor    # 0.55/0.80
        mic_w = 0.3125 * nonanchor    # 0.25/0.80
        fair = ema_w * ema + mic_w * micro + anchor_w * params["anchor"] - 0.12 * move

        # 5. Run-away detection + size/width/MT-gate decisions.
        # Note: v17 removes close_mode (the timestamp-based late-day flatten)
        # for environment-independence. run_away triggers on price action,
        # which is robust to any timestamp scale.
        size_mult = 1.0
        extra_width = 0.0
        allow_buy_taker = True
        allow_sell_taker = True
        one_sided_flatten = False

        gap = mid - params["anchor"]
        moving_away = gap * move > 0
        trend_align = gap * trend_ema > 0

        run_away = int(self.memory[product].get("run_away", 0))
        if abs(gap) >= 5 and moving_away and trend_align:
            run_away = min(8, run_away + 1)
        elif abs(gap) <= 2 or gap * trend_ema < 0:
            run_away = max(0, run_away - 2)
        else:
            run_away = max(0, run_away - 1)
        self.memory[product]["run_away"] = run_away

        # Light throttling whenever we're far from anchor and moving away
        if abs(gap) >= 10 and moving_away:
            size_mult = 0.55
            extra_width = 1.0
        elif abs(gap) >= 6 and moving_away:
            size_mult = 0.75
            extra_width = 0.5

        # Stronger throttling when run_away counter sustains
        strong_run = (abs(gap) >= 6 and trend_align and run_away >= 3)
        severe_run = (abs(gap) >= 8 and trend_align and run_away >= 5)
        if strong_run:
            size_mult = min(size_mult, 0.32)
            extra_width = max(extra_width, 1.1)
            # Disable the MT side that would deepen the wrong-way position
            if gap > 0:
                allow_sell_taker = False
            else:
                allow_buy_taker = False
        if severe_run:
            size_mult = min(size_mult, 0.18)
            extra_width = max(extra_width, 1.8)
            one_sided_flatten = True

        # 6. Market take with allow_*_taker gates
        take_edge = params["take_edge"]
        if allow_buy_taker:
            for ask_px in sorted(depth.sell_orders.keys()):
                if ask_px > fair - take_edge:
                    break
                vol_avail = abs(depth.sell_orders[ask_px])
                cap = (limit - pos) - buy_used
                qty = min(vol_avail, cap, params["max_sz"])
                if qty > 0:
                    orders.append(Order(product, ask_px, qty))
                    pos += qty; buy_used += qty

        if allow_sell_taker:
            for bid_px in sorted(depth.buy_orders.keys(), reverse=True):
                if bid_px < fair + take_edge:
                    break
                vol_avail = depth.buy_orders[bid_px]
                cap = (limit + pos) - sell_used
                qty = min(vol_avail, cap, params["max_sz"])
                if qty > 0:
                    orders.append(Order(product, bid_px, -qty))
                    pos -= qty; sell_used += qty

        # 7. Skew (target = 0 for HYDROGEL)
        target_for_skew = 0
        deviation = pos - target_for_skew
        risk_aversion = params["risk_aversion"]
        skew = deviation * risk_aversion
        reservation = fair - skew

        raw_bid = int(round(reservation - params["spread_half"] - extra_width))
        raw_ask = int(round(reservation + params["spread_half"] + extra_width))
        bid_px = min(raw_bid, bb + 1)
        ask_px = max(raw_ask, ba - 1)
        if bid_px >= ask_px:
            bid_px = ask_px - 1

        # 8. MM size with shrink * size_mult * vol_size_mult
        inv_ratio = abs(deviation) / limit
        shrink = max(0.4, 1.0 - 0.55 * inv_ratio)
        base_sz = max(8, int(round(params["base_sz"] * shrink * size_mult * vol_size_mult)))

        mm_buy = max(0, min(base_sz, (limit - pos) - buy_used))
        mm_sell = max(0, min(base_sz, (limit + pos) - sell_used))

        # 9. One-sided-flatten override (severe_run)
        if one_sided_flatten:
            if gap > 0:
                # Upward run-away: don't add fresh shorts; only buy to flatten
                # if we're already short.
                mm_sell = 0
                if pos >= 0:
                    mm_buy = 0
                else:
                    mm_buy = max(mm_buy, min(abs(pos), max(4, base_sz)))
            else:
                # Downward run-away: don't add fresh longs; only sell to
                # flatten if we're already long.
                mm_buy = 0
                if pos <= 0:
                    mm_sell = 0
                else:
                    mm_sell = max(mm_sell, min(abs(pos), max(4, base_sz)))

        if mm_buy > 0:
            orders.append(Order(product, bid_px, mm_buy))
        if mm_sell > 0:
            orders.append(Order(product, ask_px, -mm_sell))

        # v15: ensure resting bid/ask presence even if defenses suppressed MM
        self._add_stubs(product, orders, pos, buy_used, sell_used, limit, bb, ba)

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

        # 2. Fair value + vega for threshold scaling
        fair = self.bs_call(S, K, T, sigma, params["r"])
        vega = self.bs_vega(S, K, T, sigma, params["r"])
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
        if bid_px >= ask_px:
            bid_px = ask_px - 1
        if bid_px < 1 or ask_px < 2:
            self._add_stubs(product, orders, pos, buy_used, sell_used, limit, bb, ba)
            return orders

        # Inventory shrink — if we've drifted long/short, smaller MM size
        inv_ratio = abs(pos) / limit
        shrink = max(0.3, 1.0 - 0.7 * inv_ratio)
        # v14: trend defense also reduces size when underlying is trending
        mm_size = max(3, int(round(params["mm_size"] * shrink * voucher_size_mult)))

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