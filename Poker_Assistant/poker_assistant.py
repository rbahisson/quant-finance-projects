import random
import itertools
import sys
from typing import List, Tuple, Optional

RANKS = "23456789TJQKA"
SUITS = "cdhs"  # clubs, diamonds, hearts, spades
RANK_TO_VAL = {r: i for i, r in enumerate(RANKS, start=2)}  
VAL_TO_RANK = {v: r for r, v in RANK_TO_VAL.items()}

#High Card to Quinte Flush 
HAND_CATEGORY_NAMES = [
    "High Card",         # 0
    "One Pair",          # 1
    "Two Pair",          # 2
    "Three of a Kind",   # 3
    "Straight",          # 4
    "Flush",             # 5
    "Full House",        # 6
    "Four of a Kind",    # 7
    "Straight Flush",    # 8
]

#Makes sure we get valid card syntax and then transforms the input into code
def to_card_code(s: str) -> str:
    s = s.strip().lower()
    if len(s) != 2:
        raise ValueError(f"Invalid card: {s}")
    r, u = s[0].upper(), s[1]
    if r not in RANKS or u not in SUITS:
        raise ValueError(f"Invalid card: {s}")
    return r + u

#Displays cards to the user 
def format_card(c: str) -> str:
    return c[0] + c[1]


#Creates a 52-card deck and removes any card that the user has input 
def deck_without(exclude: List[str]) -> List[str]:
    full = [r + s for r in RANKS for s in SUITS]
    excl = set(c.lower() for c in exclude)
    return [c for c in full if c.lower() not in excl]

#The user can input 'flee' at anytime to break the code and literally flee the table
def check_flee(value: str):
    if value.strip().lower() == "flee":
        print("\n You fled the table. Restarting session...\n")
        main() 
        sys.exit(0)



#Converts card rank into a numerical value 
def card_rank_val(card: str) -> int:
    return RANK_TO_VAL[card[0].upper()]

#Checks if you've got a straight and returns the top card value
def is_straight(rank_vals_sorted_desc: List[int]) -> Optional[int]:
    if not rank_vals_sorted_desc:
        return None
    vals = sorted(set(rank_vals_sorted_desc))
    # Handle wheel straight A-2-3-4-5
    if set([14, 5, 4, 3, 2]).issubset(set(vals)):
        return 5
    # Normal straights
    best = None
    run = 1
    for i in range(1, len(vals)):
        if vals[i] == vals[i-1] + 1:
            run += 1
            if run >= 5:
                best = vals[i]
        else:
            run = 1
    return best

#Determines the best possible 5-card hand you can have 
def best_five_from_seven(cards7: List[str]) -> Tuple[int, List[int]]:

    # Build structures
    ranks = [card_rank_val(c) for c in cards7]
    suits = [c[1] for c in cards7]

    # Count occurrences
    from collections import Counter
    rc = Counter(ranks)
    sc = Counter(suits)

    # Flush?
    flush_suit = None
    for s, cnt in sc.items():
        if cnt >= 5:
            flush_suit = s
            break

    # Straight?
    unique_ranks_desc = sorted(set(ranks), reverse=True)
    straight_high = is_straight(unique_ranks_desc)

    # Straight flush?
    if flush_suit:
        flush_cards = sorted([card_rank_val(c) for c in cards7 if c[1] == flush_suit], reverse=True)
        flush_unique = sorted(set(flush_cards), reverse=True)
        sf_high = is_straight(flush_unique)
        if sf_high is not None:
            return (8, [sf_high])  # Straight Flush

    # Four of a kind
    quads = [r for r, cnt in rc.items() if cnt == 4]
    if quads:
        quad = max(quads)
        kicker = max([r for r in unique_ranks_desc if r != quad])
        return (7, [quad, kicker])

    # Full house
    trips = sorted([r for r, cnt in rc.items() if cnt == 3], reverse=True)
    pairs = sorted([r for r, cnt in rc.items() if cnt == 2], reverse=True)
    if trips:
        # Use best trip, then next best trip/pair as pair
        trip = trips[0]
        remaining_trips = [t for t in trips if t != trip]
        best_pair_like = (remaining_trips + pairs)
        if best_pair_like:
            return (6, [trip, max(best_pair_like)])

    # Flush
    if flush_suit:
        flush_vals = sorted([r for r, s in zip(ranks, suits) if s == flush_suit], reverse=True)
        top5 = flush_vals[:5]
        return (5, top5)

    # Straight
    if straight_high is not None:
        return (4, [straight_high])

    # Three of a kind
    if trips:
        trip = trips[0]
        kickers = [r for r in unique_ranks_desc if r != trip][:2]
        return (3, [trip] + kickers)

    # Two pair
    if len(pairs) >= 2:
        top2 = pairs[:2]
        kicker = [r for r in unique_ranks_desc if r not in top2][0]
        return (2, top2 + [kicker])

    # One pair
    if len(pairs) == 1:
        pair = pairs[0]
        kickers = [r for r in unique_ranks_desc if r != pair][:3]
        return (1, [pair] + kickers)

    # High card
    return (0, unique_ranks_desc[:5])

