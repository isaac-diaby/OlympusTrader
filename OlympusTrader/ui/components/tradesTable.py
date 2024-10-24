from typing import Optional
from dash import html, dcc, callback, no_update
from dash.dependencies import Input, Output, State, MATCH
from dash.exceptions import PreventUpdate


from OlympusTrader.broker.interfaces import IOrderSide, IPosition
from OlympusTrader.insight.insight import IInsight, InsightState
from OlympusTrader.ui.interfaces.store import STRATEGY_STORE_MAPPINGS


def tradeRow(insight: IInsight, position: Optional[IPosition]):
    # TODO: change this to use the currency symbol from the account
    currencySymbol = "£"

    def calculateProfitLoss(insight):
        if position == None:
            return 0

        # Check if the insight has been filled
        if insight["state"] != InsightState.FILLED.value:
            return 0

        currentPrice = insight["close_price"] if insight["close_price"] != None else position["current_price"]
        match insight["side"]:
            case IOrderSide.BUY.value:
                return (currentPrice - insight["limit_price"]) * insight.get("quantity", 0)
            case IOrderSide.SELL.value:
                return (insight["limit_price"] - currentPrice) * insight.get("quantity", 0)
            case _:
                print("Invalid side value - tradeRow()")
                return 0

    profitLoss = calculateProfitLoss(insight)
    return html.Tr([
        html.Td(
            insight["insight_id"], className="px-6 py-4 whitespace-nowrap text-sm text-white"),
        html.Td(
            insight["symbol"], className="px-6 py-4 whitespace-nowrap text-sm text-white"),
        html.Td(
            insight["side"], className="px-6 py-4 whitespace-nowrap text-sm text-white"),
        html.Td(
            insight["type"], className="px-6 py-4 whitespace-nowrap text-sm text-white"),
        html.Td(
            insight["strategy"], className="px-6 py-4 whitespace-nowrap text-sm text-white"),
        html.Td(
            insight["contracts"] if insight["useContractSize"] else insight["quantity"], className="px-6 py-4  whitespace-nowrap text-sm text-white"),
        html.Td(
            insight["limit_price"], className="px-6 py-4 whitespace-nowrap text-sm text-white"),
        html.Td(
            insight["close_price"], className="px-6 py-4 whitespace-nowrap text-sm text-white"),
        html.Td(f"{currencySymbol}{profitLoss}",
                className=f"px-6 py-4  whitespace-nowrap text-sm {'text-green-500' if (profitLoss > 0) else 'text-red-500' if (profitLoss < 0) else 'text-white'}")
    ], className="hover:bg-primary-light cursor-pointer")


def tradeTable(index_id, FILTERS={}):

    return html.Div([
        html.Table([
            html.Thead([
                html.Tr([
                   html.Th(
                       "Insight ID", className="px-6 py-3 text-left text-xs font-medium text-accent uppercase tracking-wider"),
                   html.Th(
                       "Asset", className="px-6 py-3 text-left text-xs font-medium text-accent uppercase tracking-wider"),
                   html.Th(
                       "Side", className="px-6 py-3 text-left text-xs font-medium text-accent uppercase tracking-wider"),
                   html.Th(
                       "Type", className="px-6 py-3 text-left text-xs font-medium text-accent uppercase tracking-wider"),
                   html.Th(
                       "Strategy", className="px-6 py-3 text-left text-xs font-medium text-accent uppercase tracking-wider"),
                   html.Th(
                       "size", className="px-6 py-3 text-left text-xs font-medium text-accent uppercase tracking-wider"),
                   html.Th(
                       "Entry", className="px-6 py-3 text-left text-xs font-medium text-accent uppercase tracking-wider"),
                   html.Th(
                       "Exit", className="px-6 py-3 text-left text-xs font-medium text-accent uppercase tracking-wider"),
                   html.Th(
                       "Profit/Loss", className="px-6 py-3 text-left text-xs font-medium text-accent uppercase tracking-wider"),
                   ])
            ], className="bg-primary-light"),
            html.Tbody(id={'type': 'trades-table-body', 'index': index_id},
                       className="bg-primary-foreground divide-y divide-accent"),
            dcc.Store(id={'type': 'trades-table-body-filter',
                      'index': index_id}, data=FILTERS)
        ], className="w-full")

    ], className="bg-primary-foreground overflow-x-auto shadow rounded-lg overflow-hidden border border-accent")


@callback(Output({'type': 'trades-table-body', 'index': MATCH}, 'children'),
          Input(STRATEGY_STORE_MAPPINGS.insights.id, 'data'),
          Input(STRATEGY_STORE_MAPPINGS.positions.id, 'data'),
          [
              State({'type': 'trades-table-body-filter', 'index': MATCH}, 'data'),
              State({'type': 'trades-table-body', 'index': MATCH}, 'children')
])
def update_trade_table_body(insights, positions, filter, children):
    def filterInsights(insights, filters: Optional[dict]):
        filterdInsights = []

        if filter == None:
            return insights

        for insight in insights.values():

            if all([(insight.get(key) == value) for key, value in filters.items()]):
                # Match all of the filters
                filterdInsights.append(insight)

        return filterdInsights

    if insights == None:
        raise PreventUpdate

    if filter == None:
        raise PreventUpdate

    entries = filterInsights(insights, filter)

    # If there are no entries and there are children, return no update
    if children != None and len(entries) == 0:
        return []

    # If there are no entries and no children, return no update
    if len(entries) == 0:
        return no_update

    # If there are entries, return the trade rows and update the table
    return [tradeRow(insight, (positions.get(insight["symbol"], None) if insight["symbol"] in positions else positions.get(insight["order_id"], None) )) for insight in entries]
