
from dash import html, dcc, callback, register_page, no_update
from dash.dependencies import Input, Output, State

from OlympusTrader.ui.components.dashboardNav import subnav
from OlympusTrader.ui.interfaces.store import STRATEGY_SYNC_MAPPING

register_page(
    __name__, title="OlympusTrader - Settings", path='/settings')

layout = html.Div([
    subnav(),
    html.Div([

        html.H3("Settings 🚧", className="text-xl font-semibold text-accent mb-2"),
        html.P('This page is under construction. Please check back later.', className= "mb-4"),

        html.Div([
            # Strategy Sync Settings
            html.Div([
                html.Div([
                    html.H2('Strategy Sync Settings',
                            className="text-2xl font-semibold text-accent mb-4"),
                    html.Div([
                        html.Div([
                            html.Label(
                                'Sync Rate (seconds)', className="block text-sm font-medium text-accent mb-2"),
                            html.Div([
                                dcc.Input(
                                    id='sync-rate-input',
                                    type='number',
                                    min=1,
                                    className="bg-primary-light border border-accent text-white rounded-md px-4 py-2 flex-grow focus:outline-none focus:ring-2 focus:ring-accent"
                                ),
                                html.Button(
                                    'Apply',
                                    id='sync-rate-submit',
                                    className="px-4 py-2 bg-accent text-black rounded hover:bg-[#a88c5b] transition-colors flex items-center"
                                )
                            ], className="flex space-x-3"),
                            html.P('Current sync rate: ', id='current-sync-rate',
                                   className="text-sm text-gray-400 mt-2")
                        ])
                    ], className="space-y-4")
                ], className="bg-primary-foreground rounded-lg shadow-lg border border-accent p-6 mb-6")
            ], className="lg:col-span-2")
        ], className="grid grid-cols-1 lg:grid-cols-3 gap-8")
    ], className="flex-grow container mx-auto py-8 text-white")
])


@callback(
    [
        Output(STRATEGY_SYNC_MAPPING.id, 'n_intervals'),
        Output('current-sync-rate', 'children'),
    ],
    Input('sync-rate-submit', 'n_clicks'),
    [
        State('sync-rate-input', 'value'),
        State(STRATEGY_SYNC_MAPPING.id, 'n_intervals')
    ],
    prevent_initial_call=True
)
def update_sync_rate(n_clicks, value, current_n_intervals):
    if value is None:
        return no_update, f'Current sync rate: {(current_n_intervals/1000)} seconds'
    if value < 1:
        return no_update
    
    print(f"Updating sync rate from {current_n_intervals} to {value} seconds")

    interval = value * 1000  # Convert to milliseconds
    return interval, f'Current sync rate: {value} seconds'
