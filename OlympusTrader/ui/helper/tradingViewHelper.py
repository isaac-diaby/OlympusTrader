import pandas as pd

def history_to_trading_view_format(data: pd.DataFrame):
    """
    Convert the history dataframe to a trading view format
    """
    history = data[["open", "high", "low", "close", "volume"]].copy()
    # if we can not pass the TA indicators values to the trading view chart
    # history = pd[["open", "high", "low", "close", "volume"]].copy()
    history.reset_index(inplace=True)
    history.dropna(inplace=True)
    history.drop(columns=["symbol"], inplace=True)
    history.rename(columns={"date": "time"}, inplace=True)
    history["time"] = history["time"].dt.strftime('%Y-%m-%d %H:%M')
    # history["time"] = history["time"].dt.strftime('%Y-%m-%dT%H:%M:%S.%f%z')
    # history["time"] = history["time"].astype(str)
    # history["time"] = history["time"].astype(int) / 10**9 # Convert to seconds
    # history["time"] = pd.to_datetime(history["time"].astype(int) / 1000000000, unit='s')
    # history["time"] = history["time"].astype(int)
    # history["time"] = history["time"].to_timestamp()
    # history["time"].timestamp()
    # history[["time"]] = history["time"].astype(int) / 1000000
    # history["time"] = history["time"].dt.strftime('%Y-%m-%d')
    print(history["time"].tail(5))

    return history.to_dict(orient='records')


def genMockDataFrame(days,startPrice,colName,startDate,seed=None): 
   
    periods = days*24
    np.random.seed(seed)
    steps = np.random.normal(loc=0, scale=0.0018, size=periods)
    steps[0]=0
    P = startPrice+np.cumsum(steps)
    P = [round(i,4) for i in P]

    fxDF = pd.DataFrame({ 
        # 'ticker':np.repeat( [colName], periods ),
        'time': np.tile( pd.date_range(startDate, periods=periods, freq='h'), 1 ),
        'price':(P)})
    fxDF.index = pd.to_datetime(fxDF.time)
    fxDF = fxDF.price.resample('D').ohlc()
    vol = np.random.randint(100,5000,days)
    fxDF['volume'] = vol
    return fxDF