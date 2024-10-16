import dash
from dash import dcc, html
from dash.dependencies import Input, Output
import datetime

# insight = {
#     "INSIGHT_ID": "12345",
#     "PARENT": None,
#     "order_id": "54321",
#     "side": "buy",
#     "symbol": "AAPL",
#     "quantity": 100,
#     "contracts": 10,
#     "type": "market",
#     "classType": "equity",
#     "limit_price": 150.0,
#     "TP": [155.0, 160.0],
#     "SL": 145.0,
#     "strategyType": "momentum",
#     "confidence": 0.85,
#     "tf": "1D",
#     "state": "new",
#     "createAt": "2023-10-01T12:00:00Z",
#     "updatedAt": "2023-10-02T12:00:00Z",
#     "filledAt": None,
#     "closedAt": None,
#     "close_price": None
# }

def InsightDetails(insight):
    def format_date(date_string):
        if not date_string:
            return 'N/A'
        return datetime.datetime.fromisoformat(date_string.replace("Z", "+00:00")).strftime('%Y-%m-%d %H:%M:%S')
    
    def get_state_icon(state):
        icons = {
            'new': '🕒',
            'filled': '✅',
            'cancelled': '⚠️',
            'closed': '✅'
        }
        return icons.get(state.lower(), '')
    
    def detail_item(label, value, icon=None):
        return html.Div([
            html.Span(f"{label}:", className="text-[#be9e6b]"),
            html.Span([
                html.Span(icon, className="mr-2") if icon else '',
                html.Span(value, className="text-white")
            ], className="flex items-center")
        ], className="flex items-center justify-between border-b border-[#be9e6b] py-2")

    return  html.Div([
            html.Div([
                html.H2("Insight Details", className="text-2xl font-bold text-[#be9e6b] mb-4"),
                html.Div([
                    detail_item("Insight ID", insight["INSIGHT_ID"]),
                    detail_item("Parent ID", insight["PARENT"] or 'N/A'),
                    detail_item("Order ID", insight["order_id"] or 'N/A'),
                    detail_item("Side", insight["side"] or 'N/A', icon='📈' if insight["side"] == 'buy' else '📉'),
                    detail_item("Symbol", insight["symbol"] or 'N/A'),
                    detail_item("Quantity", str(insight["quantity"]) or 'N/A'),
                    detail_item("Contracts", str(insight["contracts"]) or 'N/A'),
                    detail_item("Type", insight["type"] or 'N/A'),
                    detail_item("Class Type", insight["classType"] or 'N/A'),
                    detail_item("Limit Price", str(insight["limit_price"]) or 'N/A'),
                    detail_item("Take Profit", ', '.join(map(str, insight["TP"])) if insight["TP"] else 'N/A'),
                    detail_item("Stop Loss", str(insight["SL"]) or 'N/A'),
                    detail_item("Strategy Type", insight["strategyType"] or 'N/A'),
                    detail_item("Confidence", f"{insight['confidence'] * 100:.2f}%" if insight["confidence"] else 'N/A'),
                    detail_item("Timeframe", insight["tf"] or 'N/A'),
                    detail_item("State", insight["state"], icon=get_state_icon(insight["state"])),
                    detail_item("Created At", format_date(insight["createAt"]), icon='🕒'),
                    detail_item("Updated At", format_date(insight["updatedAt"]), icon='🕒'),
                    detail_item("Filled At", format_date(insight["filledAt"]), icon='🕒'),
                    detail_item("Closed At", format_date(insight["closedAt"]), icon='🕒'),
                    detail_item("Close Price", str(insight["close_price"]) or 'N/A')
                ], className="grid grid-cols-1 md:grid-cols-2 gap-4")
            ], className="bg-[#0a0f1a] rounded-lg shadow-lg border border-[#be9e6b] p-6")
        ])
       
