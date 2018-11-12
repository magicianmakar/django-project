FROM python:2.7.15
ENV PYTHONUNBUFFERED 1
ENV LANG C.UTF-8
ENV LC_ALL C.UTF-8
RUN apt-get update && apt-get install -y \
    gettext \
    postgresql-client
RUN pip install virtualenv==16.0.0
RUN pip install autoenv==1.0.0
RUN pip install pip==18.1
WORKDIR /opt/dropified
RUN virtualenv venv && /bin/bash -c "source /opt/dropified/venv/bin/activate"
COPY requirements.txt requirements.txt
RUN /opt/dropified/venv/bin/pip install -r requirements.txt
RUN echo "source /opt/dropified/.env" > /root/.bashrc
EXPOSE 8000
