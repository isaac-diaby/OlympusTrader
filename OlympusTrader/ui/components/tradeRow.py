from dash import html


def tradeRow( symbol: str, type: str, strategy: str, entry: float, exit: float, profitLoss: float):
    currencySymbol = "£"
    return  html.Tr([
                    html.Td(symbol, className="px-6 py-4  whitespace-nowrap text-sm text-white"),
                    html.Td(type, className="px-6 py-4  whitespace-nowrap text-sm text-white"),
                    html.Td(strategy, className="px-6 py-4  whitespace-nowrap text-sm text-white"),
                    html.Td(entry, className="px-6 py-4  whitespace-nowrap text-sm text-white"),
                    html.Td(exit, className="px-6 py-4  whitespace-nowrap text-sm text-white"),
                    html.Td(f"{currencySymbol}{profitLoss}", className=f"px-6 py-4  whitespace-nowrap text-sm {'text-green-500' if profitLoss > 0 else ('text-red-500' if profitLoss < 0 else 'text-white')}"),
                ])