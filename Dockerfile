# books.cpuchip.net: build the site from this repo at the pinned pd-books export, refusing on any red check, then
# serve only the built files. The browser check is not run here (no Chromium in the image); it runs in the
# rehearsal at the same commit, and tools/verifylive.py then proves the served files equal the rehearsed build.
FROM python:3.13.1-slim-bookworm AS build
RUN apt-get update && apt-get install -y --no-install-recommends git ca-certificates && rm -rf /var/lib/apt/lists/*
WORKDIR /src
COPY . .
RUN sh build.sh /site

FROM nginx:1.30.7-alpine
COPY deploy/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /site /usr/share/nginx/html
