from datamodel import TradingState, Order
from typing import Dict, List
import json
import math

# ============================================================================
# Round 5 strategy — v11 (incremental refinement of v10, which scored 676,390.5)
#
# Single change vs v10: add 3 PEBBLES entries to GROUP_FLOW_OVERRIDE.
#
# v10 added GROUP_FLOW_OVERRIDE for 4 non-Pebbles products and worked. The
# Pebbles entries were deliberately held back over a double-counting concern
# with the basket-residual signal. Re-examining the data, the two signals
# are actually orthogonal in structure:
#
#   - Basket-residual signal fires when sum(Pebbles) != 50,000 (one leg is
#     mispriced relative to the others)
#   - Group-flow signal fires when there's broad buying or selling across
#     all 5 Pebbles simultaneously (basket is shifting up or down, but sum
#     stays near 50,000)
#
# Critical evidence: PEBBLES_XL has empirical β to group_flow of -1.41,
# OPPOSITE the direction of its basket-residual β of +0.27. This makes
# sense: broad buying drives all 5 Pebbles up, but the sum-to-50,000
# constraint forces XL (the dispersing leg) to take the offsetting move
# down. So the same XL fair-value adjustment goes opposite directions for
# the two signals — they fire in different scenarios.
#
# Magnitudes calibrated using own_sig decay (0.55 per tick → steady-state
# amplification 2.22x), so optimal COEF ≈ empirical β / 2.22:
#   PEBBLES_M:  empirical +1.28 → COEF +0.58 (using 0.6)
#   PEBBLES_XL: empirical -1.41 → COEF -0.63 (using -0.7)
#   PEBBLES_L:  empirical +0.66 → COEF +0.30 (using 0.3)
#
# All three are sign-stable across all 3 days. PEBBLES_XS and PEBBLES_S
# have sign flips and are excluded.
#
# Risk: if basket and group-flow signals turn out to be more correlated
# than the structural argument suggests, this adds whipsaw rather than
# alpha. The XL coefficient of -0.7 is the largest GROUP_FLOW_OVERRIDE
# value yet and the highest-stakes new addition.
# ============================================================================
#
# Original v10 header below:
# Round 5 strategy — v10 (incremental refinement of v9, which scored 672,642)
#
# Single change vs v9: per-product GROUP_FLOW_COEF overrides for 4 products,
# applying the same calibration pattern that worked surprisingly well in v9.
#
# v9 added per-product MICRO_OVERRIDE for products where empirical microprice
# beta differed substantially from the group coefficient. Same logic applied
# to the GROUP_FLOW_COEF table reveals four products where the v9 coefficient
# is materially miscalibrated:
#
#   UV_VISOR_YELLOW       v9=+0.06  empirical avg=+0.99 (16x undershoot)
#   UV_VISOR_RED          v9=+0.06  empirical avg=+0.64 (10x undershoot)
#   OXYGEN_SHAKE_GARLIC   v9=+0.05  empirical avg=+0.57 (11x undershoot)
#   MICROCHIP_OVAL        v9=+0.03  empirical avg=-0.70 (SIGN FLIPPED)
#
# All four are cross-day sign-consistent. MICROCHIP_OVAL is the most
# significant — for every group-flow event in v9, the strategy was moving
# fair value the WRONG DIRECTION because the group's +0.03 coefficient
# doesn't match OVAL's empirical -0.70 across all three days.
#
# Coefficients set to ~50% of empirical average (safety margin, same as v9).
#
# DELIBERATELY HELD BACK: Pebbles overrides. PEBBLES_M, XL, L all show
# stable empirical betas of |0.66| to |1.41| against v9's 0.0 group coef.
# But group_flow may overlap with the basket-residual signal for these
# products, risking double-counting. If v10 lands well, that's the next
# experiment for v11.
#
# Same overfitting-aware design as v8/v9: only added overrides where the
# signal is verified across all 3 training days.
# ============================================================================
#
# Original v9 header below:
# Round 5 strategy — v9 (incremental refinement of v8, which scored 663,950)
#
# Single change vs v8: add 5 per-product micro-tilt overrides.
#
# v8 used a single MICRO_GROUP coefficient per group of 5 products, but the
# per-product empirical betas show large dispersion within groups. For four
# products (ROBOT_IRONING, TRANSLATOR_VOID_BLUE, PANEL_1X2, PANEL_2X4) the
# empirical β is 2-4x the group coefficient — v8 was undershooting their
# microprice signal. For one product (MICROCHIP_RECTANGLE) the empirical β
# is ~0 with sign flips across days — v8 was applying the group's 0.7 coef
# to noise. The MICRO_OVERRIDE table fixes both directions.
#
# Same overfitting-aware design as v8: only added per-product values where
# (1) sign is consistent across all 3 days, (2) cross-day swing/mean < 0.6,
# (3) magnitude differs from group coef by enough to matter (~2x). The two
# tempting candidates I rejected: MICROCHIP_SQUARE (β = 3.09 but swings 1.2
# to 5.2 across days — unstable) and ROBOT_DISHES (β near zero but central
# product; not worth touching).
#
# All overrides set to ~70% of empirical average for safety margin.
#
# Expected impact: small (+0 to +3k). We're well into diminishing returns
# now — most of the structural alpha is captured in v6's PEBBLES/tail-MR
# changes. v7-v9 are progressively smaller refinements.
# ============================================================================
#
# Original v8 header below:
# Round 5 strategy — v8 (incremental refinement of v7, which scored 660,234.5)
#
# Single change vs v7: clean up the OWN_IMPULSE table.
#
# Cross-day stability check on Round 5 data revealed that 7 of v7's 12
# OWN_IMPULSE products have empirical β that flips signs across days. These
# coefficients were inherited from earlier rounds and the strategy was
# shifting fair value based on noise — in one case (PANEL_4X4) actively
# trading the wrong direction (v7 coef -1.0, empirical avg +0.19). Removing
# them removes a noise source without disturbing the 5 products where the
# signal is consistent across days.
#
# The 5 surviving products keep their v7 coefficients (which are 2-3x more
# aggressive than empirical median, but those are known-working values).
# Resist the urge to also recalibrate them in this version — single-axis
# changes are easier to attribute and revert.
#
# This is also the answer to the overfitting question raised after v7:
# the architecture is sound and PEBBLES alpha is structural, but inherited
# tables can drift out of calibration. v8 fixes one such drift.
# ============================================================================
#
# Original v7 header below:
# Round 5 strategy — v7 (incremental refinement of v6, which scored 655,261.5)
#
# v6 had a single tail-MR coefficient that fired at |last_ret| >= 20. Looking
# at the actual return distributions for the four MR products, three things
# stood out that weren't visible at the v5->v6 stage:
#
#   1. ROBOT_DISHES return distribution is sharply BIMODAL. Tail variance
#      breaks down as: (20,30] = 6%, (30,40] = 1%, (>40) = 94%. Empirical β
#      in (20,30] is essentially zero (-0.005), but β in (>40) is -0.296.
#      v6 was applying -0.28 across both regimes, over-fitting the no-signal
#      middle band on 778 ticks.
#
#   2. The other three MR products (IRONING, OXY_CHOC, OXY_EVE) have weaker
#      bimodality but still show meaningfully stronger β in the (>40) regime
#      (-0.27 to -0.29) than in (20,40] (-0.08 to -0.10).
#
#   3. CV-pair EWMA mean-reversion alpha keeps improving with faster alpha:
#      α=0.010 -> per-tick alpha 0.221
#      α=0.015 -> per-tick alpha 0.275 (+25%)
#      α=0.020 -> per-tick alpha 0.320 (+45%)
#      The 5-step horizon shows the same progression, so it's signal not
#      noise. Pushing α=0.015 captures most of the lift while staying safe.
#
# Three changes vs v6, all independent:
#
#   [F] ROBOT_DISHES tail-MR threshold raised: 20 -> 30. Avoids over-applying
#       the strong tail coefficient in the (20,30] no-signal band where empirical
#       β is essentially zero. Other three MR products keep threshold = 20
#       because their (20,30] band still has meaningful (~-0.08) β.
#
#   [G] Ultra-tail tier added: |last_ret| >= 40 triggers a stronger coefficient
#       that overrides tier 1. Coefs come straight from the >40 regression on
#       29,997 ticks: -0.30 (DISHES), -0.27 (IRONING), -0.29 (OXY_CHOC),
#       -0.29 (OXY_EVE). Fires on roughly 750 / 56 / 75 / 66 ticks per
#       product across 3 days.
#
#   [H] CV-pair EWMA tuned: alpha 0.01 -> 0.015 (faster tracking; per-tick
#       alpha +25%), coefficient 0.025 -> 0.030 to compensate for smaller
#       deviation magnitude (dev_std drops 11.0 -> 8.9).
#
#   [I] ROBOT_DISHES conditional caution gate aligned with new tier-1
#       threshold for consistency: |last_ret| < 30 keeps caution, otherwise
#       drops it. Previously was < 20.
#
# REJECTED ideas tested but not added:
#   - Multi-leg Snackpack regression (per-day coefs swing 5-15k, signs flip)
#   - Cross-product residuals for ROBOT/MICROCHIP/OXYGEN/etc (same instability)
#   - Alpha=0.02 CV EWMA (better but starts feeling overfit)
#   - MICROCHIP_OVAL ultra-tail (only n=76 samples, too thin)
# ============================================================================

