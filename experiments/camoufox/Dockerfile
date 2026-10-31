# Research image only. Linux amd64, glibc; the production Alpine worker is unchanged.
FROM python:3.13.11-slim-bookworm@sha256:ac76900038d8606cc99b413d4ede77bc7152f1e42b94cf5d50d4b80a999652fe

WORKDIR /spike
ENV PYTHONPATH=/spike PYTHONUNBUFFERED=1

# Freeze Debian packages as well as Python and browser artifacts.
RUN rm /etc/apt/sources.list.d/debian.sources \
    && printf '%s\n' \
      'deb [check-valid-until=no] https://snapshot.debian.org/archive/debian/20261022T000000Z bookworm main' \
      'deb [check-valid-until=no] https://snapshot.debian.org/archive/debian-security/20261022T000000Z bookworm-security main' \
      > /etc/apt/sources.list
COPY experiments/camoufox/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir --require-hashes -r /tmp/requirements.txt \
    && python -m playwright install-deps firefox \
    && rm -rf /var/lib/apt/lists/*

# Download once into work/p13 and verify before extracting into the image.
COPY work/p13/browser.zip /tmp/browser.zip
COPY experiments/camoufox/browser.sha256 /tmp/browser.sha256
RUN cd /tmp && sha256sum --check browser.sha256 \
    && python -m zipfile -e browser.zip /opt/camoufox \
    && chmod +x /opt/camoufox/camoufox /opt/camoufox/camoufox-bin \
    && rm browser.zip browser.sha256 \
    && python -c 'from camoufox.fpgen_model import ensure_fpgen_model; ensure_fpgen_model()'

COPY app /spike/app
COPY experiments/camoufox /spike/experiments/camoufox
RUN useradd --create-home spike && mkdir /results && chown spike:spike /results
USER spike
ENTRYPOINT ["python", "experiments/camoufox/spike.py"]
CMD ["--engine", "camoufox", "--binary", "/opt/camoufox/camoufox", "--mode", "fixture", "--runs", "1", "--output", "/results/fixture"]
