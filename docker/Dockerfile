FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1
WORKDIR /app

COPY pyproject.toml README.md ./
COPY src ./src

RUN pip install --no-cache-dir .

USER 65532:65532

ENTRYPOINT ["openstack-fip-dns-reconciler"]
CMD ["--config", "/etc/openstack-fip-dns-reconciler/config.yaml"]
