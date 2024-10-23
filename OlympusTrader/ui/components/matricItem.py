from dash import html
def MatricItem(label: str, value: str):
    return html.Div(
        # className='matric-item',
        children=[
            html.H4(label, className="text-accent text-sm"),
            html.P(value, className="text-white text-lg font-semibold")
        ]
    )