LIMIT = 10
VOL_A = 0.08
FLOW_DECAY = 0.55
MARK_DECAY = 0.90
FAST_A = 0.10
SLOW_A = 0.035
CV_EWMA_A = 0.015   # [H] was 0.01 in v6

MICRO_GROUP = {
    'GALAXY': 1.4, 'MICROCHIP': 0.7, 'OXYGEN': 1.5, 'PANEL': 0.8,
    'PEBBLES': 1.0, 'ROBOT': 0.5, 'SLEEP': 1.4, 'SNACKPACK': 1.3,
    'TRANSLATOR': 0.6, 'UV': 1.5,
}
# [K] Per-product micro-tilt overrides. v8 used a single coefficient per
# group, but per-product empirical betas show that within most groups, ONE
# product responds 2-4x more strongly to microprice than the group average.
# Adding overrides only where (1) empirical β is ~2x+ the group coef,
# (2) sign is consistent across all 3 days, (3) cross-day swing is moderate.
# Coefficients = 70% of cross-day empirical average (safety margin).
# RECTANGLE override = 0 because empirical β is essentially noise (sign
# flips across days), so v8 was applying group coef of 0.7 to a non-signal.
MICRO_OVERRIDE = {
    'ROBOT_IRONING':         1.5,   # empirical avg β +2.15, days +2.23/+1.64/+2.58
    'TRANSLATOR_VOID_BLUE':  1.2,   # empirical avg β +1.71, days +1.13/+1.91/+2.08
    'PANEL_1X2':             1.0,   # empirical avg β +1.43, days +1.51/+1.65/+1.14
    'PANEL_2X4':             1.4,   # empirical avg β +1.99, days +1.82/+2.33/+1.83
    'MICROCHIP_RECTANGLE':   0.0,   # empirical avg β ~0, days -0.12/+0.01/+0.17 (noise)
}
MEANREV = {
    'ROBOT_DISHES': -0.20, 'ROBOT_IRONING': -0.11,
    'OXYGEN_SHAKE_EVENING_BREATH': -0.11, 'OXYGEN_SHAKE_CHOCOLATE': -0.08,
    'SNACKPACK_CHOCOLATE': -0.03, 'SNACKPACK_VANILLA': -0.03,
    'SNACKPACK_PISTACHIO': -0.025, 'SNACKPACK_RASPBERRY': -0.017,
    'SNACKPACK_STRAWBERRY': -0.014, 'MICROCHIP_SQUARE': -0.02,
}
# Tier-1 tail (unchanged from v6 except DISHES threshold)
TAIL_MEANREV_COEF = {
    'ROBOT_DISHES':                -0.28,
    'ROBOT_IRONING':               -0.21,
    'OXYGEN_SHAKE_CHOCOLATE':      -0.20,
    'OXYGEN_SHAKE_EVENING_BREATH': -0.22,
}
TAIL_RET_THRESHOLD = {
    'ROBOT_DISHES':                30,   # [F] was 20 in v6
    'ROBOT_IRONING':               20,
    'OXYGEN_SHAKE_CHOCOLATE':      20,
    'OXYGEN_SHAKE_EVENING_BREATH': 20,
}
# [G] Ultra-tail tier: jump-regime coefficients calibrated from the (>40)
# return bucket. Overrides tier 1 when |last_ret| >= ULTRA_TAIL_THRESHOLD.
ULTRA_TAIL_COEF = {
    'ROBOT_DISHES':                -0.30,
    'ROBOT_IRONING':               -0.27,
    'OXYGEN_SHAKE_CHOCOLATE':      -0.29,
    'OXYGEN_SHAKE_EVENING_BREATH': -0.29,
}
ULTRA_TAIL_THRESHOLD = 40

