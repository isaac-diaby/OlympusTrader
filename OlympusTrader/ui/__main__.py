import dash
from dash import dcc, html
from dash.dependencies import Input, Output
import pandas as pd

# external resources
external_stylesheets = []
external_scripts = ["https://cdn.tailwindcss.com"]
# Initialize the Dash app
app = dash.Dash(__name__,
                external_scripts=external_scripts,
                external_stylesheets=external_stylesheets,
                use_pages=True)



header = html.Header(
    className="text-white p-4 border-b border-accent",
    children=[
        html.Div(
            className="container mx-auto flex items-center justify-between",
            children=[
                html.Div(
                    className="flex items-center",

                    children = [
                        # TODO: Add logo
                        html.H1("OlympusTrader", className="text-2xl"),
                        ]),

                html.Nav(
                    className="flex space-x-4",
                    children=[
                        dcc.Link(f"{page['name']}", href=page["relative_path"]) for page in dash.page_registry.values()
                        # html.A("Overview", href="/"),
                        # html.A("Strategies", href="/strategies"),
                        # html.A("Settings", href="/settings"),
                    ]
                )
            ]
        )

    ]
)

body = html.Main(
    className="flex-grow container mx-auto py-8 text-white",
    children=dash.page_container
    
)

# Define the layout
app.layout = html.Div([header, body], className="min-h-screen bg-primary flex flex-col")



# html.Div([
#     html.H1("OlympusTrader"),
#     html.Div([
#         html.Div(
#             dcc.Link(f"{page['name']} - {page['path']}", href=page["relative_path"])
#         ) for page in dash.page_registry.values()
#     ]),
#     dash.page_container
#     ],
#     )



# Run the server
if __name__ == '__main__':
    app.run_server(debug=True)