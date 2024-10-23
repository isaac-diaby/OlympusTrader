import dash
from dash import dcc, html, callback, no_update
from dash.dependencies import Input, Output, State
from dash.exceptions import PreventUpdate
import pandas as pd
from dash_tvlwc import Tvlwc
from dash_tvlwc.types import SeriesType, ColorType, LineType

from OlympusTrader.broker.interfaces import IAsset
from OlympusTrader.ui.components.dashboardNav import subnav
from OlympusTrader.ui.components.matricItem import MatricItem
from OlympusTrader.ui.components.tradesTable import tradeTable
from OlympusTrader.ui.interfaces.store import STRATEGY_STORE_MAPPINGS


dash.register_page(__name__, title="OlympusTrader - Strategy Overview", )

# assets = [
#     {"symbol": "BTC/USD", "timeframe": "1h", "data": genMockDataFrame(365, 1.2000, 'BTC/USD', '19/3/2023', seed=41), "winrate": "78%", "profit_factor": "2.1",
#      "sharpe_ratio": "1.8", "max_drawdown": "2.5%", "avg_win_amount": "£250.75", "avg_loss_amount": "£80.59", "avg_win_percent": "2.15%", "avg_loss_percent": "1.05%"},
#     {"symbol": "ETH/USD", "timeframe": "1h", "data": genMockDataFrame(365, 1.2000, 'ETH/USD', '19/3/2023', seed=42), "winrate": "65%", "profit_factor": "1.9",
#      "sharpe_ratio": "1.6", "max_drawdown": "3.0%", "avg_win_amount": "£220.50",  "avg_loss_amount": "£92.20", "avg_win_percent": "2.00%", "avg_loss_percent": "1.10%"},
#     {"symbol": "XRP/USD", "timeframe": "15m", "data": genMockDataFrame(365, 1.2000, 'XRP/USD', '19/3/2023', seed=43), "winrate": "52%", "profit_factor": "2.3",
#      "sharpe_ratio": "2.0", "max_drawdown": "2.0%", "avg_win_amount": "£180.25",  "avg_loss_amount": "£30.48", "avg_win_percent": "1.85%", "avg_loss_percent": "0.95%"},
#     {"symbol": "ADA/USD", "timeframe": "1d", "data": genMockDataFrame(365, 1.2000, 'ADA/USD', '19/3/2023', seed=44), "winrate": "81%", "profit_factor": "1.7",
#      "sharpe_ratio": "1.4", "max_drawdown": "3.5%", "avg_win_amount": "£200.00",  "avg_loss_amount": "£340.11", "avg_win_percent": "1.95%", "avg_loss_percent": "1.20%"}
# ]


def assetCard(asset: IAsset, idx, isSelected=False):
    className = "p-4 rounded-lg cursor-pointer transition-colors "
    className += "bg-accent text-primary " if isSelected else "bg-primary-light text-white hover:bg-accent hover:text-primary"
    return html.Div(
        id={'type': 'asset-card', 'index': idx},
        className=className,
        children=[
            html.Div([
                html.P(asset['symbol'], className="text-sm text-white")
            ], className="flex items-center justify-between"),
            html.P(asset['status'], className="mt-2 text-sm")
        ]
    )


assets_in_play_section = html.Div(
    className="bg-primary-foreground rounded-lg shadow-lg border border-accent p-6 mb-8",
    children=[
        html.H2("Assets in Play",
                className="text-2xl font-semibold text-accent mb-4"),
        html.Div(
            className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4",
            # children=[
            #     assetCard(asset=asset, idx=idx) for idx, asset in enumerate(assets)
            # ],
            id='assets-in-play'
        ),
        dcc.Store(id='selected-asset-store')
    ]
)


@callback(
    Output('assets-in-play', 'children'),
    [Input(STRATEGY_STORE_MAPPINGS.assets.id, 'data')],
    State('assets-in-play', 'children'),

    # prevent_initial_call=True
)
def update_assets_in_play(assets, children):
    if children != None:
        if not assets and len(children) > 0:
            return []
        elif len(assets) == len(children):
            return no_update

    if not assets:
        return no_update

    return [assetCard(asset, idx) for idx, asset in assets.items()]


def assetChart():
    try:
        # copy = data.copy()
        # copy.reset_index(inplace=True)
        # copy['time'] = copy['time'].dt.strftime('%Y-%m-%d')
        # ohlcvt = copy.to_dict('records')
        return Tvlwc(
            id='asset-chart',
            # seriesData=[ohlcvt],
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
                },
                'timeScale': {'timeVisible': True, 'visible': True},

                'localization': {
                    'timeFormatter': "businessDayOrTimestamp => {return Date(businessDayOrTimestamp);}",
                 
                #     'locale': 'en-US',
                #     'priceFormatter': "(function(price) { return '$' + price.toFixed(2); })"
                }
            },
            fullTimeScaleOptions={
                'visible': True,
                'timeVisible': True,
            }
        )
    except Exception as e:
        print(e)
        return None
    
