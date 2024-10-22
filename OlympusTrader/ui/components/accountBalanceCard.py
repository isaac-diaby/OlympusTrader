
import dash
from dash import html, Output, Input, callback
import numpy as np


def AccountBalanceCard(balance: float, alltimeChange: float, dailyChange: float):
    currencySymbol = "£"
    return html.Div([
        html.H3("Account Balance",
                className="text-xl font-semibold text-accent mb-2"),
        html.P(f"{currencySymbol}{balance}",
               className="text-2xl font-bold text-white"),
        html.P(f"{currencySymbol}{alltimeChange} ~ {np.round((((balance+alltimeChange)/balance)-1)*100, 2)
                                                    }%", className=f"text-sm {'text-green-500' if alltimeChange > 0 else 'text-red-500' if alltimeChange < 0 else 'text-wite'}"),
        html.P(f"{currencySymbol}{dailyChange} ~ {np.round((((balance+dailyChange)/balance)-1)*100, 2)
                                                  }% (24h)", className=f"text-sm {'text-green-500' if dailyChange > 0 else 'text-red-500' if dailyChange < 0 else 'text-wite'}"),
    ], 
    className="bg-primary-foreground p-6 rounded-lg shadow-lg border border-accent")

