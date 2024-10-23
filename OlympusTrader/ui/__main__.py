import datetime
from json import JSONEncoder
from typing import Any
import dash
from dash import dcc, html
from dash.dependencies import Input, Output
from uuid import UUID
import pandas as pd

# Import the SharedStrategyManager class
from OlympusTrader.broker.interfaces import IAccount, IAsset, IOrderSide, IPosition, ITradeUpdateEvent
from OlympusTrader.insight.insight import Insight, InsightState, StrategyDependantConfirmation
# from OlympusTrader.strategy.base_strategy import BaseStrategy
from OlympusTrader.strategy.interfaces import IStrategyMatrics, IStrategyMode
from OlympusTrader.ui.helper import sharedStrategyManager
from OlympusTrader.ui.helper.tradingViewHelper import history_to_trading_view_format
from OlympusTrader.ui.interfaces.store import STRATEGY_STORE_MAPPINGS, STRATEGY_SYNC_MAPPING

# FIXME: We will temporarily Override the JSoneEncoder to handle UUID objects. When we move to using data classes, we can remove this nasty hack.
old_default = JSONEncoder.default

def new_default(self, obj):
    if isinstance(obj, UUID):
        return str(obj)
    elif isinstance(obj, IOrderSide):
        return str(obj.value)
    elif isinstance(obj, InsightState):
        return str(obj)
    elif isinstance(obj, StrategyDependantConfirmation):
        return str(obj)
    elif isinstance(obj, IStrategyMode):
        return str(obj)
    elif isinstance(obj, StrategyDependantConfirmation):
        return str(obj)
    elif isinstance(obj, ITradeUpdateEvent):
        return str(obj)
    return old_default(self, obj)

JSONEncoder.default = new_default

# Initialize the SharedStrategyManager
global SSM_manager 
SSM_manager = sharedStrategyManager.get_shared_strategy_manager()


# External resources
external_stylesheets = [
    # "https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.6.0/css/solid.min.css",
    "https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.6.0/css/all.min.css"
    ]
external_scripts = ["https://cdn.tailwindcss.com"]

# Initialize the Dash app
app = dash.Dash(__name__,
                external_scripts=external_scripts,
                external_stylesheets=external_stylesheets,
                use_pages=True)

header = html.Header(
    className="text-white p-4 border-b border-accent",
    children=[
        html.Div(
            className="container mx-auto flex items-center justify-between",
            children=[
                html.Div(
                    className="flex items-center",
                    children=[
                        # TODO: Add logo
                        html.H1("OlympusTrader", className="text-2xl"),
                    ]
                ),
                html.Nav(
                    className="flex space-x-4",
                    children=[

                        dcc.Link(f"Overview", href="/", className="text-accent hover:text-white"),
                        html.A(
                            "Docs",
                            href="https://olympustrader.readthedocs.io/en/latest/?badge=latest",
                            target="_blank",
                            className="text-accent hover:text-white ml-4",
                            ),
                            html.A(
                            href="https://discord.gg/v2R5dcvssG",
                            target="_blank",
                            className="text-accent hover:text-white",
                            children=[
                                html.I(className="fab fa-discord fa-2x")  # Font Awesome Discord icon
                            ]
                        )

                        
                        # dcc.Link(f"{page['name']}", href=page["relative_path"]) for page in dash.page_registry.values()
                    ]
                )
            ]
        )
    ]
)

body = html.Main(
    children=dash.page_container
)

footer = html.Footer(
    className="bg-primary text-accent py-4 border-t border-accent",
    children=[
        html.Div(
            className="container mx-auto text-center",
            children=[
                html.P("© 2024 OlympusTrader. All rights reserved."),
                html.A(
                    href="https://github.com/isaac-diaby/OlympusTrader",
                    target="_blank",
                    className="text-accent hover:text-white ml-4 mt-1",
                    children=[
                        html.I(className="fab fa-github fa-2x")  # Font Awesome GitHub icon
                    ]
                ),
                # html.A(
                #     href="https://discord.gg/v2R5dcvssG",
                #     target="_blank",
                #     className="text-accent hover:text-white ml-4",
                #     children=[
                #         html.I(className="fab fa-discord fa-2x")  # Font Awesome Discord icon
                #     ]
                # )
            ]
        )
    ]
)