# [J] OWN_IMPULSE cleaned up vs v7. The cross-day stability check on Round 5
# data showed that 7 of v7's 12 OWN_IMPULSE products had betas that flip
# signs across days (i.e., the strategy was applying fair-value shifts based
# on noise from Round 4-tuned coefficients). Removed those 7 products.
# The remaining 5 have consistent signs across all 3 days; their v7
# coefficients are 2-3x more aggressive than empirical averages but I'm
# leaving them at v7 values since those are known to work in production.
OWN_IMPULSE = {
    'PEBBLES_M': 3.2,         # cross-day β: +1.52, +0.77, +1.54 (consistent +)
    'PEBBLES_XL': -3.2,       # cross-day β: -1.94, -1.13, -1.18 (consistent -)
    'ROBOT_MOPPING': 1.2,     # cross-day β: +0.44, +0.18, +0.67 (consistent +)
    'UV_VISOR_RED': 1.3,      # cross-day β: +1.28, +0.49, +0.14 (consistent +)
    'UV_VISOR_YELLOW': 1.2,   # cross-day β: +0.77, +0.84, +1.39 (well-calibrated)
    # REMOVED (sign flips → noise from Round 4 carryover):
    #   MICROCHIP_SQUARE, ROBOT_DISHES, ROBOT_LAUNDRY,
    #   MICROCHIP_RECTANGLE, PANEL_4X4, TRANSLATOR_VOID_BLUE, PANEL_1X2
}
GROUPS = {
    'GALAXY': ['GALAXY_SOUNDS_DARK_MATTER', 'GALAXY_SOUNDS_BLACK_HOLES', 'GALAXY_SOUNDS_PLANETARY_RINGS', 'GALAXY_SOUNDS_SOLAR_WINDS', 'GALAXY_SOUNDS_SOLAR_FLAMES'],
    'SLEEP': ['SLEEP_POD_SUEDE', 'SLEEP_POD_LAMB_WOOL', 'SLEEP_POD_POLYESTER', 'SLEEP_POD_NYLON', 'SLEEP_POD_COTTON'],
    'MICROCHIP': ['MICROCHIP_CIRCLE', 'MICROCHIP_OVAL', 'MICROCHIP_SQUARE', 'MICROCHIP_RECTANGLE', 'MICROCHIP_TRIANGLE'],
    'PEBBLES': ['PEBBLES_XS', 'PEBBLES_S', 'PEBBLES_M', 'PEBBLES_L', 'PEBBLES_XL'],
    'ROBOT': ['ROBOT_VACUUMING', 'ROBOT_MOPPING', 'ROBOT_DISHES', 'ROBOT_LAUNDRY', 'ROBOT_IRONING'],
    'UV': ['UV_VISOR_YELLOW', 'UV_VISOR_AMBER', 'UV_VISOR_ORANGE', 'UV_VISOR_RED', 'UV_VISOR_MAGENTA'],
    'TRANSLATOR': ['TRANSLATOR_SPACE_GRAY', 'TRANSLATOR_ASTRO_BLACK', 'TRANSLATOR_ECLIPSE_CHARCOAL', 'TRANSLATOR_GRAPHITE_MIST', 'TRANSLATOR_VOID_BLUE'],
    'PANEL': ['PANEL_1X2', 'PANEL_2X2', 'PANEL_1X4', 'PANEL_2X4', 'PANEL_4X4'],
    'OXYGEN': ['OXYGEN_SHAKE_MORNING_BREATH', 'OXYGEN_SHAKE_EVENING_BREATH', 'OXYGEN_SHAKE_MINT', 'OXYGEN_SHAKE_CHOCOLATE', 'OXYGEN_SHAKE_GARLIC'],
    'SNACKPACK': ['SNACKPACK_CHOCOLATE', 'SNACKPACK_VANILLA', 'SNACKPACK_PISTACHIO', 'SNACKPACK_STRAWBERRY', 'SNACKPACK_RASPBERRY'],
}
PROD_TO_GROUP = {p: g for g, ps in GROUPS.items() for p in ps}

