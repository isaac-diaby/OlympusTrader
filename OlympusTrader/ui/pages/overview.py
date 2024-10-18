import dash
from dash import dcc, html
from dash.dependencies import Input, Output
import numpy as np
import pandas as pd
from dash_tvlwc import Tvlwc
from dash_tvlwc.types import SeriesType, LineType, ColorType
import plotly.graph_objects as go
import plotly.express as px


from OlympusTrader.ui.components.accountBalanceCard import AccountBalanceCard
from OlympusTrader.ui.components.dashboardCard import dashboardCard
from OlympusTrader.ui.components.insightDetail import InsightDetails
from OlympusTrader.ui.components.placeholderChart import PlaceholderChart
from OlympusTrader.ui.components.tradeRow import tradeRow
from OlympusTrader.ui.components.dashboardNav import subnav

dash.register_page(__name__, title="OlympusTrader - Overview", path='/')


account_card_section = html.Div([
    AccountBalanceCard(balance=50_000.00,
                       alltimeChange=12_345.00, dailyChange=1_200.00),
    dashboardCard(title="Active Insights", value=8,
                  icon="fa-thin fa-magnifying-glass-chart"),
    dashboardCard(title="Win Rate", value="68%", icon="fa-thin fa-chart-pie"),
    dashboardCard(title="Total Insights", value="69",
                  icon="fa-thin fa-chart-pie"),




], className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6")

balance_series = [{"time": time.strftime('%Y-%m-%d'), "value": value} for time, value in zip(
    pd.date_range(start="2023-01-01", periods=100), np.random.randint(40_000, 60_000, 100))]


def accountBalanceChart():
    return Tvlwc(
        id='account-balance-chart',
        seriesTypes=[SeriesType.Baseline],
        seriesData=[balance_series],
        seriesOptions=[{
            'baseValue': {'type': 'price', 'price': 50_000},
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
            'timeScale': {'visible': True},
            'grid': {'vertLines': {'visible': False}, 'horzLines': {'style': 0, 'color': '#be9e6b80'}},
            'layout': {'textColor': '#fffffa', 'background': {'type':  ColorType.Solid, 'color': '#0a0f1a'}}

        }
    )


# Define the data
names = ["Portfolio", "Cash", "BTC/USD", "BTC/USD-1", "BTC/USD-2", "ETH/USD"]
parents = ["", "Portfolio", "Portfolio", "BTC/USD", "BTC/USD", "Portfolio"]
values = [0, 30_000, 10_000, 5_000, 5_000, 2_000]

fig = go.Figure(go.Sunburst(
    labels=names,
    parents=parents,
    values=values,

), layout=go.Layout(
    plot_bgcolor='white',
    paper_bgcolor='#0a0f1a',
    font={"color": 'white'},
))


def assetAllocationChart():
    return dcc.Graph(id="accet-allocation-chart", figure=fig, className="bg-primary-light"),


account_porfolio_chart_section = html.Div([
    PlaceholderChart(title="Portfolio Balance Chart",
                     children=accountBalanceChart()),
    PlaceholderChart(title="Portfolio Distribution",
                     children=assetAllocationChart()),


], className="mt-8 grid grid-cols-1 lg:grid-cols-2 gap-6")

insight = [
    {
        "INSIGHT_ID": "550e8400-e29b-41d4-a716-446655440000",
        "PARENT": None,
        "CHILDREN": {
            "660e8400-e29b-41d4-a716-446655440001": {
                "INSIGHT_ID": "660e8400-e29b-41d4-a716-446655440001",
                "PARENT": "550e8400-e29b-41d4-a716-446655440000",
                "CHILDREN": {},
                "order_id": "ORD123457",
                "side": "sell",
                "symbol": "BTC/USD",
                "quantity": 0.25,
                "contracts": 1,
                "type": "market",
                "classType": "take_profit",
                "strategyType": "trend_following",
                "confidence": 0.75,
                "tf": "1h",
                "state": "FILLED",
                "createAt": "2024-03-15T11:30:00Z",
                "updatedAt": "2024-03-15T11:35:00Z",
                "filledAt": "2024-03-15T11:40:00Z",
                "closedAt": "2024-03-15T12:00:00Z",
                "close_price": 36000,
            }
        },
        "order_id": "ORD123456",
        "side": "buy",
        "symbol": "BTC/USD",
        "quantity": 0.5,
        "contracts": 1,
        "type": "limit",
        "classType": "bracket",
        "limit_price": 35000,
        "TP": [36000, 37000],
        "SL": 34000,
        "strategyType": "trend_following",
        "confidence": 0.85,
        "tf": "1h",
        "state": "FILLED",
        "createAt": "2024-03-15T10:30:00Z",
        "updatedAt": "2024-03-15T10:35:00Z",
        "filledAt": "2024-03-15T10:40:00Z",
        "closedAt": None,
        "close_price": None,
    },
    {
        "INSIGHT_ID": "770e8400-e29b-41d4-a716-446655440002",
        "PARENT": None,
        "CHILDREN": {},
        "order_id": "ORD123458",
        "side": "sell",
        "symbol": "ETH/USD",
        "quantity": 2,
        "contracts": 1,
        "type": "market",
        "classType": "single",
        "strategyType": "mean_reversion",
        "confidence": 0.7,
        "tf": "4h",
        "state": "FILLED",
        "createAt": "2024-03-15T09:00:00Z",
        "updatedAt": "2024-03-15T09:05:00Z",
        "filledAt": "2024-03-15T09:10:00Z",
        "closedAt": "2024-03-15T13:10:00Z",
        "close_price": 2050,
    }
]


insight_details_section = html.Div([
    # InsightDetails(insight)
], className="mt-8")

recent_trades_section = html.Div([
    html.H2("Recent Trades", className="text-2xl font-bold mb-4 text-accent"),
    html.Div([
        html.Table([
            html.Thead([
                html.Tr([
                    html.Th(
                        "Asset", className="px-6 py-3 text-left text-xs font-medium text-accent uppercase tracking-wider"),
                    html.Th(
                        "Type", className="px-6 py-3 text-left text-xs font-medium text-accent uppercase tracking-wider"),
                    html.Th(
                        "Strategy", className="px-6 py-3 text-left text-xs font-medium text-accent uppercase tracking-wider"),
                    html.Th(
                        "Entry", className="px-6 py-3 text-left text-xs font-medium text-accent uppercase tracking-wider"),
                    html.Th(
                        "Exit", className="px-6 py-3 text-left text-xs font-medium text-accent uppercase tracking-wider"),
                    html.Th(
                        "Profit/Loss", className="px-6 py-3 text-left text-xs font-medium text-accent uppercase tracking-wider"),
                ])
            ], className="bg-primary-light"),
            html.Tbody([
                tradeRow("btc/usd", "long", "breakout", 50000, 51000, 650),
                tradeRow("eth/usd", "short", "mean reversion", 2100, 2050, 50),
                tradeRow("xrp/usd", "long", "breakout", 0.45, 0.43, -20)

            ], className="bg-primary-foreground divide-y divide-accent")
        ], className="w-full")
    ], className="bg-primary-foreground shadow rounded-lg overflow-hidden border border-accent")
], className="mt-8")

layout = html.Div([
    subnav(),
    html.Div(
        className="flex-grow container mx-auto py-8 text-white",
        children=[
            account_card_section,
            account_porfolio_chart_section,
            insight_details_section,
            recent_trades_section
        ])
])
