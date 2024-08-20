# Building and running your bot with Docker

This guide will show you how to build and run your bot using Docker. initally it will use the main.py file to run the bot, but you can also run the bot with the UI option enabled.

When you're ready, Trading bot by running:
`docker compose up --build`.

you can add th `--detach` flag to run the container in the background.

If you have the UI option enabled, you will be able to view the bots performance at http://localhost:8501.

## Stopping your application

When you're ready to stop your bot, press `Ctrl+C` in your terminal.

Then, stop your application by running:
`docker compose down`.

## References

* [Docker's Python guide](https://docs.docker.com/language/python/)