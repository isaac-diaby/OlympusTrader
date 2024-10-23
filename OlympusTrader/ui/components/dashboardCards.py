
from dash import html

from OlympusTrader.insight.insight import IInsight, InsightState


def dashboardCard(title: str, value: float, icon: str = ""):
    return html.Div([
        html.Div([
            html.H3(title, className="text-xl font-semibold mb-2 text-accent"),
            html.I(None, className=icon)
        ]),
        html.P(value, className="text-2xl font-bold text-white")
    ], className="bg-primary-foreground p-6 rounded-lg shadow-lg border border-accent")

def dashboardCardInsights (title: str, insights: dict[str, IInsight]):
    insightsByStatus = {}
    for insight in insights.values():
        if insight['state'] not in insightsByStatus:
            insightsByStatus[insight['state']] = 1
        else:
            insightsByStatus[insight['state']] += 1

    displayInsights_byStatus = [ html.Div([
                html.P(status, className="text-sm text-accent"),
                html.P(count, className="text-2xl font-bold text-white")
            ], className="flex items-center justify-between") for status, count in insightsByStatus.items()]

    # numberOfFilledInsights = len([insight for insight in insights.values(
    # ) if insight['state'] == str(InsightState.FILLED)])
    return html.Div([
        html.Div([
            html.H3(title, className="text-xl font-semibold mb-2 text-accent"),
        ]),

        html.Div([
            html.P("Total", className="text-sm text-accent"),
            html.P(len(insights), className="text-2xl font-bold text-white")
        ], className="flex items-center justify-between"),
        *displayInsights_byStatus
        
        # html.P(value, className="text-2xl font-bold text-white")
    ], className="bg-primary-foreground p-6 rounded-lg shadow-lg border border-accent")


def dashboardCardMode(title: str, mode: str, accountType: str, connected: bool):
    return html.Div([
        html.Div([
            html.H3(title, className="text-xl font-semibold mb-2 text-accent"),
            html.Span([
                html.Span(className=f"animate-ping absolute inline-flex h-full w-full rounded-full opacity-75 {
                          'bg-green-400' if connected else 'bg-red-400'} "),
                html.Span(className=f"relative inline-flex rounded-full h-3 w-3 {
                          'bg-green-500' if connected else 'bg-red-500'}")
            ],
                className="relative flex h-3 w-3"
            )
        ], className="flex items-center justify-between"),
        html.P(accountType.replace('_', ' ').lower().capitalize(), className="text-2xl font-bold text-white"),
        html.P(mode, className="text-2xl font-bold text-white")
    ], className="bg-primary-foreground p-6 rounded-lg shadow-lg border border-accent")
