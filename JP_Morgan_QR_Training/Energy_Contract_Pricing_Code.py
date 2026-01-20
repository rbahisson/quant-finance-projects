import pandas as pd 
import numpy as np 
from sklearn.linear_model import LinearRegression

#Import Price Data with 2 columns: Dates, Prices
df = pd.read_csv(r"C:\Users\Startklar\Documents\Milan\Becoming a quant\Quant Projects - Jan 26 onwards\JPM - Qr\Nat_Gas.csv")

#Setting the problem as a time-series analysis 
df['Dates'] = pd.to_datetime(df['Dates'])
df = df.sort_values('Dates')
df.set_index('Dates', inplace = True)

#Feature Engineering 
df['Month'] = df.index.month

#Fit: Price = Trend + Seasonality 
df['t'] = np.arange(len(df))
month_dummies = pd.get_dummies(df['Month'], prefix='m', drop_first=True)

x = pd.concat([df[['t']], month_dummies], axis=1)
y = df['Prices'].values 

model = LinearRegression()
model.fit(x, y)

#Forecast next 12 months 
months_ahead = 12 
last_date = df.index.max()
last_t = df['t'].iloc[-1]

future_dates = pd.date_range( 
    start = last_date + pd.offsets.MonthEnd(1), 
    periods = months_ahead, 
    freq = 'M' 
)

future = pd.DataFrame(index=future_dates)
future['Month'] = future.index.month
future['t'] = np.arange(last_t + 1, last_t + 1 + months_ahead)

future_dummies = pd.get_dummies(future['Month'], prefix='m', drop_first=True)
x_future =  pd.concat([future[['t']], future_dummies], axis = 1)

x_future = x_future.reindex(columns= x.columns, fill_value= 0)

future['ForecastPrice'] = model.predict(x_future)

hist_curve = df['Prices'].copy()
fwd_curve = future['ForecastPrice'].copy()
full_curve = pd.concat([hist_curve, fwd_curve]).sort_index()

def estimate_price(date_str_or_dt): 
    d = pd.to_datetime(date_str_or_dt)

    if d < full_curve.index.min():
        raise ValueError(f"Date {d.date()} is before available history ({full_curve.index.min().date()}).")
    if d > full_curve.index.max():
        raise ValueError(f"Date {d.date()} is beyond forecast horizon ({full_curve.index.max().date()}).")

    tmp = full_curve.copy()
    tmp.loc[d] = np.nan
    tmp = tmp.sort_index().interpolate(method='time')
    return float(tmp.loc[d])

#Quick Tests
#print("Example past date:", estimate_price("2022-06-15"))
#print("Example month-end:", estimate_price("2023-11-30"))
#print("Example Jan 7th 2025:", estimate_price("2025-01-07"))
#print("Example future date:", estimate_price(full_curve.index.max()))


#############################################################################################################
#############################################################################################################
### Task 2 
#############################################################################################################
#############################################################################################################


def price_storage_contract(injections, withdrawals, injection_rate, withdrawal_rate, max_volume, storage_cost_per_month, ): 

    #Building the record of events (injections and withdrawals)
    events = []

    for d, v in injections: 
        events.append({"date": pd.to_datetime(d), "type": "inject", "volume": float(v)})

    for d, v in withdrawals:
        events.append({"date": pd.to_datetime(d), "type": "withdraw", "volume": float(v)})
    
    events = pd.DataFrame(events).sort_values("date").reset_index(drop=True)

    
    #Calculating Inventory and Cashflow 
    inventory = 0.0 
    cashflow = 0.0 

    for _, row in events.iterrows(): 
        date = row["date"]
        vol = row["volume"]
        price = estimate_price(date)


        if row["type"] == "inject": 
            if vol > injection_rate: 
                raise ValueError(f"Injection Volume exceeds injection rate on {date.date()}")
            
            if inventory + vol > max_volume: 
                raise ValueError(f"Storage capacity exceeded on {date.date()}")

            inventory += vol 
            cashflow -= price * vol 

        elif row["type"] == "withdraw": 
            if vol > withdrawal_rate:
                raise ValueError(f"Withdrawal volume exceeds withdrawal rate on {date.date()}.")

            if vol > inventory:
                raise ValueError(f"Insufficient inventory on {date.date()}.")

            inventory -= vol
            cashflow += price * vol

    start = events["date"].min()
    end = events["date"].max()
    number_of_months = (end.year - start.year) * 12 + (end.month - start.month) + 1

    total_storage_cost = number_of_months * storage_cost_per_month

    contract_value = cashflow - total_storage_cost
    return contract_value


# Quick Test
injections = [("2024-01-31", 50), ("2024-02-29", 40)]
withdrawals = [("2024-08-31", 60), ("2024-09-30", 30)]
value = price_storage_contract(injections=injections, withdrawals=withdrawals, injection_rate=60, withdrawal_rate=60, max_volume=100, storage_cost_per_month=10)
print("Contract value:", value)