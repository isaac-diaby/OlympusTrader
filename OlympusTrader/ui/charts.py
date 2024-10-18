
from multiprocessing import freeze_support
import numpy as np
import pandas as pd

from lightweight_charts import Chart

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

priceData = genMockDataFrame(365,1.2000,'EUR/USD','19/3/2023',seed=42)

if __name__ == '__main__':
    # freeze_support()
    chart = Chart(toolbox=True)
    print(priceData.tail(10))
    chart.set(priceData)
    chart.show(block=True)