#Determines who has the best hand (between 2 players)
def compare_7card_vs_7card(cards7_a: List[str], cards7_b: List[str]) -> int:
    ra = best_five_from_seven(cards7_a)
    rb = best_five_from_seven(cards7_b)
    if ra > rb:
        return 1
    elif rb > ra:
        return -1
    return 0

#Uses a Monte Carlo Simulation (randomly completes the unknown cards multiple times) and counts how often you win or tie 
#Estimates your chance of winning
def simulate_win_prob(hole: List[str], board: List[str], num_opponents: int, trials: int = 1500) -> float:
    known = hole + board
    wins = 0
    ties = 0
    for _ in range(trials):
        d = deck_without(known)
        random.shuffle(d)

        # Complete opponents' hole cards
        opp_holes = []
        for _ in range(num_opponents):
            opp_holes.append([d.pop(), d.pop()])

        # Complete the board to 5 cards
        draw_needed = 5 - len(board)
        sim_board = board[:] + [d.pop() for _ in range(draw_needed)]

        our_7 = hole + sim_board

        # Compare against each opponent; if we lose to any, it's a loss for this trial
        our_result_better_than_all = True
        tie_with_any_and_no_losses = False
        for opp in opp_holes:
            cmpres = compare_7card_vs_7card(our_7, opp + sim_board)
            if cmpres < 0:
                our_result_better_than_all = False
                tie_with_any_and_no_losses = False
                break
            elif cmpres == 0:
                tie_with_any_and_no_losses = True
        if our_result_better_than_all:
            if tie_with_any_and_no_losses:
                ties += 1
            else:
                wins += 1

    total = float(trials)
    # Allocate half credit to ties
    return (wins + 0.5 * ties) / total

#Determines Pot Odds = (Amount to Call / (Pot Size + Amount to Call))
def compute_pot_odds(call_amount: float, pot: float) -> float:
    if call_amount <= 0:
        return 0.0
    denom = pot + call_amount
    return call_amount / denom if denom > 0 else 1.0

# +/- 10% based on whether you are risk-adverse or not 
def risk_adjust(win_prob: float, risk_factor: float) -> float:
    # Base adjustment range: ±0.10
    adj = (risk_factor - 0.5) * 0.20  # -0.10 .. +0.10
    return max(0.0, min(1.0, win_prob + adj))

#Compares your risk-adjusted win probability to the pot odds 
def recommend_action(win_prob: float,
                     pot_odds: float,
                     bankroll: float,
                     min_bet: float,
                     pot: float,
                     risk_factor: float) -> Tuple[str, float, dict]:
    
    # Risk-adjust the *required* equity boundary, by applying the same transformation to win_prob
    adj_equity = risk_adjust(win_prob, risk_factor)

    debug = {
        "win_prob": win_prob,
        "risk_adj_equity": adj_equity,
        "pot_odds": pot_odds
    }

    if adj_equity < pot_odds - 1e-9:
        # Not enough equity to profitably call
        return ("fold", 0.0, debug)

    # If calling is OK, consider raising if we have clear edge
    # Define a margin to raise
    edge = adj_equity - pot_odds
    # Bet sizing: a fraction of pot scaled by edge and risk
    # Floor at min_bet, cap at pot*1.5, not exceeding bankroll
    if edge > 0.05:  # confident advantage
        target = pot * (0.5 + risk_factor) * (min(1.0, 2.0 * edge))  # 0.5–1.5 pot roughly
        size = max(min_bet, min(target, bankroll))
        if size >= min_bet and bankroll >= min_bet:
            return ("raise", round(size, 2), debug)

    # Otherwise recommend call if we can afford it
    call_amt = min_bet if min_bet > 0 else 0.0
    # In poker “amount to call” could differ from min_bet; caller supplies that outside.
    # We'll override in CLI with the input `to_call`.
    return ("call", 0.0, debug)

