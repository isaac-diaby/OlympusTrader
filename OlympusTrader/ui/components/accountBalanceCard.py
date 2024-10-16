
from dash import html


def AccountBalanceCard(balance, dailyChange):
    return html.Div([
        html.H3("Account Balance", className="text-xl font-semibold text-accent mb-2"),
        html.P(balance, className="text-2xl font-bold text-white"),
        html.P(f"{dailyChange} (24h)", className=f"text-sm {'text-green-500' if dailyChange.startswith('+') else 'text-red-500'}")
        ], className="bg-primary-foreground p-6 rounded-lg shadow-lg border border-accent")
