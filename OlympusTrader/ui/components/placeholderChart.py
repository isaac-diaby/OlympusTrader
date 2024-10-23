from dash import html


def PlaceholderChart(title: str, children=None):
    return html.Div(
        className='bg-primary-foreground p-6 rounded-lg shadow-lg border border-accent',
        children=[
            html.H3(
                className='text-xl font-semibold text-accent mb-4',
                children=title
            ),
            (html.Div(
                className='reletive min-h-64 bg-primary-light rounded flex items-center justify-center',
                children=[
                    html.P(
                        className='text-accent',
                        children='Chart Placeholder'
                    )
                ]
            ) if children is None else html.Div(
                className='reletive overflow-hidden  min-h-64 rounded flex items-center justify-center',
                children=children
            ))
        ]
    )