@callback(
    Output("asset-chart", "seriesData"),
    [ 
        Input('selected-asset-store', 'data'),
        Input(STRATEGY_STORE_MAPPINGS.history.id, 'data')
    ],
    State("asset-chart", "seriesData"),
    prevent_initial_call=True,
    suppress_callback_exceptions=True
)
def update_asset_chart(selected_asset, history, seriesData):
    if selected_asset is None or history is None:
        raise PreventUpdate
    
    if selected_asset not in history:
        raise PreventUpdate
    
    # No history data
    if len(history[selected_asset]) == 0:
        return no_update
    
    if seriesData == None:
        if selected_asset not in history:
            return no_update
        else:
            seriesData = [[]]
            seriesData[0].extend(history[selected_asset])
            return seriesData
            
    if (len(seriesData[0]) == len(history[selected_asset])) or seriesData[0][-1]["time"] == history[selected_asset][-1]["time"]:
        return no_update
    
    indexdiff = len(history[selected_asset]) - len(seriesData[0])
    seriesData[0].extend(history[selected_asset][-indexdiff:])

    print(history[selected_asset][-1])
    print(seriesData[0][-1])

    return seriesData


def strategy_metrics_section(asset: IAsset):
    return html.Div(
        className="bg-primary-foreground rounded-lg shadow-lg border border-accent p-6",
        children=[
            html.H3("Asset Info",
                    className="text-xl font-semibold text-accent mb-4"),
            html.Div(
                className="grid grid-cols-2 gap-4",
                children=[
                    MatricItem(label="Name", value=asset['name']),
                    MatricItem(label="Status",
                               value=asset['status'].capitalize()),
                    MatricItem(label="Tadable",
                               value="True" if asset['tradable'] else "False"),
                    MatricItem(label="Shortable",
                               value="True" if asset['shortable'] else "False"),
                    MatricItem(label="Marginable",
                               value="True" if asset['marginable'] else "False"),
                    MatricItem(
                        label="Fractionable", value="True" if asset['fractionable'] else "False"),
                    MatricItem(label="Min Order Size",
                               value=asset.get('min_order_size', "N/A")),
                    MatricItem(label="Max Order Size",
                               value=asset.get('max_order_size', "N/A"))
                ]
            )

        ]
    )


def chart_section(asset: IAsset):
    return html.Div(
        children=[
            html.H2(f"{asset['symbol']} - Chart",
                    className="text-2xl font-semibold text-accent mb-4"),
            html.Div(
                className="relative min-h-64 bg-primary-light rounded flex items-center justify-center",
                children=assetChart()
                # [
                    # assetChart(assets[idx]['data'])
                    # (html.P(
                    #     className="text-accent",
                    #     children="Chart Placeholder"
                    # ) if asset is None else assetChart(),
                    # ) if asset is None else assetChart(assets(['data'])),
                    # strategy_metrics_section(idx)
                # ]
            )
        ]
    )


# Define the layout
layout = html.Div([
    subnav(),
    html.Div(
        className="flex-grow container mx-auto py-8 text-white",
        children=[
            html.H1('Assets Overview',
                    className="text-3xl font-bold text-accent mb-6"),
            assets_in_play_section,
            html.Div(id='selected-asset-chart',
                     className="bg-primary-foreground rounded-lg shadow-lg border border-accent p-6", children=[]),
            html.Div(id='selected-asset-metrics',
                     className="mt-8 grid grid-cols-1 md:grid-cols-2 gap-6", children=[])
        ]
    )
])

# Callback to update the selected-asset-store and display the chart section


@callback(
    [Output('selected-asset-store', 'data'),
     Output('selected-asset-chart', 'children'),
     Output('selected-asset-metrics', 'children')
     ],
    [
        Input({'type': 'asset-card', 'index': dash.dependencies.ALL}, 'n_clicks'),
    ],
    [State(STRATEGY_STORE_MAPPINGS.assets.id, 'data'),
     State('selected-asset-store', 'data')]
)
def update_selected_asset_store(n_clicks, assets: IAsset, selected_asset_data):
    ctx = dash.callback_context

    if not ctx.triggered or not n_clicks or all(click is None for click in n_clicks):
        return None, no_update, []

    # Get the index of the clicked asset card
    prop_id = ctx.triggered[0]['prop_id']
    clicked_index = str(prop_id.split('.')[0].split(':')[
                        1].split(',')[0].strip('"'))

    if assets.get(clicked_index, None) is None:
        return None, f"No Data Found For Asset: {clicked_index}", []

    display_chart = no_update
    # Update the selected asset data
    if selected_asset_data is None or selected_asset_data != clicked_index:
        selected_asset_data = clicked_index
        display_chart = chart_section(assets[clicked_index])
    else:
        selected_asset_data = no_update

    return selected_asset_data, display_chart, [strategy_metrics_section(assets[clicked_index]), tradeTable("strategy", FILTERS={"symbol": assets[clicked_index]['symbol']})]

# Callback to update the class names of all asset cards


@callback(
    Output({'type': 'asset-card', 'index': dash.dependencies.ALL}, 'className'),
    [Input('selected-asset-store', 'data')],
    [State(STRATEGY_STORE_MAPPINGS.assets.id, 'data')]
)
def update_class_names(selected_asset_data, assets):
    # default class names for the asset cards
    class_names = [
        "p-4 bg-primary-light rounded-lg shadow-md cursor-pointer bg-primary-light text-white hover:bg-accent hover:text-primary"] * len(assets)
    
    if selected_asset_data is None:
        # Return the default class names
        return class_names

    # Update the class name of the selected asset card
    class_names[list(assets).index(selected_asset_data)
                ] = "p-4 bg-primary-light rounded-lg shadow-md cursor-pointer border border-accent"

    return class_names
