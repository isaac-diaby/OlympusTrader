import dash
from dash import html
from dash.dependencies import Input, Output


dash.register_page(
    __name__, title="OlympusTrader - Settings", path='/settings')

layout = html.Div([
    html.Div('Settings Page - Coming Soon',
            className="text-2xl bold text-accent"),


], className="flex-grow container mx-auto py-8 text-white")