# PEBBLES per-leg betas (XL was 0.08 in v5, fixed to 0.27 in v6, kept here)
PEBBLE_BETA = {
    'PEBBLES_XS': 0.17,
    'PEBBLES_S':  0.20,
    'PEBBLES_M':  0.18,
    'PEBBLES_L':  0.17,
    'PEBBLES_XL': 0.27,
}

PEB_NORMAL_COEF    = 0.06
PEB_TAIL_COEF      = 0.40
PEB_TAIL_THRESHOLD = 8.0
PEB_TAIL_TAKE_EDGE = 1.5
PEB_TAIL_MIN_SIZE  = 8

TAIL_MULT = {
    'ROBOT_DISHES': 2.4, 'ROBOT_IRONING': 2.0,
    'OXYGEN_SHAKE_CHOCOLATE': 2.1, 'OXYGEN_SHAKE_EVENING_BREATH': 2.1,
    'MICROCHIP_OVAL': 1.2, 'MICROCHIP_SQUARE': 1.15,
}

# [H] CV adjustment coefficient: bumped 0.025 -> 0.030 because the faster
# EWMA gives a smaller dev_std (8.9 vs 11.0); we want fair-shift magnitude
# to match the empirical predict_beta of 0.031.
CV_COEF = 0.030

GROUP_FLOW_COEF = {
    'GALAXY': 0.10, 'SLEEP': 0.06, 'MICROCHIP': 0.03, 'PEBBLES': 0.0,
    'ROBOT': 0.02, 'UV': 0.06, 'TRANSLATOR': 0.04, 'PANEL': 0.03,
    'OXYGEN': 0.05, 'SNACKPACK': 0.08,
}
# [L] Per-product group-flow overrides (same pattern as v9's MICRO_OVERRIDE).
# Within most groups, one product responds 5-15x more strongly to group-mean
# trade flow than the others, but v9 applied the same group coef to all 5.
# Selection criteria mirror v9's MICRO_OVERRIDE: (1) sign consistent across
# all 3 days, (2) cross-day swing/mean reasonable, (3) magnitude differs
# from group coef by enough to matter. Coefficients ~50% of empirical
# average for safety margin.
#
# MICROCHIP_OVAL is the dramatic case — v9 applied +0.03 (group coef) when
# empirical β is -0.70 on every single day, so the strategy was moving
# fair the wrong direction on every group-flow event.
#
# Pebbles overrides (PEBBLES_M, XL, L all show stable |β| > 0.6) deliberately
# omitted — group_flow may overlap with the basket-residual signal there.
# Cleaner to test non-Pebbles first.
GROUP_FLOW_OVERRIDE = {
    # v10 (kept unchanged):
    'UV_VISOR_YELLOW':       0.5,   # avg β +0.99, days +0.76/+0.86/+1.35
    'UV_VISOR_RED':          0.3,   # avg β +0.64, days +1.27/+0.48/+0.17
    'OXYGEN_SHAKE_GARLIC':   0.3,   # avg β +0.57, days +0.65/+0.61/+0.43
    'MICROCHIP_OVAL':       -0.3,   # avg β -0.70, days -0.75/-0.72/-0.62
    # [M] v11 additions: Pebbles overrides. Empirical signals here are LARGER
    # than anything we've calibrated yet. Held back from v10 over concern
    # they'd overlap with the basket-residual signal, but the structural
    # logic argues they're orthogonal:
    #   - Basket signal fires when sum != 50000 (one leg mispriced)
    #   - Group flow fires when there's broad buying/selling across all 5 legs
    # The XL beta being NEGATIVE to group flow (-1.41) makes sense: when the
    # whole basket sees broad buying, the basket sum tends up; XL (the
    # dispersing leg) gets pushed down by the sum-to-50000 constraint.
    # That's the opposite direction from XL's basket-residual β (+0.27),
    # so the two signals fire in different scenarios and can be additive.
    'PEBBLES_M':             0.6,   # avg β +1.28, days +1.52/+0.77/+1.53
    'PEBBLES_XL':           -0.7,   # avg β -1.41, days -1.98/-1.08/-1.18 (neg, very stable)
    'PEBBLES_L':             0.3,   # avg β +0.66, days +0.62/+0.50/+0.87 (very stable)
}
STALE_PRODUCTS = {
    'GALAXY_SOUNDS_DARK_MATTER',
    'GALAXY_SOUNDS_PLANETARY_RINGS',
    'SLEEP_POD_LAMB_WOOL',
    'PANEL_1X2',
    'UV_VISOR_YELLOW',
}


