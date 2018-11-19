FROM python:2.7.15
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
RUN pip install virtualenv==16.0.0
RUN pip install autoenv==1.0.0
RUN pip install pip==18.1
WORKDIR /opt/dropified
RUN virtualenv venv && /bin/bash -c "source /opt/dropified/venv/bin/activate"
COPY requirements.txt requirements.txt
RUN /opt/dropified/venv/bin/pip install -r requirements.txt
COPY package.json package.json
RUN npm install
COPY bower.json bower.json
RUN ./node_modules/bower/bin/bower install --allow-root
RUN echo "source /opt/dropified/.env" > /root/.bashrc
EXPOSE 8000
