# deploy-kubernetes

This builds a docker container that knows how to deploy a simple
k8s deployment on a number nodes. This configuration is not production ready but
can serve as a simple test bed

At least two ip addresses must be provided. The first is used as the master
and any remaining are configured as nodes

```
[user@host]$ docker build -t deploy-kubernetes .

[user@host]$ docker run -it --rm deploy-kubernetes
usage: deploy-scaleio.py [-h] [--ip [IP [IP ...]]]
                         [--username USERNAME]
                         [--password PASSWORD]
```