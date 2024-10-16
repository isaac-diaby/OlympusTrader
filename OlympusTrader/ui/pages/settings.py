import dash
from dash import dcc, html
from dash.dependencies import Input, Output
import pandas as pd

dash.register_page(__name__, title="OlympusTrader - Settings", path='/settings')

layout = html.Div([
    html.H1('Settings Page - Coming Soon', className="text-2xl bold text-accent"),
    
])
