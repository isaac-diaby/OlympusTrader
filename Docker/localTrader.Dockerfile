FROM python:3.12-bookworm as builder

# Prevents Python from writing pyc files.
ENV PYTHONDONTWRITEBYTECODE=1

# Keeps Python from buffering stdout and stderr to avoid situations where
# the application crashes without emitting any logs due to buffering.
ENV PYTHONUNBUFFERED=1


RUN pip install poetry==1.8.3

ENV POETRY_NO_INTERACTION=1 \
    POETRY_VIRTUALENVS_IN_PROJECT=1 \
    POETRY_VIRTUALENVS_CREATE=1 \
    POETRY_CACHE_DIR=/tmp/poetry_cache

WORKDIR /app

# Install TA Lib
RUN apt-get update && apt-get install -y \
    build-essential \
    wget \
    && rm -rf /var/lib/apt/lists/*

RUN wget http://prdownloads.sourceforge.net/ta-lib/ta-lib-0.4.0-src.tar.gz && \
    tar -xvzf ta-lib-0.4.0-src.tar.gz && \
    cd ta-lib/ && \
    ./configure --prefix=/usr && \
    make && \
    make install && \
    cd .. && \
    rm -rf ta-lib ta-lib-0.4.0-src.tar.gz

COPY OlympusTrader OlympusTrader
COPY pyproject.toml poetry.lock README.md ./

# Install with the project root and TA Lib extras
RUN --mount=type=cache,target=$POETRY_CACHE_DIR poetry install -E talib 

# ----------------------

FROM python:3.12-slim-bookworm  as runtime

WORKDIR /app
# Prevents Python from writing pyc files.
ENV PYTHONDONTWRITEBYTECODE=1

# Keeps Python from buffering stdout and stderr to avoid situations where
# the application crashes without emitting any logs due to buffering.
ENV PYTHONUNBUFFERED=1

# Install TA Lib
RUN apt-get update && apt-get install -y \
    build-essential \
    wget \
    && rm -rf /var/lib/apt/lists/*

# RUN wget http://prdownloads.sourceforge.net/ta-lib/ta-lib-0.4.0-src.tar.gz && \
#     tar -xvzf ta-lib-0.4.0-src.tar.gz && \
#     cd ta-lib/ && \
#     ./configure --prefix=/usr && \
#     make && \
#     make install && \
#     cd .. && \
#     rm -rf ta-lib ta-lib-0.4.0-src.tar.gz

COPY --from=builder /usr/lib/libta* /usr/lib/
COPY --from=builder /usr/include/libta* /usr/include/

COPY OlympusTrader OlympusTrader

# Create a non-privileged user that the app will run under.
# See https://docs.docker.com/go/dockerfile-user-best-practices/
ARG UID=10001
RUN adduser \
--disabled-password \
--gecos "" \
--home "/nonexistent" \
--shell "/sbin/nologin" \
--no-create-home \
--uid "${UID}" \
trader
# Switch to the non-privileged user to run the application.
RUN mkdir -p data
RUN mkdir -p backtests
RUN chown -R trader:trader data
RUN chown -R trader:trader backtests

USER trader

ENV VIRTUAL_ENV=/app/.venv \
    PATH="/app/.venv/bin:$PATH" \
    NUMBA_CACHE_DIR=/tmp/numba_cache \
    TA_LIBRARY_PATH=/usr/lib \
    TA_INCLUDE_PATH=/usr/include



COPY --from=builder ${VIRTUAL_ENV} ${VIRTUAL_ENV}

ARG STRATEGY
COPY strategies/$STRATEGY strategy

ENV STRATEGY=$STRATEGY
CMD ["python", "strategy/__init__.py"]
# CMD ["python", "-m", "strategy.$STRATEGY"]
# ENTRYPOINT ["python", "-m", "strategy"]


# FROM python:3.12-bookworm as runtime

# # Prevents Python from writing pyc files.
# ENV PYTHONDONTWRITEBYTECODE=1

# # Keeps Python from buffering stdout and stderr to avoid situations where
# # the application crashes without emitting any logs due to buffering.
# ENV PYTHONUNBUFFERED=1

# RUN pip install poetry==1.8.3

# ENV POETRY_NO_INTERACTION=1 \
#     POETRY_VIRTUALENVS_IN_PROJECT=1 \
#     POETRY_VIRTUALENVS_CREATE=1 \
#     POETRY_CACHE_DIR=/tmp/poetry_cache

# WORKDIR /app

# # Install TA Lib
# RUN apt-get update && apt-get install -y \
#     build-essential \
#     wget \
#     && rm -rf /var/lib/apt/lists/*

# RUN wget http://prdownloads.sourceforge.net/ta-lib/ta-lib-0.4.0-src.tar.gz && \
#     tar -xvzf ta-lib-0.4.0-src.tar.gz && \
#     cd ta-lib/ && \
#     ./configure --prefix=/usr && \
#     make && \
#     make install && \
#     cd .. && \
#     rm -rf ta-lib ta-lib-0.4.0-src.tar.gz

# COPY  OlympusTrader OlympusTrader
# COPY pyproject.toml poetry.lock ./

# # Install with the project root and TA Lib extras

# RUN --mount=type=cache,target=$POETRY_CACHE_DIR poetry install -E talib

# # Create a non-privileged user that the app will run under.
# # See https://docs.docker.com/go/dockerfile-user-best-practices/
# # ARG UID=10001
# # RUN adduser \
# # --disabled-password \
# # --gecos "" \
# # --home "/nonexistent" \
# # --shell "/sbin/nologin" \
# # --no-create-home \
# # --uid "${UID}" \
# # trader
# # Switch to the non-privileged user to run the application.
# # RUN mkdir -p data
# # RUN mkdir -p backtests
# # RUN chown -R trader:trader data
# # RUN chown -R trader:trader backtests

# # USER trader

# # ENV TA_LIBRARY_PATH=/usr/lib \
# #     TA_INCLUDE_PATH=/usr/include

# ARG STRATEGY
# COPY strategies/$STRATEGY strategy

# ENV STRATEGY=$STRATEGY
# CMD ["python", "strategy/__init__.py"]