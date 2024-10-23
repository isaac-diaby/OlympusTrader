import pandas as pd
from datetime import datetime
import pytz
import numpy as np

# TODO: we would want to make this function more performant by taking in candles that are already in the correct format and just convert the ones that are not
def history_to_trading_view_format(data: pd.DataFrame):
    """
    Convert the history dataframe to a trading view format
    """

    # IF the data is empty return an empty list
    if data.empty:
        return []
    
    history = data[["open", "high", "low", "close", "volume"]].copy()
    # if we can not pass the TA indicators values to the trading view chart
    # history = data.copy()
    history.reset_index(inplace=True)
    history.dropna(inplace=True)
    history.drop(columns=["symbol"], inplace=True)

    if "date" in history.columns:
        history.rename(columns={"date": "time"}, inplace=True)
    elif "timestamp" in history.columns:
        history.rename(columns={"timestamp": "time"}, inplace=True)
    else:
        history.rename(columns={"level_1": "time"}, inplace=True)



    # DEBUG: What the  date time looks like
    # print(history.tail(5))

    epoch = datetime(1970, 1, 1, tzinfo=pytz.UTC)
    history["time"] = history["time"].apply(lambda x: int((x - epoch).total_seconds()))

    # Sort the DataFrame by the timestamp column
    history.sort_values(by="time", inplace=True)

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