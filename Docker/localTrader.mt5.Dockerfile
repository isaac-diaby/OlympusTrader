# FROM gmag11/metatrader5_vnc as builder

# # Set environment variables
# ENV PYTHONDONTWRITEBYTECODE=1
# ENV PYTHONUNBUFFERED=1

# # Install pip and winetricks TA Lib dependencies
# RUN apt-get update && apt-get install -y \
#     build-essential \
#     python3-pip \
#     winetricks \
#     xvfb \
#     wget \
#     && rm -rf /var/lib/apt/lists/*

# # Configure Wine to run in a virtual desktop mode
# RUN winetricks settings win10
# RUN winetricks vd=1024x768

# # Install Poetry
# # RUN wine cmd /c "python -m ensurepip" && wine cmd /c "pip install --upgrade pip"
# # RUN  xvfb-run --auto-servernum --server-args="-screen 0 1024x768x24"  wine cmd /c "pip install poetry==1.8.3"
# RUN pip install poetry==1.8.3
# # RUN  wine cmd /c "pip install poetry==1.8.3"

# ENV POETRY_NO_INTERACTION=1 \
#     POETRY_VIRTUALENVS_IN_PROJECT=1 \
#     POETRY_VIRTUALENVS_CREATE=1 \
#     POETRY_CACHE_DIR=C:/tmp/poetry_cache

# WORKDIR /app



# RUN wget http://prdownloads.sourceforge.net/ta-lib/ta-lib-0.4.0-src.tar.gz && \
#     tar -xvzf ta-lib-0.4.0-src.tar.gz && \
#     cd ta-lib && \
#     ./configure --prefix=/usr && \
#     make && \
#     make install && \
#     cd .. && \
#     rm -rf ta-lib ta-lib-0.4.0-src.tar.gz

# COPY OlympusTrader OlympusTrader
# COPY pyproject.toml poetry.lock README.md ./

# # Install with the project root and TA Lib extras
# # If you want to use MT5, add the -E metatrader extra
# RUN xvfb-run --auto-servernum --server-args="-screen 0 1024x768x24" wine cmd /c "poetry install -E talib -E metatrader"

# RUN wine poetry install -E talib -E metatrader

# -- Alternative to the above line

# FROM python:3.12-bookworm as builder

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

# COPY OlympusTrader OlympusTrader
# COPY pyproject.toml poetry.lock README.md ./

# # Install with the project root and TA Lib extras
# # If you want to use MT5, add the -E metatrader extra
# RUN --mount=type=cache,target=$POETRY_CACHE_DIR poetry install -E talib 

# ----------------------

FROM ghcr.io/linuxserver/baseimage-kasmvnc:debianbookworm as runtime

LABEL build_version="Metatrader Docker:- 1.0 Build-date:- 2/12/25"
LABEL maintainer="OlympusTrader"
ENV TITLE=Metatrader5
ENV WINEPREFIX="/config/.wine"




# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

RUN apt-get update && apt-get upgrade -y && apt-get install -y \
build-essential libssl-dev zlib1g-dev libbz2-dev \
libreadline-dev libsqlite3-dev wget curl llvm libncurses5-dev libncursesw5-dev \
xz-utils tk-dev libffi-dev liblzma-dev python3-openssl git 

RUN wget https://www.python.org/ftp/python/3.12.0/Python-3.12.0.tgz \
&& tar xvf Python-3.12.0.tgz \
&& cd Python-3.12.0 \
&& ./configure --enable-optimizations \
&& make -j 8 \
&& make install \
&& cd .. \
&& rm -rf Python-3.12.0 Python-3.12.0.tgz

# Add i386 architecture and update package lists
RUN dpkg --add-architecture i386 \
    && apt-get update

# Add WineHQ repository key and APT source
RUN sudo mkdir -pm755 /etc/apt/keyrings
RUN wget -O - https://dl.winehq.org/wine-builds/winehq.key | gpg --dearmor -o /etc/apt/keyrings/winehq-archive.key - 
RUN sudo wget -NP /etc/apt/sources.list.d/ https://dl.winehq.org/wine-builds/debian/dists/bookworm/winehq-bookworm.sources
# Old way
# RUN wget -q https://dl.winehq.org/wine-builds/winehq.key \
#     && apt-key add winehq.key \
#     && add-apt-repository 'deb https://dl.winehq.org/wine-builds/debian/ bullseye main' \
    


# Install WineHQ stable package and dependencies
RUN apt update && apt-get install --install-recommends -y \
    winehq-stable \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Install TA Lib dependencies

RUN wget http://prdownloads.sourceforge.net/ta-lib/ta-lib-0.4.0-src.tar.gz && \
    tar -xvzf ta-lib-0.4.0-src.tar.gz && \
    cd ta-lib && \
    ./configure --prefix=/usr && \
    make && \
    make install && \
    cd .. && \
    rm -rf ta-lib ta-lib-0.4.0-src.tar.gz

# COPY --from=builder /usr/lib/libta* /usr/lib/
# COPY --from=builder /usr/include/libta* /usr/include/


COPY Docker/Metatrader /Metatrader
COPY Docker/mt5Root /
RUN chmod +x /Metatrader/start.sh
# RUN ./Metatrader/start.sh

VOLUME /config
WORKDIR /app

COPY OlympusTrader OlympusTrader
# COPY pyproject.toml poetry.lock README.md ./
# we dont need to copy over the lock file since we are not using linux OS but a windows OS
COPY pyproject.toml README.md ./

# RUN python3.12 -m pip install poetry==1.8.3
# Install with the project root and TA Lib extras
# If you want to use MT5, add the -E metatrader extra
# RUN --mount=type=cache,target=$POETRY_CACHE_DIR poetry install -E talib -E metatrader

# Create a non-privileged user that the app will run under
# ARG UID=10001
# RUN adduser --disabled-password --gecos "" --home "/nonexistent" --shell "/sbin/nologin" --no-create-home --uid "${UID}" trader

# # Set permissions for the data and backtests directories
# RUN mkdir -p data backtests && chown -R trader:trader data backtests

# USER trader

# ENV VIRTUAL_ENV=/app/.venv \
#     PATH="/app/.venv/bin:$PATH" \
#     NUMBA_CACHE_DIR=/tmp/numba_cache \
#     TA_LIBRARY_PATH=/usr/lib \
#     TA_INCLUDE_PATH=/usr/include

# COPY --from=builder ${VIRTUAL_ENV} ${VIRTUAL_ENV}


# RUN wine python.exe -m pip install MetaTrader5

ARG STRATEGY
COPY strategies/$STRATEGY strategy
ENV STRATEGY=$STRATEGY

EXPOSE 8050 50000 3000
# CMD ["python3.12", "strategy"]
# CMD [ "wine" ,"poetry", "run", "python", "/app/strategy"]