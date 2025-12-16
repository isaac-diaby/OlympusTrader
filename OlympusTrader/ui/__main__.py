from .app import app

if __name__ == "__main__":
    """ Run the dashboard app with `python -m OlympusTrader.ui` """
    devMode = True
    if devMode:
        app.enable_dev_tools(
            debug=True,
            dev_tools_ui=True,
            dev_tools_serve_dev_bundles=True,
        )
    app.run(debug=devMode, threaded=devMode)