def group_of(p: str) -> str:
    return PROD_TO_GROUP.get(p, 'OTHER')


def infer_side(trade_price: int, best_bid: int, best_ask: int, mid: float) -> float:
    db = abs(trade_price - best_bid)
    da = abs(trade_price - best_ask)
    if da < db: return 1.0
    if db < da: return -1.0
    return 1.0 if trade_price >= mid else -1.0


def own_signed_qty(tr) -> int:
    buyer = getattr(tr, 'buyer', '')
    seller = getattr(tr, 'seller', '')
    q = int(getattr(tr, 'quantity', 0))
    if buyer == 'SUBMISSION': return q
    if seller == 'SUBMISSION': return -q
    return q


def clip(x: float, lo: float, hi: float) -> float:
    if x < lo: return lo
    if x > hi: return hi
    return x


def sanitize_orders(product: str, start_pos: int, raw_orders: List[Order]) -> List[Order]:
    buys  = sorted([o for o in raw_orders if o.quantity > 0], key=lambda o: o.price, reverse=True)
    sells = sorted([o for o in raw_orders if o.quantity < 0], key=lambda o: o.price)
    out: List[Order] = []
    buy_cap  = max(0, LIMIT - start_pos)
    sell_cap = max(0, LIMIT + start_pos)
    used = 0
    for o in buys:
        qty = min(o.quantity, buy_cap - used)
        if qty > 0:
            out.append(Order(product, o.price, qty))
            used += qty
    used = 0
    for o in sells:
        qty = min(-o.quantity, sell_cap - used)
        if qty > 0:
            out.append(Order(product, o.price, -qty))
            used += qty
    return out


