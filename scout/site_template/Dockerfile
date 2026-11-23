# Hill Scout site: static pages, GET /api/import, POST /api/request on 0.0.0.0:8080, as Egbe hosting requires.
FROM python:3.12-alpine
WORKDIR /site
COPY wheels/ /wheels/
RUN pip install --no-cache-dir --no-index --find-links /wheels pg8000==1.31.2 && rm -rf /wheels
COPY . .
RUN rm -rf /site/wheels /site/Dockerfile
RUN mkdir -p /data
ENV REQUESTS_FILE=/data/requests.jsonl
EXPOSE 8080
CMD ["python", "server.py"]
