from dash import dcc, html


def subnav():
    return html.Nav(
    className="bg-primary-foreground border-b border-accent py-2",
    children=[
        html.Div(
            className="container mx-auto",
            children=[
                html.Ul(
                    className="flex space-x-4",
                    children=[
                        html.Li(
                            children=[
                                dcc.Link(
                                    "Dashboard",
                                    href="/",
                                    className="text-accent hover:text-white transition-colors"
                                )
                            ]
                        ),
                        html.Li(
                            children=[
                                dcc.Link(
                                    "Assets",
                                    href="/assets",
                                    className="text-accent hover:text-white transition-colors"
                                )
                            ]
                        ),
                        html.Li(
                            children=[
                                dcc.Link(
                                    "Settings",
                                    href="/settings",
                                    className="text-accent hover:text-white transition-colors"
                                )
                            ]
                        )
                    ]
                )
            ]
        )
    ]
)