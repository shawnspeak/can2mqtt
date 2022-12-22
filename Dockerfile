FROM alpine

ENV PYTHONUNBUFFERED=1
RUN apk add --update --no-cache python3 && ln -sf python3 /usr/bin/python
RUN python3 -m ensurepip
RUN pip3 install --no-cache --upgrade pip setuptools
RUN pip3 install python-can
RUN pip3 install paho-mqtt

COPY can2mqtt.py .
ENTRYPOINT ["python3", "can2mqtt.py"]