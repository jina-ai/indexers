FROM jinaai/jina:2.0 as base
# tests fail with jina:master for some reason

# install the third-party requirements
RUN apt-get update && apt-get install --no-install-recommends -y gcc build-essential git

# setup the workspace
COPY . /workspace
WORKDIR /workspace

RUN pip install -r requirements.txt

FROM base as entrypoint
ENTRYPOINT ["jina", "executor", "--uses", "config.yml"]
