from datetime import datetime
from dash import dcc, html, register_page, callback, no_update
from dash.dependencies import Input, Output, State
from dash_tvlwc import Tvlwc
from dash_tvlwc.types import SeriesType, ColorType
import plotly.graph_objects as go


from OlympusTrader.broker.interfaces import IAccount, IPosition
from OlympusTrader.insight.insight import Insight
from OlympusTrader.strategy.interfaces import IStrategyMatrics, IStrategyMode
from OlympusTrader.ui.components.accountBalanceCard import AccountBalanceCard
from OlympusTrader.ui.components.dashboardCards import dashboardCard, dashboardCardInsights, dashboardCardMode
from OlympusTrader.ui.components.matricItem import MatricItem
from OlympusTrader.ui.components.placeholderChart import PlaceholderChart
from OlympusTrader.ui.components.dashboardNav import subnav
from OlympusTrader.ui.components.tradesTable import tradeTable
from OlympusTrader.ui.interfaces.store import STRATEGY_STORE_MAPPINGS

register_page(__name__, title="OlympusTrader - Overview", path='/')

# TESTING
# balance_series =[{"time": time.strftime('%Y-%m-%d'), "value": value} for time, value in zip(
#     pd.date_range(start="2023-01-01", periods=100), np.random.randint(40_000, 60_000, 100))]


def account_card_section_populate(account: IAccount, metrics: IStrategyMatrics, insights: Insight, mode: IStrategyMode):
    alltimeChange = round(account["equity"] - metrics["starting_cash"], 2)

    # print(insight)
    # print(metrics)
    return [AccountBalanceCard(balance=round(account["equity"], 2), alltimeChange=alltimeChange, dailyChange=alltimeChange),
            dashboardCardInsights(title="Insights", insights=insights),
            # dashboardCard(title="Win Rate", value=f"{metrics["win_rate"]*100}%", icon="fa-thin fa-chart-pie"),
            dashboardCardMode(title="Mode", mode=mode, accountType=account['account_id'], connected=True)
            ]


