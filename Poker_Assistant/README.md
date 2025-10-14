# Poker Assistant — Monte Carlo Betting Advisor

This project implements a Python-based **Poker Assistant** for *Texas Hold’em*.  
It uses **Monte Carlo simulations** to estimate win probabilities in real-time, compares them to **pot odds**, and recommends whether to *fold*, *call*, or *raise* based on your bankroll and risk preference.

The tool combines elements of **probabilistic modeling**, **simulation-based decision making**, and **game theory**, demonstrating the application of quantitative reasoning outside traditional finance.

---

## Workflow Overview

### 1. Card Input and Validation
- The user enters known cards (hole cards and community cards) using the two-character format (e.g., `Ah`, `Kd`, `7c`).  
- Inputs are validated for syntax, duplicates, and completeness.  
- A helper guide explains the format and card ranks/suits.

### 2. Deck Construction
- Builds a 52-card deck, excluding any known cards.  
- Randomly shuffles the deck for simulation purposes.

### 3. Monte Carlo Simulation
- Runs multiple simulated hands (`~1500` trials by default).  
- Randomly deals remaining cards and completes the board.  
- Compares the user’s 7-card hand against all opponents’ hands.  
- Estimates the **probability of winning or tying** given current conditions.

### 4. Pot Odds and Risk Adjustment
- Computes **pot odds** = amount to call / (pot size + amount to call).  
- Adjusts the simulated win probability according to the user’s **risk factor** (0 = risk-averse, 1 = risk-seeking).  
- Incorporates behavioral elements into expected value decision-making.

### 5. Decision Recommendation
- Compares adjusted win probability to pot odds:  
  - If expected equity < pot odds → *fold*.  
  - If equity ≈ pot odds → *call*.  
  - If equity > pot odds → *raise*.  
- Suggests a **raise size** proportional to edge and bankroll.  
- Provides full reasoning, including win probability, pot odds, and risk-adjusted equity.

### 6. Interactive Session
- Guides the player through consecutive decisions while updating bankroll.  
- Allows custom settings for number of players, pot size, trials, and bet sizing.  
- The user can exit anytime by typing `flee` or `quit`.
