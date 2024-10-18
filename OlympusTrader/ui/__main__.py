import dash
from dash import dcc, html
from dash.dependencies import Input, Output
import pandas as pd

# external resources
external_stylesheets = ["https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.6.0/css/solid.min.css"]
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
                    ]
                )
            ]
        )

    ]
)

body = html.Main(
    children=dash.page_container
)

footer = html.Footer(
    className="bg-[#02050e] text-accent py-4 border-t border-accent",
    children=[
        html.Div(
            className="container mx-auto text-center",
            children=[
                html.P("© 2024 OlympusTrader. All rights reserved.")
            ]
        )
    ]
)

# Define the layout
app.layout = html.Div([header, body, footer], className="min-h-screen bg-primary flex flex-col")



# Run the server
if __name__ == '__main__':
    devMode = True
    if devMode:
        app.enable_dev_tools(
            dev_tools_ui=True,
            dev_tools_serve_dev_bundles=True,
        )
    
    app.run_server(debug=devMode, threaded=devMode)