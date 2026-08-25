from datamodel import OrderDepth, TradingState, Order
from typing import Dict, List, Tuple
import math
 
 
class Trader:
    POSITION_LIMIT = { "EMERALDS": 80, "TOMATOES": 80, }
 
    EMERALDS_FAIR = 10000.0
 
    # traderData format:
    # E_last;E_ema;T_last;T_ema;T_absret
    def parse_trader_data(self, s: str):
        if not s:
            return {
                "EMERALDS": {
                    "last_mid": 10000.0,
                    "ema": 10000.0, },
            
                "TOMATOES": {
                    "last_mid": 5000.0,
                    "ema": 5000.0,
                    "absret_ema": 1.0, },  }
 
        parts = s.split(";")
        try:
            return {
                "EMERALDS": {
                    "last_mid": float(parts[0]),
                    "ema": float(parts[1]), },
                
                "TOMATOES": {
                    "last_mid": float(parts[2]),
                    "ema": float(parts[3]),
                    "absret_ema": float(parts[4]), },  }
        
        except Exception:
            return {
                "EMERALDS": {
                    "last_mid": 10000.0,
                    "ema": 10000.0, },
 
                "TOMATOES": {
                    "last_mid": 5000.0,
                    "ema": 5000.0,
                    "absret_ema": 1.0, },  }
 
    def encode_trader_data(self, mem) -> str:
        return (
            str(mem["EMERALDS"]["last_mid"]) + ";" +
            str(mem["EMERALDS"]["ema"]) + ";" +
            str(mem["TOMATOES"]["last_mid"]) + ";" +
            str(mem["TOMATOES"]["ema"]) + ";" +
            str(mem["TOMATOES"]["absret_ema"]) )
 
    def best_prices(self, depth: OrderDepth) -> Tuple[int, int, int, int]:
        best_bid = max(depth.buy_orders.keys()) if depth.buy_orders else None
        best_ask = min(depth.sell_orders.keys()) if depth.sell_orders else None
        bid_vol = depth.buy_orders.get(best_bid, 0) if best_bid is not None else 0
        ask_vol = -depth.sell_orders.get(best_ask, 0) if best_ask is not None else 0
        return best_bid, bid_vol, best_ask, ask_vol
 
    def mid_price(self, depth: OrderDepth, fallback: float) -> float:
        best_bid, _, best_ask, _ = self.best_prices(depth)
        if best_bid is not None and best_ask is not None:
            return (best_bid + best_ask) / 2.0
        if best_bid is not None:
            return float(best_bid)
        if best_ask is not None:
            return float(best_ask)
        return fallback
 
    def microprice(self, depth: OrderDepth, fallback: float) -> float:
        best_bid, bid_vol, best_ask, ask_vol = self.best_prices(depth)
        if best_bid is None or best_ask is None:
            return fallback
        total = bid_vol + ask_vol
        if total <= 0:
            return fallback
        return (best_bid * ask_vol + best_ask * bid_vol) / total
 
    def add_buy(self, orders: List[Order], product: str, price: int, qty: int, buy_budget: int) -> int:
        q = min(qty, buy_budget)
        if q > 0:
            orders.append(Order(product, int(price), int(q)))
            buy_budget -= q
        return buy_budget
 
    def add_sell(self, orders: List[Order], product: str, price: int, qty: int, sell_budget: int) -> int:
        q = min(qty, sell_budget)
        if q > 0:
            orders.append(Order(product, int(price), -int(q)))
            sell_budget -= q
        return sell_budget
 
    def trade_emeralds(self, state: TradingState, depth: OrderDepth, mem) -> List[Order]:
        product = "EMERALDS"
        limit = self.POSITION_LIMIT[product]
        pos0 = state.position.get(product, 0)
 
        buy_budget = limit - pos0
        sell_budget = limit + pos0
        orders: List[Order] = []
 
        best_bid, _, best_ask, _ = self.best_prices(depth)
        if best_bid is None or best_ask is None:
            return orders
 
        fair = self.EMERALDS_FAIR
        spread = best_ask - best_bid
 
        # Aggressive stale taking
        for ask in sorted(depth.sell_orders.keys()):
            if ask <= fair - 7 and buy_budget > 0: #### Change Value here
                vol = -depth.sell_orders[ask]
                buy_budget = self.add_buy(orders, product, ask, min(vol, 20), buy_budget)
 
        for bid in sorted(depth.buy_orders.keys(), reverse=True):
            if bid >= fair + 7 and sell_budget > 0: #### Change Value here
                vol = depth.buy_orders[bid]
                sell_budget = self.add_sell(orders, product, bid, min(vol, 20), sell_budget)
 
        # Inventory balancing
        if pos0 > 55 and sell_budget > 0:
            sell_budget = self.add_sell(orders, product, best_bid + 1, min(18, sell_budget), sell_budget)
        elif pos0 < -55 and buy_budget > 0:
            buy_budget = self.add_buy(orders, product, best_ask - 1, min(18, buy_budget), buy_budget)
 
        # Passive maker
        if spread >= 3:
            bid_px = best_bid + 1
            ask_px = best_ask - 1
        elif spread == 2:
            bid_px = best_bid + 1
            ask_px = best_ask - 1
        else:
            bid_px = 9993 #### Change Value here
            ask_px = 10007 #### Change Value here
 
        skew = int(round(0.03 * pos0))
        bid_px -= skew
        ask_px -= skew
 
        bid_px = min(bid_px, best_ask - 1)
        ask_px = max(ask_px, best_bid + 1)
 
        bid_size = 28
        ask_size = 28
 
        if pos0 > 35:
            bid_size = 16
            ask_size = 34
        elif pos0 < -35:
            bid_size = 34
            ask_size = 16
 
        if bid_px < best_ask and buy_budget > 0:
            buy_budget = self.add_buy(orders, product, bid_px, min(bid_size, buy_budget), buy_budget)
 
        if ask_px > best_bid and sell_budget > 0:
            sell_budget = self.add_sell(orders, product, ask_px, min(ask_size, sell_budget), sell_budget)
 
        return orders
 
    def trade_tomatoes(self, state: TradingState, depth: OrderDepth, mem) -> List[Order]:
        product = "TOMATOES"
        limit = self.POSITION_LIMIT[product]
        pos0 = state.position.get(product, 0)
 
        buy_budget = limit - pos0
        sell_budget = limit + pos0
        orders: List[Order] = []
 
        best_bid, bid_vol, best_ask, ask_vol = self.best_prices(depth)
        if best_bid is None or best_ask is None:
            return orders
 
        spread = best_ask - best_bid
        mid = self.mid_price(depth, mem[product]["last_mid"])
        micro = self.microprice(depth, mid)
 
        last_mid = mem[product]["last_mid"]
        ema_prev = mem[product]["ema"]
        absret_prev = mem[product]["absret_ema"]
 
        momentum = mid - last_mid
        absret = abs(momentum)
 
        ema = 0.18 * mid + 0.82 * ema_prev
        absret_ema = 0.18 * absret + 0.82 * absret_prev
 
        mem[product]["last_mid"] = mid
        mem[product]["ema"] = ema
        mem[product]["absret_ema"] = absret_ema
 
        imbalance = 0.0
        if bid_vol + ask_vol > 0:
            imbalance = (bid_vol - ask_vol) / float(bid_vol + ask_vol)
 
        # Deep book imbalance (levels 1+2+3) — strongest signal from regression (-0.669)
        bvol_deep = sum(v for v in [
            depth.buy_orders.get(p, 0)
            for p in sorted(depth.buy_orders.keys(), reverse=True)[:3] ])
        
        avol_deep = sum(-v for v in [
            depth.sell_orders.get(p, 0)
            for p in sorted(depth.sell_orders.keys())[:3] ])
        
        deep_imbalance = 0.0
        if bvol_deep + avol_deep > 0:
            deep_imbalance = (bvol_deep - avol_deep) / float(bvol_deep + avol_deep)
 
        # Volatility regime
        high_vol = absret_ema >= 2.2
        very_high_vol = absret_ema >= 3.5
 
        # Mean reversion: how far microprice has deviated from EMA, capped at ±6 ticks
        mean_rev = max(min(4.60 * (ema - micro), 6.0), -6.0)
 
        fair = (
            micro
            + mean_rev
            + 0.252 * imbalance
            - 0.669 * deep_imbalance
            + 0.7  * momentum
            - 0.07  * pos0     )
 
        # Aggressive taking only with meaningful edge
        take_edge = 3 if not high_vol else 5 # Take edge in calm vs. high vol regimes 
        buy_take = math.floor(fair - take_edge)
        sell_take = math.ceil(fair + take_edge)
 
        max_take_size = 12 if not high_vol else 5 # Max Take size in calm vs. high vol regimes 
 
        for ask in sorted(depth.sell_orders.keys()):
            if ask <= buy_take and buy_budget > 0:
                vol = -depth.sell_orders[ask]
                buy_budget = self.add_buy(orders, product, ask, min(vol, max_take_size), buy_budget)
 
        for bid in sorted(depth.buy_orders.keys(), reverse=True):
            if bid >= sell_take and sell_budget > 0:
                vol = depth.buy_orders[bid]
                sell_budget = self.add_sell(orders, product, bid, min(vol, max_take_size), sell_budget)
 
        # Passive quoting:
        # in calm regime: join inside spread
        # in volatile regime: widen and cut size
        if spread >= 3:
            bid_px = best_bid + 1
            ask_px = best_ask - 1
        else:
            bid_px = best_bid
            ask_px = best_ask
 
        center = (best_bid + best_ask) / 2.0
 
        if not high_vol:
            if fair >= center + 1.0:
                bid_px = min(bid_px + 1, best_ask - 1)
            elif fair <= center - 1.0:
                ask_px = max(ask_px - 1, best_bid + 1)
        else:
            if fair >= center + 2.0:
                bid_px = min(bid_px + 1, best_ask - 1)
            elif fair <= center - 2.0:
                ask_px = max(ask_px - 1, best_bid + 1)
 
        # Inventory skew
        skew = int(round(0.05 * pos0))
        bid_px -= skew
        ask_px -= skew
 
        # Position control
        if pos0 > 35:
            ask_px = best_bid + 1
        elif pos0 < -35:
            bid_px = best_ask - 1
 
        bid_px = min(bid_px, best_ask - 1)
        ask_px = max(ask_px, best_bid + 1)
 
        if very_high_vol:
            bid_size = 6
            ask_size = 6
        elif high_vol:
            bid_size = 8
            ask_size = 8
        else:
            bid_size = 20
            ask_size = 20
 
        # directional lean only in calm regime
        if not high_vol:
            if momentum > 0.8:
                bid_size += 2
                ask_size -= 2
            elif momentum < -0.8:
                ask_size += 2
                bid_size -= 2
 
        bid_size = max(2, bid_size)
        ask_size = max(2, ask_size)
 
        if pos0 > 50:
            bid_size = 2
            ask_size = max(ask_size, 12)
        elif pos0 < -50:
            ask_size = 2
            bid_size = max(bid_size, 12)
 
        if bid_px < best_ask and buy_budget > 0:
            buy_budget = self.add_buy(orders, product, bid_px, min(bid_size, buy_budget), buy_budget)
 
        if ask_px > best_bid and sell_budget > 0:
            sell_budget = self.add_sell(orders, product, ask_px, min(ask_size, sell_budget), sell_budget)
 
        return orders
 
    def run(self, state: TradingState):
        mem = self.parse_trader_data(state.traderData)
        result: Dict[str, List[Order]] = {}
 
        if "EMERALDS" in state.order_depths:
            result["EMERALDS"] = self.trade_emeralds(state, state.order_depths["EMERALDS"], mem)
 
        if "TOMATOES" in state.order_depths:
            result["TOMATOES"] = self.trade_tomatoes(state, state.order_depths["TOMATOES"], mem)
 
        trader_data = self.encode_trader_data(mem)
        conversions = 0
        return result, conversions, trader_data