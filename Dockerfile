FROM python:2
MAINTAINER Jon Bullen

RUN apt-get update && apt-get install -y \
        libssl-dev \
        libusb-1.0-0 \
        python-dev \
        swig \
        && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

RUN pip --no-cache-dir install --upgrade pip
RUN pip --no-cache-dir install flask
RUN pip --no-cache-dir install https://pypi.python.org/packages/source/M/M2Crypto/M2Crypto-0.24.0.tar.gz
RUN pip --no-cache-dir install firetv[firetv-server]

# Default listening port.
EXPOSE 5556

# The configuration yaml for persistance.
VOLUME /config

#CMD [ "firetv-server" ]
ENTRYPOINT ["firetv-server"]

CMD ["--help"]

#firetv-server -v --config ./config/house.yaml


# docker build -t docker-firetv .
# docker run -it --rm --name python-firetv -p 5556:5556 sytone/python-firetv
# docker run -d --restart=always -v E:/myconfigpath:/config --name python-firetv -p 5556:5556 sytone/python-firetv

# docker run -it --rm -v E:/myconfigpath:/config --name python-firetv -p 5556:5556 sytone/python-firetv -v --config /config/house.yaml
# docker run -d --restart=always -v E:/myconfigpath:/config --name python-firetv -p 5556:5556 sytone/python-firetv -v --config /config/house.yaml