#Asks user to input cards while checking for valid inputs
def ask_cards(prompt_text: str, expected_count_range=(0, 7)) -> List[str]:
    
    print("\n--- Card Input Guide ---")
    print("Use 2 characters per card: [Rank][Suit]")
    print("Ranks: 2 3 4 5 6 7 8 9 T J Q K A")
    print("Suits: c = Clubs, d = Diamonds, h = Hearts, s = Spades")
    print("Example: Ah Kd 7c (Ace of hearts, King of diamonds, 7 of clubs)\n")

    while True:
        line = input(prompt_text).strip()
        check_flee(line)

        if not line:
            return []
        tokens = line.split()
        try:
            cs = [to_card_code(tok) for tok in tokens]
            if not (expected_count_range[0] <= len(cs) <= expected_count_range[1]):
                print(f"Please enter between {expected_count_range[0]} and {expected_count_range[1]} cards.")
                continue
            if len(set([c.lower() for c in cs])) != len(cs):
                print("Duplicate cards detected. Try again.")
                continue
            return cs
        except Exception as e:
            print(f"Error: {e}. Example format: Ah Kd 7c")

#Asks user for bet size, bankroll and pot size 
def ask_float(prompt_text: str, min_value: float = 0.0) -> float:
    while True:
        try:
            raw = input(prompt_text).strip()
            check_flee(raw) 

            v = float(raw)
            if v < min_value:
                print(f"Enter a number ≥ {min_value}.")
                continue
            return v
        except:
            print("Please enter a valid number.")

#Asks users for number of players
def ask_int(prompt_text: str, min_value: int = 0) -> int:
    while True:
        try:
            raw = input(prompt_text).strip()
            check_flee(raw) 

            v = int(raw)
            if v < min_value:
                print(f"Enter an integer ≥ {min_value}.")
                continue
            return v
        except:
            print("Please enter a valid integer.")


