FROM python:3.6.8
ENV PYTHONUNBUFFERED 1
ENV LANG C.UTF-8
ENV LC_ALL C.UTF-8
RUN apt-get update && apt-get install -y \
    curl && \
    curl -sL https://deb.nodesource.com/setup_8.x | bash - && \
    apt-get install -y \
    gettext \
    nodejs \
    postgresql-client
RUN pip install -U pip
WORKDIR /opt/dropified
COPY requirements.txt requirements.txt
RUN pip install -r requirements.txt
COPY package.json package.json
RUN echo "source /opt/dropified/.env" > /root/.bashrc
EXPOSE 8000
