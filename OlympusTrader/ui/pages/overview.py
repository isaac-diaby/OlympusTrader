import dash
from dash import dcc, html
from dash.dependencies import Input, Output
import pandas as pd

from OlympusTrader.ui.components.accountBalanceCard import AccountBalanceCard
from OlympusTrader.ui.components.insightDetail import InsightDetails
from OlympusTrader.ui.components.placeholderChart import PlaceholderChart

dash.register_page(__name__, title="OlympusTrader - Overview", path='/')

account_card_section = html.Div([
    # TODO: Account Balance Card 
    AccountBalanceCard(balance="£50,000", dailyChange="+£1,200")
    # <DashboardCard title="Total Profit" value="$12,345" icon={<DollarSign />} />
    # <DashboardCard title="Active Trades" value="8" icon={<Activity />} />
    # <DashboardCard title="Win Rate" value="68%" icon={<PieChart />} />

   
], className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6")

account_porfolio_chart_section = html.Div([
    PlaceholderChart(title="Portfolio Chart"),
    PlaceholderChart(title="Asset Allocation"),
    # dcc.Graph(
    #     figure={
    #         'data': [
    #             {'x': [1, 2, 3, 4], 'y': [50000, 49980, 50030,  50680], 'type': 'line'},
    #         ],
    #         'layout': {
    #             'title': 'Profit/Loss Chart'
    #         }
    #     },
    # ), 
    # dcc.Graph(
    #     figure={
    #         'data': [
    #             {'x': [1], 'y': [10000], 'type': 'bar', 'name': 'BTC/USD'},
    #             {'x': [1], 'y': [24500], 'type': 'bar', 'name': 'ETH/USD'},
    #         ],
    #         'layout': {
    #             'title': 'Asset Allocation'
    #         }
    #     }
    # )

], className="mt-8 grid grid-cols-1 lg:grid-cols-2 gap-6")

insight = {
    "INSIGHT_ID": "12345",
    "PARENT": None,
    "order_id": "54321",
    "side": "buy",
    "symbol": "AAPL",
    "quantity": 100,
    "contracts": 10,
    "type": "market",
    "classType": "equity",
    "limit_price": 150.0,
    "TP": [155.0, 160.0],
    "SL": 145.0,
    "strategyType": "momentum",
    "confidence": 0.85,
    "tf": "1D",
    "state": "new",
    "createAt": "2023-10-01T12:00:00Z",
    "updatedAt": "2023-10-02T12:00:00Z",
    "filledAt": None,
    "closedAt": None,
    "close_price": None
}

insight_details_section = html.Div([
            # <InsightDetails insight={mockInsight} />
            InsightDetails(insight)

], className="mt-8")

recent_trades_section = html.Div([
    html.H2("Recent Trades", className="text-2xl font-bold mb-4 text-accent"),
    html.Div([
        html.Table([
            html.Thead([
                html.Tr([
                    html.Th("Asset", className="px-6 py-3 text-left text-xs font-medium text-accent uppercase tracking-wider"),
                    html.Th("Type", className="px-6 py-3 text-left text-xs font-medium text-accent uppercase tracking-wider"),
                    html.Th("Strategy", className="px-6 py-3 text-left text-xs font-medium text-accent uppercase tracking-wider"),
                    html.Th("Entry", className="px-6 py-3 text-left text-xs font-medium text-accent uppercase tracking-wider"),
                    html.Th("Exit", className="px-6 py-3 text-left text-xs font-medium text-accent uppercase tracking-wider"),
                    html.Th("Profit/Loss", className="px-6 py-3 text-left text-xs font-medium text-accent uppercase tracking-wider"),
                ])
            ], className="bg-primary-light"),
            html.Tbody([
                html.Tr([
                    html.Td("BTC/USD", className="px-6 py-3"),
                    html.Td("Long", className="px-6 py-3"),
                    html.Td("Trend Following", className="px-6 py-3"),
                    html.Td("32,450", className="px-6 py-3"),
                    html.Td("33,100", className="px-6 py-3"),
                    html.Td("+$650", className="px-6 py-3"),
                ]),
                html.Tr([
                    html.Td("ETH/USD", className="px-6 py-3"),
                    html.Td("Short", className="px-6 py-3"),
                    html.Td("Mean Reversion", className="px-6 py-3"),
                    html.Td("2,100", className="px-6 py-3"),
                    html.Td("2,050", className="px-6 py-3"),
                    html.Td("+$50", className="px-6 py-3"),
                ]),
                html.Tr([
                    html.Td("XRP/USD", className="px-6 py-3"),
                    html.Td("Long", className="px-6 py-3"),
                    html.Td("Breakout", className="px-6 py-3"),
                    html.Td("0.45", className="px-6 py-3"),
                    html.Td("0.43", className="px-6 py-3"),
                    html.Td("-$20", className="px-6 py-3"),
                ])
            ], className="bg-primary-foreground divide-y divide-accent")
        ], className="w-full")
    ], className="bg-primary-foreground shadow rounded-lg overflow-hidden border border-accent")
], className="mt-8")

layout = html.Div([
    account_card_section,
    account_porfolio_chart_section,
    insight_details_section,
    recent_trades_section
])

# Initialize the Dash app
app = dash.Dash(__name__)

# Define the layout
app.layout = layout

# Run the server
if __name__ == '__main__':
    app.run_server(debug=True)
