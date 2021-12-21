#!/bin/bash

set -euo pipefail

export DOCKER_BUILDKIT=1

if [ "$1" = "develop" -o "$1" = "master" ]; then
    # If image does not exist, don't use cache
    docker pull metissafe/$DOCKERHUB_PROJECT:$1 && \
    docker build -t $DOCKERHUB_PROJECT -f docker/web/Dockerfile . --cache-from metissafe/$DOCKERHUB_PROJECT:$1 --build-arg BUILDKIT_INLINE_CACHE=1 || \
    docker build -t $DOCKERHUB_PROJECT -f docker/web/Dockerfile . --build-arg BUILDKIT_INLINE_CACHE=1
else
    # Building tag version from staging image (vX.X.X)
    docker pull metissafe/$DOCKERHUB_PROJECT:staging && \
    docker build -t $DOCKERHUB_PROJECT -f docker/web/Dockerfile . --cache-from metissafe/$DOCKERHUB_PROJECT:staging --build-arg BUILDKIT_INLINE_CACHE=1 || \
    docker build -t $DOCKERHUB_PROJECT -f docker/web/Dockerfile . --build-arg BUILDKIT_INLINE_CACHE=1
    docker tag $DOCKERHUB_PROJECT metissafe/$DOCKERHUB_PROJECT:latest
fi
docker tag $DOCKERHUB_PROJECT metissafe/$DOCKERHUB_PROJECT:$1
docker push metissafe/$DOCKERHUB_PROJECT:$1