def main():
    print("\n=== Poker Assistant (Texas Hold’em) — First Draft ===\n")
    print("Tip: Card format is RankSuit like: Ah Kd Tc 9s (A=Ace, K, Q, J, T=10; suits: c,d,h,s)\n")

    print("\n--- Betting Terms Guide ---")
    print("1. Bankroll: The total amount of money you have available to play.")
    print("2. Bet size: The amount of money you choose to put in the pot on a given hand or street.")
    print("3. Pot size: The total money already in play from all players.")

    bankroll = ask_float("Your starting bankroll (€): ", 1.0)
    min_bet = ask_float("Table minimum bet / current smallest call amount (€): ", 0.0)
    n_players = ask_int("Number of players at the table (including you): ", 2)
    risk_factor = ask_float("Risk preference (0=very risk-averse, 1=very risk-seeking): ", 0.0)
    risk_factor = max(0.0, min(1.0, risk_factor))

    default_trials = ask_int("Monte Carlo trials per estimate (e.g., 1500): ", 200)

    while bankroll > 0:
        print("\n--- New Decision ---")
        print("Enter your *current* situation. Leave empty to auto-deal random cards if desired.")
        hole = ask_cards("Your hole cards (2 cards, e.g., Ah Kd): ", (0, 2))
        board = ask_cards("Community cards so far (0, 3, 4, or 5 cards): ", (0, 5))

        # Auto-deal if user left empty
        known = hole + board
        if not hole:
            d = deck_without(known)
            random.shuffle(d)
            hole = [d.pop(), d.pop()]
            print(f"Dealt you: {format_card(hole[0])} {format_card(hole[1])}")
            known = hole + board

        # Validate that hole has exactly 2, board <=5 and no conflicts
        try:
            assert len(hole) == 2
            assert len(board) <= 5
            # also ensure no duplicates with deck
            _ = deck_without(hole + board)  # raises if invalid format, not if dupes (handled earlier)
        except AssertionError:
            print("Invalid number of cards. Try again.")
            continue

        # Opponents
        opps = max(1, n_players - 1)

        # Pot and to-call
        pot = ask_float("Current pot size (€): ", 0.0)
        to_call = ask_float("Amount you must call to continue (€): ", 0.0)

        # Adjust min_bet for this decision: in live hands, 'to_call' is the key amount
        effective_min = max(min_bet, to_call)

        # Estimate equity
        trials = default_trials
        try:
            win_prob = simulate_win_prob(hole, board, opps, trials=trials)
        except Exception as e:
            print(f"Simulation error: {e}")
            continue

        pot_odds = compute_pot_odds(to_call, pot)

        # Recommend
        action, size, dbg = recommend_action(
            win_prob=win_prob,
            pot_odds=pot_odds,
            bankroll=bankroll,
            min_bet=effective_min,
            pot=pot,
            risk_factor=risk_factor
        )

        # Bet sizing if action == call: the amount is to_call (if any)
        suggested_amount = 0.0
        if action == "call":
            suggested_amount = min(to_call, bankroll)
        elif action == "raise":
            # suggest a raise amount *in addition* to call (simplification: total put in this street)
            suggested_amount = min(size, bankroll)

        # Show details
        print("\n=== Recommendation ===")
        print(f"Win probability (est.): {win_prob*100:.1f}%")
        print(f"Pot odds (call/(pot+call)): {pot_odds*100:.1f}%")
        print(f"Risk-adjusted equity used: {dbg['risk_adj_equity']*100:.1f}%")
        print(f"Suggested action: {action.upper()}")

        if action in ("call", "raise"):
            if action == "call":
                print(f"Suggested call: €{suggested_amount:.2f}")
            else:
                print(f"Suggested raise size (this street): €{suggested_amount:.2f}")
        else:
            print("No chips committed this street.")

        # Apply the user's choice to bankroll (simplified accounting)
        print("\nMake your move:")
        print("  [f]old   [c]all   [r]aise   [q]uit")
        user_move = input("> ").strip().lower() or action[0]

        if user_move == 'q':
            print("Good session. See you next time!")
            break

        if user_move == 'f':
            spent = 0.0
            print("You folded.")
        elif user_move == 'c':
            spent = min(to_call, bankroll)
            bankroll -= spent
            print(f"You called €{spent:.2f}.")
        elif user_move == 'r':
            # ask user for raise size (total amount they want to put in this street)
            max_raise = bankroll
            print(f"Enter your raise size for this street (suggested €{suggested_amount:.2f}, max €{max_raise:.2f}):")
            try:
                amt = float(input("> ").strip())
                if not (effective_min <= amt <= max_raise):
                    print(f"Invalid raise size. Using suggested amount €{min(suggested_amount, max_raise):.2f}.")
                    amt = min(suggested_amount, max_raise)
            except:
                amt = min(suggested_amount, max_raise)
            spent = amt
            bankroll -= spent
            print(f"You raised €{spent:.2f}.")
        else:
            print("Unrecognized input; taking recommended action.")
            if action == "fold":
                spent = 0.0
            elif action == "call":
                spent = min(to_call, bankroll)
                bankroll -= spent
            else:
                amt = min(suggested_amount, bankroll)
                spent = amt
                bankroll -= spent

        print(f"Bankroll now: €{bankroll:.2f}")

        # Optional: quick end condition
        if bankroll <= 0:
            print("You are out of money. Session over.")
            break

        # Ask to continue
        print("\nContinue? [Enter to continue / q to quit]")
        if input("> ").strip().lower() == 'q':
            print("Good session. Bye!")
            break

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nSession interrupted. Goodbye!")
        sys.exit(0)