account_card_section = html.Div(
    id="account-card-section", className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6")


@callback(
    Output("account-card-section", "children"),
    [
        Input(STRATEGY_STORE_MAPPINGS.account.id, 'data'),
        Input(STRATEGY_STORE_MAPPINGS.metrics.id, 'data'),
        Input(STRATEGY_STORE_MAPPINGS.insights.id, 'data'),
        Input(STRATEGY_STORE_MAPPINGS.mode.id, 'data'),

    ],
    # prevent_initial_call=True,

)
def update_account_card_section(account, metrics, insights, mode):

    return account_card_section_populate(account, metrics, insights, mode)

strategy_metrics_section = html.Div(
        className="bg-primary-foreground rounded-lg shadow-lg border border-accent p-6 mt-8 ",
        children=[
            html.H3("Strategy Metrics",
                    className="text-xl font-semibold text-accent mb-4"),
            html.Div(
                id="strategy-metrics",
                className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-4",
                children=[
                    # MatricItem(label="Win Rate", value=assets[idx]['winrate']),
                    # MatricItem(label="Profit Factor",
                    #            value=assets[idx]['profit_factor']),
                    # MatricItem(label="Sharpe Ratio",
                    #            value=assets[idx]['sharpe_ratio']),
                    # MatricItem(label="Max Drawdown",
                    #            value=assets[idx]['max_drawdown']),
                    # MatricItem(label="Avg Win Amount",
                    #            value=assets[idx]['avg_win_amount']),
                    # MatricItem(label="Avg Loss Amount",
                    #            value=assets[idx]['avg_loss_amount']),
                    # MatricItem(label="Avg Win %",
                    #            value=assets[idx]['avg_win_percent']),
                    # MatricItem(label="Avg Loss %",
                    #            value=assets[idx]['avg_loss_percent']),

                ]
            )
        ]
    )

@callback(
    Output("strategy-metrics", "children"),
    [
        Input(STRATEGY_STORE_MAPPINGS.metrics.id, 'data'),
    ],
    # prevent_initial_call=True,

)
def update_account_card_section(metrics: IStrategyMatrics):
    currency = "£"
    if metrics is None:
        return  None
    return  [
                    MatricItem(label="Win Rate", value=f"{round(metrics['win_rate'], 2)*100}%"),
                    MatricItem(label="Net PnL", value=f"{currency}{round(metrics['total_pnl'], 2)}"), 
                    MatricItem(label="Trades Open", value=metrics['total_open']),
                    MatricItem(label="Trades Closed", value=metrics['total_closed']),
                    MatricItem(label="Total Profits", value=f"{currency}{round(metrics['total_profit'], 2)}"),
                    MatricItem(label="Total Losses", value=f"{currency}{round(metrics['total_loss'], 2)}"),
                    MatricItem(label="Avg Win", value=f"{currency}{round(metrics['avg_win'], 2)}"),
                    MatricItem(label="Avg Loss", value=f"{currency}{round(metrics['avg_loss'], 2)}"),
    ]
 


def accountBalanceChart():
    return Tvlwc(
        id='account-balance-chart',
        seriesTypes=[SeriesType.Baseline],
        # seriesData=[],
        seriesOptions=[{
            'baseValue': {'type': 'price', 'price': 0},
            'topFillColor1': 'rgb(34, 197, 94)',
            'topFillColor2': 'rgba(34, 197, 94, 0)',
            'topLineColor': 'rgb(34, 197, 94)',
            'crosshairMarkerRadius': 4,
            'lineWidth': 2,
            'priceScaleId': 'left',
        }],
        width='100%',
        chartOptions={
            'rightPriceScale': {'visible': False},
            'leftPriceScale': {'visible': True, 'borderColor': '#be9e6b', },
            'timeScale': {'timeVisible': True, 'visible': True, 'secondsVisible': True},
            'grid': {'vertLines': {'visible': False}, 'horzLines': {'style': 0, 'color': '#be9e6b80'}},
            'layout': {'textColor': '#fffffa', 'background': {'type':  ColorType.Solid, 'color': '#0a0f1a'}},
            'localization': {
                    'timeFormatter': "(businessDayOrTimestamp) => {return Date(businessDayOrTimestamp);}",
                    # 'timeFormatter': "(businessDayOrTimestamp) => {return Date(businessDayOrTimestamp/1000);}",
                 
                #     'locale': 'en-US',
                #     'priceFormatter': "(function(price) { return '$' + price.toFixed(2); })"
                }

        }, 
        fullTimeScaleOptions={
            'visible': True,
		    'timeVisible': True,
            'secondsVisible': True,
        }
    )


@callback(
    [Output("account-balance-chart", "seriesData"),
     Output("account-balance-chart", 'seriesOptions')],
    [Input(STRATEGY_STORE_MAPPINGS.account.id, 'data')],
    [
         State(STRATEGY_STORE_MAPPINGS.metrics.id, 'data'),
         State("account-balance-chart", 'seriesData'),
         State("account-balance-chart",'seriesOptions'),
         State(STRATEGY_STORE_MAPPINGS.time.id, 'data')
    ],
    # prevent_initial_call=True,
    suppress_callback_exceptions=True
)
def update_account_balance_chart(account, metrics, balance_series, chart_options, time):
    updateBaseline = False

    # Check if the balance series is empty and populate the starting balance
    if balance_series == None:
        balance_series = [[]]
        if metrics is None:
            return no_update, no_update
        balance_series[0].append(
            {"time": metrics["start_date"], "value": metrics["starting_cash"]})
        chart_options[0]["baseValue"]["price"] = metrics["starting_cash"]
        updateBaseline = True

    # Check if the balance has changed
    if balance_series[0][-1]["value"] == account["equity"]:
        return  balance_series if updateBaseline else no_update, chart_options if updateBaseline else no_update
    
    # Add a new data point to the series
    new_datapoint = [{"time": time, "value": account["equity"]}]
    # if balance_series[0][-1]["time"]  < time:
    #     balance_series[0].extend(new_datapoint)
    balance_series[0].extend(new_datapoint)

    return balance_series, chart_options if updateBaseline else no_update



def assetAllocationChart():
    return dcc.Graph(id="asset-allocation-chart", className="bg-primary-light")

@callback(
    [Output("asset-allocation-chart", "figure")],
    [Input(STRATEGY_STORE_MAPPINGS.account.id, 'data'),
     Input(STRATEGY_STORE_MAPPINGS.positions.id, 'data')],
    # prevent_initial_call=True,
    suppress_callback_exceptions=True
)
def update_asset_allocation_chart(account: IAccount, positions: IPosition):
        names = ["Portfolio", "Cash"]
        parents = ["", "Portfolio"]
        values = [0, account["cash"]]

        # print(positions)
        # Populate the names, parents and values lists
        if positions is not None:
            for symbol, position in positions.items():
                names.append(symbol)
                if position is None:
                    continue
                parents.append("Portfolio")
                values.append(position["market_value"])
        
        asset_allocation = go.Figure(go.Sunburst(
            labels=names,
            parents=parents,
            values=values,

        ), layout=go.Layout(
            plot_bgcolor='white',
            paper_bgcolor='#0a0f1a',
            font={"color": 'white'},
        ))
        return [asset_allocation]

account_porfolio_chart_section = html.Div([
    PlaceholderChart(title="Portfolio Balance Chart",
                     children=accountBalanceChart()),
    PlaceholderChart(title="Portfolio Distribution",
                     children=assetAllocationChart()),


], className="mt-8 grid grid-cols-1 lg:grid-cols-2 gap-6")


insight_details_section = html.Div([
    # InsightDetails(insight)
], className="mt-8")

recent_trades_section = html.Div([
    html.H2("Recent Trades", className="text-2xl font-bold mb-4 text-accent"),
    tradeTable("dashboard"),
], className="mt-8")

layout = html.Div([
    subnav(),
    html.Div(
        className="flex-grow container mx-auto py-8 text-white",
        children=[
            account_card_section,
            strategy_metrics_section,
            account_porfolio_chart_section,
            insight_details_section,
            recent_trades_section
        ])
])
