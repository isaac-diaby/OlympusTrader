import dash
from dash import dcc, html
from dash.dependencies import Input, Output, State
import pandas as pd
from dash_tvlwc import Tvlwc
from dash_tvlwc.types import SeriesType, ColorType, LineType

from OlympusTrader.ui.charts import genMockDataFrame
from OlympusTrader.ui.components.dashboardNav import subnav
from OlympusTrader.ui.components.matricItem import MatricItem

dash.register_page(__name__, title="OlympusTrader - Strategy Overview")

assets = [
    {"symbol": "BTC/USD", "timeframe": "1h", "data": genMockDataFrame(365,1.2000,'BTC/USD','19/3/2023',seed=41)},
    {"symbol": "ETH/USD", "timeframe": "1h", "data": genMockDataFrame(365,1.2000,'ETH/USD','19/3/2023',seed=42)},
    {"symbol": "XRP/USD", "timeframe": "15m", "data": genMockDataFrame(365,1.2000,'XRP/USD','19/3/2023',seed=43)},
    {"symbol": "ADA/USD", "timeframe": "1d", "data": genMockDataFrame(365,1.2000,'ADA/USD','19/3/2023',seed=44)}
]

def assetCard(asset, idx, isSelected=False):
    className = "p-4 rounded-lg cursor-pointer transition-colors "
    className += "bg-accent text-primary " if isSelected else "bg-primary-light text-white hover:bg-accent hover:text-primary"
    return html.Div(
        id={'type': 'asset-card', 'index': idx},
        className=className,
        children=[
            html.Div([
                html.P(asset['symbol'], className="text-sm text-white")
            ], className="flex items-center justify-between"),
            html.P(asset['timeframe'], className="mt-2 text-sm")
        ]
    )

assets_in_play_section = html.Div(
    className="bg-primary-foreground rounded-lg shadow-lg border border-accent p-6 mb-8",
    children=[
        html.H2("Assets in Play", className="text-2xl font-semibold text-accent mb-4"),
        html.Div(
            className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4",
            children=[
                assetCard(asset=asset, idx=idx) for idx, asset in enumerate(assets)
            ]
        ),
        dcc.Store(id='selected-asset-store')
    ]
)
def assetChart(data: pd.DataFrame):
    try: 
        copy = data.copy()
        copy.reset_index(inplace=True)
        copy['time'] = copy['time'].dt.strftime('%Y-%m-%d')
        ohlcvt = copy.to_dict('records')
        return Tvlwc(
                id='asset-chart',
                seriesData=[ohlcvt],
                seriesTypes=[SeriesType.Candlestick],
                width='100%',
                chartOptions={
                    'layout': {
                        'background': {'type': ColorType.Solid, 'color': '#0a0f1a'},
                        'textColor': '#fffffa',
                    },
                    'grid': {
                        'vertLines': {'visible': True, 'style': 0, 'color': '#be9e6b40'},
                        'horzLines': {'visible': True, 'style': 0, 'color': '#be9e6b40'},
                    }
                    # 'localization': {
                    #     'locale': 'en-US',
                    #     'priceFormatter': "(function(price) { return '$' + price.toFixed(2); })"
                    # }
                }
                )
    except Exception as e:
        print(e)
        return None
    

def strategy_metrics_section(idx):
    return html.Div(
        className="bg-primary-foreground rounded-lg shadow-lg border border-accent p-6",
        children=[
            html.H3(f"{assets[idx]['symbol']} - Strategy Metrics", className="text-xl font-semibold text-accent mb-4"),
            html.Div(
                className="grid grid-cols-2 gap-4",
                children=[
                    MatricItem(label="Win Rate", value="68%"),
                    MatricItem(label="Profit Factor", value="2.1"),
                    MatricItem(label="Sharpe Ratio", value="1.8"),
                    MatricItem(label="Max Drawdown", value="2.5%"),
                    MatricItem(label="Avg Win Amount", value="$250.75"),
                    MatricItem(label="Avg Win %", value="2.15%"),
                    MatricItem(label="Avg Loss %", value="1.05%" ),
                    
                ]
            )

        ]
    )

def chart_section(idx):
    return html.Div(
        children=[
            html.H2(f"{assets[idx]['symbol']} - Chart", className="text-2xl font-semibold text-accent mb-4"),
            html.Div(
                className="relative min-h-64 bg-primary-light rounded flex items-center justify-center",
                children=[
                    # assetChart(assets[idx]['data'])
                    (html.P(
                        className="text-accent",
                        children="Chart Placeholder"
                    ) if idx is None else assetChart(assets[idx]['data'])),
                    # strategy_metrics_section(idx)
                ]
            )
        ]
    )



# Define the layout
layout = html.Div([
    subnav(),
    html.Div(
        className="flex-grow container mx-auto py-8 text-white",
        children=[
            html.H1('Strategy Overview', className="text-3xl font-bold text-accent mb-6"),
            assets_in_play_section,
            html.Div(id='selected-asset-chart', className="bg-primary-foreground rounded-lg shadow-lg border border-accent p-6", children=[]),
            html.Div(id='selected-asset-metrics', className="mt-8 grid grid-cols-1 md:grid-cols-2 gap-6", children=[])
        ]
    )
])

# Callback to update the selected-asset-store and display the chart section
@dash.callback(
    [Output('selected-asset-store', 'data'),
     Output('selected-asset-chart', 'children'),
     Output('selected-asset-metrics', 'children')
     ],
    [Input({'type': 'asset-card', 'index': dash.dependencies.ALL}, 'n_clicks')],
    [State('selected-asset-store', 'data')]
)
def update_selected_asset_store(n_clicks, selected_asset_data):
    ctx = dash.callback_context

    if not ctx.triggered or not n_clicks or all(click is None for click in n_clicks):
        return None, "No asset selected", []

    # Get the index of the clicked asset card
    prop_id = ctx.triggered[0]['prop_id']
    clicked_index = int(prop_id.split('.')[0].split(':')[1].split(',')[0])

    # Update the selected asset data
    if selected_asset_data is None or selected_asset_data != clicked_index:
        selected_asset_data = clicked_index

    return selected_asset_data, chart_section(clicked_index), [strategy_metrics_section(clicked_index)]

# Callback to update the class names of all asset cards
@dash.callback(
    Output({'type': 'asset-card', 'index': dash.dependencies.ALL}, 'className'),
    [Input('selected-asset-store', 'data')]
)
def update_class_names(selected_asset_data):
    if selected_asset_data is None:
        return ["p-4 bg-primary-light rounded-lg shadow-md cursor-pointer bg-primary-light text-white hover:bg-accent hover:text-primary"] * len(assets)

    class_names = ["p-4 bg-primary-light rounded-lg shadow-md cursor-pointer bg-primary-light text-white hover:bg-accent hover:text-primary"] * len(assets)
    class_names[selected_asset_data] = "p-4 bg-primary-light rounded-lg shadow-md cursor-pointer border border-accent"

    return class_names