# Add the dcc.Interval component
interval_component = dcc.Interval(
    id=STRATEGY_SYNC_MAPPING.id,
    # interval=2*1000,  # Update every 2 seconds  - some works sometimes dont complete in 2 seconds so the data is not updated on the UI and the next updates come in
    interval=5*1000,  # Update every 5 seconds
    # interval=60*1000,  # Update every minute - for testing
    n_intervals=0
)

# Add a dcc.Store component to store the strategy data
# TODO: Might need to change the storage type to a  storage_type='local' or 'session'. This is becuase we can let the front end store the account balance history and calculate the profit/loss over time on the front end. in a local storage. This will reduce the amount of data that needs to be sent to the front end on page load.
strategy_data_store = [
    dcc.Store(id=STRATEGY_STORE_MAPPINGS.account.id),
    dcc.Store(id=STRATEGY_STORE_MAPPINGS.mode.id),
    dcc.Store(id=STRATEGY_STORE_MAPPINGS.assets.id),
    dcc.Store(id=STRATEGY_STORE_MAPPINGS.positions.id),
    dcc.Store(id=STRATEGY_STORE_MAPPINGS.insights.id),
    dcc.Store(id=STRATEGY_STORE_MAPPINGS.history.id),
    dcc.Store(id=STRATEGY_STORE_MAPPINGS.metrics.id),
    dcc.Store(id=STRATEGY_STORE_MAPPINGS.time.id),
    ]

# Define the layout
app.layout = html.Div([header, body, *strategy_data_store, interval_component,
                      footer], className="min-h-screen bg-primary flex flex-col")

# Define the callback to update strategy data


@app.callback(
    [
        Output(STRATEGY_STORE_MAPPINGS.account.id, 'data'),
        Output(STRATEGY_STORE_MAPPINGS.mode.id, 'data'),
        Output(STRATEGY_STORE_MAPPINGS.assets.id, 'data'),
        Output(STRATEGY_STORE_MAPPINGS.positions.id, 'data'),
        Output(STRATEGY_STORE_MAPPINGS.insights.id, 'data'),
        Output(STRATEGY_STORE_MAPPINGS.history.id, 'data'),
        Output(STRATEGY_STORE_MAPPINGS.metrics.id, 'data'),
        Output(STRATEGY_STORE_MAPPINGS.time.id, 'data'),
    ],
    [
        Input(STRATEGY_SYNC_MAPPING.id, 'n_intervals'),
    ]
)
def update_strategy_data(n_intervals):
    # Fetch strategy data using the SharedStrategyManager

    global SSM_manager 
    if SSM_manager == None:
        SSM_manager = sharedStrategyManager.get_shared_strategy_manager()

    if n_intervals == None or SSM_manager == None:
        return ({},), (0,), ("Loading...",), ({},), ({},), (pd.DataFrame()) ({},), (None,)
    
    STRATEGY = SSM_manager.get_strategy()
    # Convert the objects to serializable formats
    ACCOUNT: IAccount = {k: v for k, v in SSM_manager.get_account().items()}
    ASSETS: dict[str, IAsset] = {k: v for k, v in SSM_manager.get_assets().items()}
    POSITIONS: dict[str, IPosition] = {k: v for k, v in SSM_manager.get_positions().items()}
    MODE: IStrategyMode = str(SSM_manager.get_mode().strip("'"))
    INSIGHTS: dict[str, Insight] = {k: v for k, v in SSM_manager.get_insights().items()}
    HISTORY = { k : history_to_trading_view_format(v) for k, v in SSM_manager.get_history().items() }
    METRICS: IStrategyMatrics =  {k: v for k, v in SSM_manager.get_metrics().items()}
    
    BROKER_TIME: datetime.datetime = int(str(SSM_manager.get_time()).split('.')[0])
    # print("Broker Time:", BROKER_TIME)



    return ACCOUNT, MODE, ASSETS, POSITIONS, INSIGHTS, HISTORY, METRICS, BROKER_TIME


# Run the server
if __name__ == '__main__':
    devMode = True
    if devMode:
        app.enable_dev_tools(
            debug=True,
            dev_tools_ui=True,
            dev_tools_serve_dev_bundles=True,
        )

    app.run(debug=devMode, threaded=devMode)
