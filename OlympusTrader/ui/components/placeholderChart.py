from dash import html

def PlaceholderChart(title: str):
    return html.Div(
        className='bg-[#0a0f1a] p-6 rounded-lg shadow-lg border border-accent',
        children=[
            html.H3(
                className='text-xl font-semibold text-accent mb-4',
                children=title
            ),
            html.Div(
                className='h-64 bg-primary-light rounded flex items-center justify-center',
                children=[
                    html.P(
                        className='text-accent',
                        children='Chart Placeholder'
                    )
                ]
            )
        ]
    )