
from dash import html


def dashboardCard(title: str, value: float, icon: str = ""):
    return html.Div([
        html.Div([
            html.H3(title, className="text-xl font-semibold mb-2 text-accent"),
            html.I(None, className=icon)
        ]),
        html.P(value, className="text-2xl font-bold text-white")
    ], className="bg-primary-foreground p-6 rounded-lg shadow-lg border border-accent")
