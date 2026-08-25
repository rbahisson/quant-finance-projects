import json
import jsonpickle
from typing import Any, Dict, List, Tuple, Optional

from datamodel import OrderDepth, TradingState, Order, Symbol, Listing, Trade, Observation, ProsperityEncoder


# =========================================================
# LOGGER
# =========================================================
class Logger:
    def __init__(self) -> None:
        self.logs = ""
        self.max_log_length = 3750

    def print(self, *objects: Any, sep: str = " ", end: str = "\n") -> None:
        self.logs += sep.join(map(str, objects)) + end

    def flush(
        self,
        state: TradingState,
        orders: Dict[Symbol, List[Order]],
        conversions: int,
        trader_data: str,
    ) -> None:
        base_length = len(
            self.to_json(
                [
                    self.compress_state(state, ""),
                    self.compress_orders(orders),
                    conversions,
                    "",
                    "",
                ]
            )
        )

        max_item_length = max(0, (self.max_log_length - base_length) // 3)

        print(
            self.to_json(
                [
                    self.compress_state(
                        state, self.truncate(state.traderData, max_item_length)
                    ),
                    self.compress_orders(orders),
                    conversions,
                    self.truncate(trader_data, max_item_length),
                    self.truncate(self.logs, max_item_length),
                ]
            )
        )

        self.logs = ""

    def compress_state(self, state: TradingState, trader_data: str) -> list[Any]:
        return [
            state.timestamp,
            trader_data,
            self.compress_listings(state.listings),
            self.compress_order_depths(state.order_depths),
            self.compress_trades(state.own_trades),
            self.compress_trades(state.market_trades),
            state.position,
            self.compress_observations(state.observations),
        ]

    def compress_listings(self, listings: dict[Symbol, Listing]) -> list[list[Any]]:
        return [[listing.symbol, listing.product, listing.denomination] for listing in listings.values()]

    def compress_order_depths(
        self, order_depths: dict[Symbol, OrderDepth]
    ) -> dict[Symbol, list[Any]]:
        return {
            symbol: [order_depth.buy_orders, order_depth.sell_orders]
            for symbol, order_depth in order_depths.items()
        }

    def compress_trades(self, trades: dict[Symbol, list[Trade]]) -> list[list[Any]]:
        out = []
        for arr in trades.values():
            for trade in arr:
                out.append(
                    [
                        trade.symbol,
                        trade.price,
                        trade.quantity,
                        trade.buyer,
                        trade.seller,
                        trade.timestamp,
                    ]
                )
        return out

    def compress_observations(self, observations: Observation) -> list[Any]:
        conversion_observations = {}
        for product, observation in observations.conversionObservations.items():
            conversion_observations[product] = [
                observation.bidPrice,
                observation.askPrice,
                observation.transportFees,
                observation.exportTariff,
                observation.importTariff,
                observation.sugarPrice,
                observation.sunlightIndex,
            ]
        return [observations.plainValueObservations, conversion_observations]

    def compress_orders(self, orders: dict[Symbol, list[Order]]) -> list[list[Any]]:
        out = []
        for arr in orders.values():
            for order in arr:
                out.append([order.symbol, order.price, order.quantity])
        return out

    def to_json(self, value: Any) -> str:
        return json.dumps(value, cls=ProsperityEncoder, separators=(",", ":"))

    def truncate(self, value: str, max_length: int) -> str:
        if max_length <= 3:
            return value[:max_length]
        if len(value) <= max_length:
            return value
        return value[: max_length - 3] + "..."


logger = Logger()


# =========================================================
# TRADER
# =========================================================
class Trader:
    PEPPER = "INTARIAN_PEPPER_ROOT"
    OSMIUM = "ASH_COATED_OSMIUM"

    POSITION_LIMITS = {
        PEPPER: 80,
        OSMIUM: 80,
    }

    # -------------------------
    # ACO / OSMIUM PARAMETERS
    # -------------------------
    ACO_ANCHOR = 10_000.0
    ACO_EMA_ALPHA = 0.06

    ACO_W_EMA = 0.55
    ACO_W_MICRO = 0.25
    ACO_W_ANCHOR = 0.20
    ACO_MOM_PENALTY = 0.15

    ACO_IMB_WEIGHT = 2

    ACO_BASE_SIZE = 24
    ACO_MAX_SIZE = 38
    ACO_SECOND_SIZE = 14
    ACO_MIN_SIZE = 8
    ACO_INV_SHRINK = 0.55

    ACO_RISK_AVERSION = 0.035
    ACO_SPREAD_HALF = 1.5
    ACO_INSIDE_TICKS = 1
    ACO_TAKE_THRESHOLD = 1.5
    ACO_SECOND_LAYER_MIN_SPREAD = 6

    # -------------------------
    # PEPPER PARAMETERS
    # -------------------------
    HISTORICAL_MEAN_SLOPE = (0.0010010482 + 0.0010085544 + 0.0010328491) / 3.0

    INITIAL_SWITCH_TICK = 50
    RECALC_EVERY = 50
    ROLLING_WINDOW = 80

    EARLY_MIN_POSITION = 80
    EARLY_PHASE_TICKS = 50
    EARLY_MAX_ASK_EDGE_BPS = 9.5
    EARLY_FORCE_FILL = True

    ENTRY_LADDER = [
        (6.0, 0.25),
        (5.0, 0.50),
        (4.0, 0.65),
        (3.0, 0.80),
        (2.0, 1.00),
    ]

    EXIT_LADDER = [
        (7.0, 0.25),
        (8.5, 0.50),
        (10.0, 0.65),
        (11.5, 0.80),
        (12.5, 1.00),
    ]

    PASSIVE_BID_SIZE = 15
    PASSIVE_ASK_SIZE = 15

    def __init__(self):
        pass

    # -----------------------------------------------------
    # state helpers
    # -----------------------------------------------------
    def _empty_state(self) -> Dict[str, Any]:
        return {
            self.PEPPER: {
                "day_start_ts": None,
                "day_index": 0,
                "timestamps": [],
                "mids": [],
                "current_slope": self.HISTORICAL_MEAN_SLOPE,
                "current_intercept": None,
                "fair_value": None,
            },
            self.OSMIUM: {
                "ema": None,
                "last_mid": None,
                "anchor": self.ACO_ANCHOR,
            },
        }

    def _load_trader_data(self, raw: str) -> Dict[str, Any]:
        default_state = self._empty_state()
        if not raw:
            return default_state

        # First try jsonpickle (used by the PEPPER strategy)
        try:
            data = jsonpickle.decode(raw)
            if isinstance(data, dict):
                if self.PEPPER not in data:
                    data[self.PEPPER] = default_state[self.PEPPER]
                if self.OSMIUM not in data:
                    data[self.OSMIUM] = default_state[self.OSMIUM]
                return data
        except Exception:
            pass

        # Fallback to plain json (used by the original ACO strategy)
        try:
            data = json.loads(raw)
            if isinstance(data, dict):
                if self.PEPPER not in data:
                    data[self.PEPPER] = default_state[self.PEPPER]
                if self.OSMIUM not in data:
                    data[self.OSMIUM] = default_state[self.OSMIUM]
                return data
        except Exception:
            pass

        return default_state

    def _is_new_day(self, pepper_state: Dict[str, Any], timestamp: int) -> bool:
        if pepper_state["day_start_ts"] is None:
            return True
        return timestamp < pepper_state["day_start_ts"]

    # -----------------------------------------------------
    # market helpers
    # -----------------------------------------------------
    def _best_bid_ask(self, order_depth: OrderDepth) -> Tuple[Optional[int], Optional[int]]:
        best_bid = max(order_depth.buy_orders.keys()) if order_depth.buy_orders else None
        best_ask = min(order_depth.sell_orders.keys()) if order_depth.sell_orders else None
        return best_bid, best_ask

    def _best_prices_with_vol(self, depth: OrderDepth) -> Tuple[Optional[int], int, Optional[int], int]:
        best_bid = max(depth.buy_orders.keys()) if depth.buy_orders else None
        best_ask = min(depth.sell_orders.keys()) if depth.sell_orders else None
        bid_vol = depth.buy_orders[best_bid] if best_bid is not None else 0
        ask_vol = -depth.sell_orders[best_ask] if best_ask is not None else 0
        return best_bid, bid_vol, best_ask, ask_vol

    def _mid_price(self, order_depth: OrderDepth) -> Optional[float]:
        best_bid, best_ask = self._best_bid_ask(order_depth)
        if best_bid is None or best_ask is None:
            return None
        return (best_bid + best_ask) / 2.0

    def _fit_line(self, x: List[float], y: List[float]) -> Optional[Tuple[float, float]]:
        if len(x) < 2 or len(y) < 2:
            return None

        n = len(x)
        sx = sum(x)
        sy = sum(y)
        sxx = sum(v * v for v in x)
        sxy = sum(a * b for a, b in zip(x, y))
        denom = n * sxx - sx * sx

        if abs(denom) < 1e-12:
            return None

        slope = (n * sxy - sx * sy) / denom
        intercept = (sy - slope * sx) / n
        return slope, intercept

    def _microprice(self, bid: int, bid_vol: int, ask: int, ask_vol: int, fallback: float) -> float:
        total = bid_vol + ask_vol
        if total <= 0:
            return fallback
        return (bid * ask_vol + ask * bid_vol) / total

    def _add_buy(self, orders: List[Order], product: str, price: int, qty: int, budget: int) -> int:
        q = min(qty, budget)
        if q > 0:
            orders.append(Order(product, int(price), int(q)))
            budget -= q
        return budget

    def _add_sell(self, orders: List[Order], product: str, price: int, qty: int, budget: int) -> int:
        q = min(qty, budget)
        if q > 0:
            orders.append(Order(product, int(price), -int(q)))
            budget -= q
        return budget

    # -----------------------------------------------------
    # PEPPER fair update
    # -----------------------------------------------------
    def _update_pepper_fair(
        self,
        state: TradingState,
        pepper_state: Dict[str, Any],
    ) -> Optional[float]:
        if self.PEPPER not in state.order_depths:
            return pepper_state.get("fair_value", None)

        timestamp = state.timestamp
        order_depth = state.order_depths[self.PEPPER]
        mid = self._mid_price(order_depth)

        if mid is None:
            return pepper_state.get("fair_value", None)

        if self._is_new_day(pepper_state, timestamp):
            pepper_state["day_start_ts"] = timestamp
            pepper_state["day_index"] = 0
            pepper_state["timestamps"] = []
            pepper_state["mids"] = []
            pepper_state["current_slope"] = self.HISTORICAL_MEAN_SLOPE
            pepper_state["current_intercept"] = mid - pepper_state["current_slope"] * timestamp
            pepper_state["fair_value"] = mid

        pepper_state["timestamps"].append(float(timestamp))
        pepper_state["mids"].append(float(mid))
        pepper_state["day_index"] += 1

        day_index = pepper_state["day_index"]

        if day_index == self.INITIAL_SWITCH_TICK:
            xs = pepper_state["timestamps"][: self.INITIAL_SWITCH_TICK]
            ys = pepper_state["mids"][: self.INITIAL_SWITCH_TICK]
            fitted = self._fit_line(xs, ys)
            if fitted is not None:
                pepper_state["current_slope"], pepper_state["current_intercept"] = fitted

        elif day_index > self.INITIAL_SWITCH_TICK and (
            (day_index - self.INITIAL_SWITCH_TICK) % self.RECALC_EVERY == 0
        ):
            xs = pepper_state["timestamps"][-self.ROLLING_WINDOW:]
            ys = pepper_state["mids"][-self.ROLLING_WINDOW:]
            fitted = self._fit_line(xs, ys)
            if fitted is not None:
                pepper_state["current_slope"], pepper_state["current_intercept"] = fitted

        if pepper_state["current_intercept"] is None:
            pepper_state["current_intercept"] = mid - pepper_state["current_slope"] * timestamp

        fair_value = (
            pepper_state["current_slope"] * timestamp + pepper_state["current_intercept"]
        )
        pepper_state["fair_value"] = fair_value
        return fair_value

    # -----------------------------------------------------
    # PEPPER ladder logic
    # -----------------------------------------------------
    def _entry_target_position(self, ask_edge_bps: float, limit: int) -> int:
        target = 0
        for threshold, frac in self.ENTRY_LADDER:
            if ask_edge_bps <= threshold:
                target = max(target, int(round(frac * limit)))
        return target

    def _exit_target_position(self, bid_edge_bps: float, current_pos: int, limit: int) -> int:
        if current_pos <= 0:
            return current_pos

        target = current_pos
        for threshold, frac in self.EXIT_LADDER:
            if bid_edge_bps >= threshold:
                keep_frac = max(0.0, 1.0 - frac)
                target = min(target, int(round(keep_frac * limit)))
        return target

    def _sell_take_ratio(self, bid_edge_bps: float) -> float:
        if bid_edge_bps >= 12.5:
            return 1.00
        if bid_edge_bps >= 11.5:
            return 1.00
        if bid_edge_bps >= 10.0:
            return 1.00
        if bid_edge_bps >= 8.5:
            return 0.45
        if bid_edge_bps >= 7.0:
            return 0.25
        return 0.0

    # -----------------------------------------------------
    # PEPPER strategy
    # -----------------------------------------------------
    def _pepper_orders(
        self,
        state: TradingState,
        pepper_state: Dict[str, Any],
    ) -> List[Order]:
        orders: List[Order] = []

        if self.PEPPER not in state.order_depths:
            return orders

        order_depth = state.order_depths[self.PEPPER]
        current_position = state.position.get(self.PEPPER, 0)
        limit = self.POSITION_LIMITS[self.PEPPER]

        best_bid, best_ask = self._best_bid_ask(order_depth)
        fair = pepper_state.get("fair_value", None)

        if best_bid is None or best_ask is None or fair is None:
            return orders

        bid_edge_bps = (best_bid - fair) / fair * 10_000
        ask_edge_bps = (best_ask - fair) / fair * 10_000

        simulated_position = current_position
        day_index = pepper_state["day_index"]

        # 0) EARLY BOOTSTRAP INVENTORY
        if day_index <= self.EARLY_PHASE_TICKS and simulated_position < self.EARLY_MIN_POSITION:
            available_ask = abs(order_depth.sell_orders.get(best_ask, 0))
            qty_missing = self.EARLY_MIN_POSITION - simulated_position

            if available_ask > 0 and qty_missing > 0:
                if ask_edge_bps <= self.EARLY_MAX_ASK_EDGE_BPS:
                    buy_qty = min(qty_missing, available_ask)
                else:
                    buy_qty = min(5, qty_missing, available_ask)

                if buy_qty > 0:
                    orders.append(Order(self.PEPPER, best_ask, buy_qty))
                    simulated_position += buy_qty

        # 1) EXIT LONGS FIRST
        exit_target = self._exit_target_position(bid_edge_bps, simulated_position, limit)
        qty_to_sell = max(0, simulated_position - exit_target)

        if qty_to_sell > 0:
            available_bid = order_depth.buy_orders.get(best_bid, 0)
            ratio = self._sell_take_ratio(bid_edge_bps)

            if ratio > 0 and available_bid > 0:
                sell_cap = max(1, int(round(available_bid * ratio)))
                sell_qty = min(qty_to_sell, sell_cap)

                if sell_qty > 0:
                    orders.append(Order(self.PEPPER, best_bid, -sell_qty))
                    simulated_position -= sell_qty

        # 2) ENTER / ADD LONG
        entry_target = self._entry_target_position(ask_edge_bps, limit)
        qty_to_buy = max(0, entry_target - simulated_position)

        if qty_to_buy > 0:
            available_ask = abs(order_depth.sell_orders.get(best_ask, 0))
            buy_qty = min(qty_to_buy, available_ask)
            if buy_qty > 0:
                orders.append(Order(self.PEPPER, best_ask, buy_qty))
                simulated_position += buy_qty

        # 3) PASSIVE QUOTES
        passive_bid = best_bid + 1
        passive_ask = best_ask - 1

        if passive_bid < fair and simulated_position < int(0.75 * limit):
            buy_cap = limit - simulated_position
            qty = min(self.PASSIVE_BID_SIZE, buy_cap)
            if qty > 0:
                orders.append(Order(self.PEPPER, passive_bid, qty))

        if simulated_position > 0 and passive_ask > fair:
            qty = min(self.PASSIVE_ASK_SIZE, simulated_position)
            if qty > 0:
                orders.append(Order(self.PEPPER, passive_ask, -qty))

        logger.print(
            f"PEPPER ts={state.timestamp} "
            f"idx={day_index} pos={current_position} sim_pos={simulated_position} "
            f"fair={fair:.2f} bid={best_bid} ask={best_ask} "
            f"bid_edge={bid_edge_bps:.2f} ask_edge={ask_edge_bps:.2f} "
            f"slope={pepper_state['current_slope']:.8f}"
        )

        return orders

    # -----------------------------------------------------
    # ACO / OSMIUM strategy
    # -----------------------------------------------------
    def _osmium_orders(
        self,
        state: TradingState,
        depth: OrderDepth,
        osmium_state: Dict[str, Any],
    ) -> List[Order]:
        product = self.OSMIUM
        orders: List[Order] = []
        limit = self.POSITION_LIMITS[product]
        pos = state.position.get(product, 0)

        buy_budget = limit - pos
        sell_budget = limit + pos

        best_bid, bid_vol, best_ask, ask_vol = self._best_prices_with_vol(depth)

        if best_bid is None and best_ask is None:
            return orders

        if best_bid is not None and best_ask is not None:
            mid = (best_bid + best_ask) / 2.0
            micro = self._microprice(
                best_bid,
                bid_vol,
                best_ask,
                ask_vol,
                osmium_state["ema"] if osmium_state["ema"] is not None else mid,
            )
        elif best_bid is not None:
            mid = float(best_bid)
            micro = mid
        else:
            mid = float(best_ask)
            micro = mid

        if osmium_state["anchor"] is None:
            osmium_state["anchor"] = mid
        if osmium_state["ema"] is None:
            osmium_state["ema"] = mid
        if osmium_state["last_mid"] is None:
            osmium_state["last_mid"] = mid

        anchor = osmium_state["anchor"]
        prev_ema = osmium_state["ema"]
        ema = self.ACO_EMA_ALPHA * micro + (1 - self.ACO_EMA_ALPHA) * prev_ema
        osmium_state["ema"] = ema

        last_mid = osmium_state["last_mid"]
        move = mid - last_mid
        osmium_state["last_mid"] = mid

        fair = (
            self.ACO_W_EMA * ema
            + self.ACO_W_MICRO * micro
            + self.ACO_W_ANCHOR * anchor
            - self.ACO_MOM_PENALTY * move
        )

        if best_bid is not None and best_ask is not None:
            total_vol = bid_vol + ask_vol
            if total_vol > 0:
                imbalance = (bid_vol - ask_vol) / total_vol
                fair += imbalance * self.ACO_IMB_WEIGHT

        skew = pos * self.ACO_RISK_AVERSION
        reservation = fair - skew

        # Aggressive taking: buy cheap asks
        for px in sorted(depth.sell_orders.keys()):
            if px >= fair - self.ACO_TAKE_THRESHOLD:
                break
            vol = -depth.sell_orders[px]
            qty = min(vol, buy_budget)
            if qty > 0:
                buy_budget = self._add_buy(orders, product, px, qty, buy_budget)

        # Aggressive taking: sell rich bids
        for px in sorted(depth.buy_orders.keys(), reverse=True):
            if px <= fair + self.ACO_TAKE_THRESHOLD:
                break
            vol = depth.buy_orders[px]
            qty = min(vol, sell_budget)
            if qty > 0:
                sell_budget = self._add_sell(orders, product, px, qty, sell_budget)

        if best_bid is None or best_ask is None:
            return orders

        spread = best_ask - best_bid

        raw_bid = int(round(reservation - self.ACO_SPREAD_HALF))
        raw_ask = int(round(reservation + self.ACO_SPREAD_HALF))

        if spread >= 4:
            bid_px = min(raw_bid, best_bid + self.ACO_INSIDE_TICKS)
            ask_px = max(raw_ask, best_ask - self.ACO_INSIDE_TICKS)
        else:
            bid_px = min(raw_bid, best_bid)
            ask_px = max(raw_ask, best_ask)

        if bid_px >= ask_px:
            bid_px = ask_px - 1

        inv_ratio = abs(pos) / limit
        shrink = 1.0 - self.ACO_INV_SHRINK * inv_ratio
        size = max(self.ACO_MIN_SIZE, int(round(self.ACO_BASE_SIZE * shrink)))

        buy_size = min(size, buy_budget, self.ACO_MAX_SIZE)
        sell_size = min(size, sell_budget, self.ACO_MAX_SIZE)

        if buy_size > 0:
            buy_budget = self._add_buy(orders, product, bid_px, buy_size, buy_budget)

        if sell_size > 0:
            sell_budget = self._add_sell(orders, product, ask_px, sell_size, sell_budget)

        if spread >= self.ACO_SECOND_LAYER_MIN_SPREAD:
            buy2 = min(self.ACO_SECOND_SIZE, buy_budget)
            sell2 = min(self.ACO_SECOND_SIZE, sell_budget)

            if buy2 > 0:
                buy_budget = self._add_buy(orders, product, bid_px - 1, buy2, buy_budget)

            if sell2 > 0:
                sell_budget = self._add_sell(orders, product, ask_px + 1, sell2, sell_budget)

        logger.print(
            f"OSMIUM ts={state.timestamp} pos={pos} fair={fair:.2f} "
            f"res={reservation:.2f} bid={best_bid} ask={best_ask} "
            f"ema={ema:.2f} micro={micro:.2f}"
        )

        return orders

    # -----------------------------------------------------
    # main
    # -----------------------------------------------------
    def run(self, state: TradingState):
        trader_data = self._load_trader_data(state.traderData)

        pepper_state = trader_data[self.PEPPER]
        osmium_state = trader_data[self.OSMIUM]

        self._update_pepper_fair(state, pepper_state)

        result: Dict[str, List[Order]] = {}
        conversions = 0

        result[self.PEPPER] = self._pepper_orders(state, pepper_state)

        if self.OSMIUM in state.order_depths:
            result[self.OSMIUM] = self._osmium_orders(
                state,
                state.order_depths[self.OSMIUM],
                osmium_state,
            )
        else:
            result[self.OSMIUM] = []

        encoded_trader_data = jsonpickle.encode(trader_data)
        logger.flush(state, result, conversions, encoded_trader_data)
        return result, conversions, encoded_trader_data