class Trader:
    def run(self, state: TradingState):
        try:
            saved = json.loads(state.traderData) if state.traderData else {}
        except Exception:
            saved = {}
        prev_mid:  Dict[str, float] = saved.get('prev_mid', {})
        own_sig:   Dict[str, float] = saved.get('own_sig', {})
        vol:       Dict[str, float] = saved.get('vol', {})
        buy_mark:  Dict[str, float] = saved.get('buy_mark', {})
        sell_mark: Dict[str, float] = saved.get('sell_mark', {})
        ema_fast:  Dict[str, float] = saved.get('ema_fast', {})
        ema_slow:  Dict[str, float] = saved.get('ema_slow', {})
        pos_age:   Dict[str, int]   = saved.get('pos_age', {})
        prev_pos:  Dict[str, int]   = saved.get('prev_pos', {})
        ewma_cv:   float            = saved.get('ewma_cv', None)

        for k in list(own_sig.keys()):
            own_sig[k] *= FLOW_DECAY
            if abs(own_sig[k]) < 0.05:
                own_sig.pop(k, None)
        for k in list(buy_mark.keys()):  buy_mark[k]  *= MARK_DECAY
        for k in list(sell_mark.keys()): sell_mark[k] *= MARK_DECAY

        current_mid: Dict[str, float] = {}
        top: Dict[str, tuple] = {}
        trend: Dict[str, float] = {}
        for product, od in state.order_depths.items():
            if od.buy_orders and od.sell_orders:
                best_bid = max(od.buy_orders)
                best_ask = min(od.sell_orders)
                bid_vol = od.buy_orders[best_bid]
                ask_vol = -od.sell_orders[best_ask]
                mid = 0.5 * (best_bid + best_ask)
                current_mid[product] = mid
                top[product] = (best_bid, bid_vol, best_ask, ask_vol, mid)
                ret = mid - prev_mid.get(product, mid)
                v = vol.get(product, abs(ret))
                vol[product] = (1.0 - VOL_A) * v + VOL_A * abs(ret)
                ef = ema_fast.get(product, mid)
                es = ema_slow.get(product, mid)
                ef = ef + FAST_A * (mid - ef)
                es = es + SLOW_A * (mid - es)
                ema_fast[product] = ef
                ema_slow[product] = es
                trend[product] = ef - es

        for p in current_mid:
            pos = state.position.get(p, 0)
            pp = prev_pos.get(p, 0)
            if pos == 0:
                pos_age[p] = 0
            elif pp == 0 or pos * pp <= 0:
                pos_age[p] = 1
            else:
                pos_age[p] = min(50, pos_age.get(p, 0) + 1)
            prev_pos[p] = pos

        for product, trades in state.own_trades.items():
            if product not in current_mid: continue
            mid = current_mid[product]
            for tr in trades:
                sq = own_signed_qty(tr)
                if sq > 0:
                    buy_mark[product] = clip(buy_mark.get(product, 0.0) + 0.12 * (mid - tr.price), -6.0, 6.0)
                elif sq < 0:
                    sell_mark[product] = clip(sell_mark.get(product, 0.0) + 0.12 * (tr.price - mid), -6.0, 6.0)

        for product, trades in state.market_trades.items():
            if product not in top or not trades: continue
            best_bid, bid_vol, best_ask, ask_vol, mid = top[product]
            ssum = 0.0
            n = 0
            for tr in trades:
                ssum += infer_side(tr.price, best_bid, best_ask, mid)
                n += 1
            if n:
                own_sig[product] = clip(own_sig.get(product, 0.0) + ssum / n, -4.0, 4.0)

        group_flow = {g: 0.0 for g in GROUPS}
        group_count = {g: 0 for g in GROUPS}
        for p in current_mid:
            g = group_of(p)
            group_flow[g] += own_sig.get(p, 0.0)
            group_count[g] += 1
        for g in GROUPS:
            group_flow[g] /= max(1, group_count[g])

        peb_resid = 0.0
        peb_arb_mode = False
        if all(p in current_mid for p in GROUPS['PEBBLES']):
            peb_resid = 50000.0 - sum(current_mid[p] for p in GROUPS['PEBBLES'])
            peb_arb_mode = abs(peb_resid) >= PEB_TAIL_THRESHOLD

        cv_resid = 0.0
        if all(p in current_mid for p in ('SNACKPACK_CHOCOLATE', 'SNACKPACK_VANILLA')):
            cv_sum = current_mid['SNACKPACK_CHOCOLATE'] + current_mid['SNACKPACK_VANILLA']
            if ewma_cv is None:
                ewma_cv = cv_sum
            else:
                ewma_cv = (1.0 - CV_EWMA_A) * ewma_cv + CV_EWMA_A * cv_sum
            cv_resid = ewma_cv - cv_sum

        orders: Dict[str, List[Order]] = {}
        for product, od in state.order_depths.items():
            if product not in top:
                orders[product] = []
                continue
            best_bid, bid_vol, best_ask, ask_vol, mid = top[product]
            spread = best_ask - best_bid
            start_pos = state.position.get(product, 0)
            pos = start_pos
            grp = group_of(product)
            micro = (best_ask * bid_vol + best_bid * ask_vol) / max(1, bid_vol + ask_vol)
            micro_sig = micro - mid
            last_ret = mid - prev_mid.get(product, mid)
            sigma = max(1.0, vol.get(product, 1.0))
            scale = max(1.0, sigma, 0.5 * spread)
            tail = TAIL_MULT.get(product, 1.0)
            age = pos_age.get(product, 0)
            tscore = clip(trend.get(product, 0.0) / scale, -3.0, 3.0)

            fair = mid
            # [K] Use per-product override if present, else fall back to group coef
            mic_coef = MICRO_OVERRIDE[product] if product in MICRO_OVERRIDE else MICRO_GROUP.get(grp, 0.0)
            fair += mic_coef * micro_sig

            # [F][G] Two-tier tail-aware mean reversion. Tier 2 (>=40) overrides
            # Tier 1 when both conditions are met. Threshold for DISHES Tier 1
            # raised to 30 to skip the no-signal middle band.
            mr_coef = MEANREV.get(product, 0.0)
            abs_ret = abs(last_ret)
            if product in TAIL_MEANREV_COEF and abs_ret >= TAIL_RET_THRESHOLD[product]:
                mr_coef = TAIL_MEANREV_COEF[product]
            if product in ULTRA_TAIL_COEF and abs_ret >= ULTRA_TAIL_THRESHOLD:
                mr_coef = ULTRA_TAIL_COEF[product]
            fair += mr_coef * last_ret

            fair += OWN_IMPULSE.get(product, 0.0) * own_sig.get(product, 0.0)
            # [L] Use per-product group-flow override if present, else group coef
            gf_coef = GROUP_FLOW_OVERRIDE[product] if product in GROUP_FLOW_OVERRIDE else GROUP_FLOW_COEF.get(grp, 0.0)
            fair += gf_coef * group_flow.get(grp, 0.0)

            if product in PEBBLE_BETA:
                coef = PEB_TAIL_COEF if peb_arb_mode else PEB_NORMAL_COEF
                fair += coef * PEBBLE_BETA[product] * peb_resid
            elif product in ('SNACKPACK_CHOCOLATE', 'SNACKPACK_VANILLA'):
                fair += CV_COEF * 0.5 * cv_resid

            buy_ok = True
            sell_ok = True
            qs: List[Order] = []
            if product in STALE_PRODUCTS and age >= 26:
                if start_pos > 0 and tscore < -1.35:
                    buy_ok = False
                    fair -= 0.08 * scale
                elif start_pos < 0 and tscore > 1.35:
                    sell_ok = False
                    fair += 0.08 * scale

            reserve = fair - 0.70 * pos
            mm_edge = 1.0 if spread >= 4 else 0.5
            mm_edge += 0.03 * min(5.0, sigma / max(1.0, 0.5 * spread))
            take_edge = max(2.0, 0.20 * spread + 0.12 * sigma * tail)

            if product in PEBBLE_BETA and peb_arb_mode:
                take_edge = PEB_TAIL_TAKE_EDGE

            buy_tox = max(0.0, -buy_mark.get(product, 0.0))
            sell_tox = max(0.0, -sell_mark.get(product, 0.0))
            bid_edge = mm_edge + 0.08 * buy_tox
            ask_edge = mm_edge + 0.08 * sell_tox
            if product in STALE_PRODUCTS and age >= 26 and start_pos > 0 and tscore < -1.35:
                bid_edge += 0.18
            elif product in STALE_PRODUCTS and age >= 26 and start_pos < 0 and tscore > 1.35:
                ask_edge += 0.18

            # [I] ROBOT_DISHES caution gate raised 20 -> 30 to align with the
            # new tier-1 tail-MR threshold for DISHES. Below the threshold,
            # base MR (-0.20) applies and we want full defensive posture.
            # Above it, tier-1 (-0.28) or ultra-tail (-0.30) fires and we
            # want the contrarian take to be unimpeded.
            if product == 'ROBOT_DISHES':
                if abs(last_ret) < 30:
                    take_edge += 0.70
                    bid_edge  += 0.24 + 0.10 * buy_tox
                    ask_edge  += 0.24 + 0.10 * sell_tox
                else:
                    bid_edge  += 0.10 * buy_tox
                    ask_edge  += 0.10 * sell_tox
                if buy_tox  > 0.80 and start_pos >= 0: buy_ok = False
                if sell_tox > 0.80 and start_pos <= 0: sell_ok = False

            if best_ask <= reserve - take_edge and pos < LIMIT:
                qty = min(LIMIT - pos, ask_vol)
                if qty > 0:
                    qs.append(Order(product, best_ask, qty))
                    pos += qty
            if best_bid >= reserve + take_edge and pos > -LIMIT:
                qty = min(LIMIT + pos, bid_vol)
                if qty > 0:
                    qs.append(Order(product, best_bid, -qty))
                    pos -= qty

            buy_cap  = LIMIT - pos
            sell_cap = LIMIT + pos
            buy_quote  = min(best_bid + 1 if spread >= 2 else best_bid,
                             math.floor(reserve - bid_edge))
            sell_quote = max(best_ask - 1 if spread >= 2 else best_ask,
                             math.ceil(reserve + ask_edge))
            size = 4
            if grp in ('SNACKPACK', 'SLEEP', 'MICROCHIP', 'PEBBLES'):
                size = 5
            if tail > 2.0:
                size = min(size, 4)
            if sigma > 2.5 * max(1.0, 0.5 * spread):
                size = max(3, size - 1)
            if product == 'ROBOT_DISHES':
                size = min(size, 3)
            if product in PEBBLE_BETA and peb_arb_mode:
                size = max(size, PEB_TAIL_MIN_SIZE)

            if buy_cap > 0 and buy_ok and buy_quote < best_ask:
                qs.append(Order(product, int(buy_quote), min(size, buy_cap)))
            if sell_cap > 0 and sell_ok and sell_quote > best_bid:
                qs.append(Order(product, int(sell_quote), -min(size, sell_cap)))
            orders[product] = sanitize_orders(product, start_pos, qs)

        traderData = json.dumps({
            'prev_mid': current_mid,
            'own_sig': own_sig,
            'vol': vol,
            'buy_mark': buy_mark,
            'sell_mark': sell_mark,
            'ema_fast': ema_fast,
            'ema_slow': ema_slow,
            'pos_age': pos_age,
            'prev_pos': prev_pos,
            'ewma_cv': ewma_cv,
        }, separators=(',', ':'))
        return orders, 0, traderData