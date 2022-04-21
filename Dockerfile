FROM python:3.7
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1
ENV LANG C.UTF-8
ENV LC_ALL C.UTF-8
RUN apt-get update && apt-get install -y \
    curl && \
    curl -sL https://deb.nodesource.com/setup_12.x | bash - && \
    apt-get install -y \
    gettext \
    nodejs \
    postgresql-client
# We should give exact version to make caching work in a predictable manner.
RUN pip install pip==21.0
WORKDIR /opt/dropified
COPY requirements.txt requirements.txt
COPY docker/dev_requirements.txt docker/dev_requirements.txt
RUN pip install -r docker/dev_requirements.txt
COPY package.json package.json
RUN echo "source /opt/dropified/.env" > /root/.bashrc
EXPOSE 8000
