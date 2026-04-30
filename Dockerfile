# Base stage - Python 3.14
FROM python:3.14-slim AS base

# Install Node.js 24.x
RUN apt-get update && apt-get install -y curl && \
    curl -fsSL https://deb.nodesource.com/setup_24.x | bash - && \
    apt-get install -y nodejs && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY int/ ./int/
COPY tester/ ./tester/
COPY sol2xml/ ./sol2xml/

# Check stage - code quality tools
FROM base AS check
WORKDIR /app

# Install Python dependencies FIRST (for mypy plugins)
RUN pip install --no-cache-dir -r int/requirements.txt --break-system-packages

# Install Python tools
RUN pip install --no-cache-dir ruff mypy --break-system-packages

# Create wrapper scripts for Python tools in int/
RUN echo '#!/bin/bash\nexec ruff "$@"' > /app/int/ruff && chmod +x /app/int/ruff
RUN echo '#!/bin/bash\nexec mypy "$@"' > /app/int/mypy && chmod +x /app/int/mypy

# Install ALL Node dependencies (not just eslint/prettier)
WORKDIR /app/tester
RUN npm install

# Create wrapper scripts for Node tools in tester/
RUN echo '#!/bin/bash\nexec npx eslint "$@"' > /app/tester/eslint && chmod +x /app/tester/eslint
RUN echo '#!/bin/bash\nexec npx prettier "$@"' > /app/tester/prettier && chmod +x /app/tester/prettier

WORKDIR /app
ENTRYPOINT ["/bin/bash"]

# Build-test stage - compile TypeScript tester
FROM base AS build-test
WORKDIR /app/tester
RUN npm install && npm run build

# Runtime stage - interpreter only
FROM python:3.14-slim AS runtime
WORKDIR /app

# Install ALL build dependencies for lxml
RUN apt-get update && \
    apt-get install -y \
        libxml2-dev \
        libxslt-dev \
        gcc \
        zlib1g-dev \
        && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

COPY int/ ./int/
COPY sol2xml/ ./sol2xml/
RUN pip install --no-cache-dir -r int/requirements.txt && \
    pip install --no-cache-dir -r sol2xml/requirements.txt

ENV PYTHONPATH=/app/int/src:$PYTHONPATH
RUN chmod +x int/solint.py sol2xml/sol_to_xml.py
ENTRYPOINT ["python3", "/app/int/solint.py"]

# Test stage - tester + interpreter
FROM runtime AS test
COPY --from=build-test /app/tester/dist /app/tester/dist
COPY --from=build-test /app/tester/node_modules /app/tester/node_modules
COPY --from=build-test /app/tester/package.json /app/tester/package.json
RUN apt-get update && apt-get install -y nodejs && \
    apt-get clean && rm -rf /var/lib/apt/lists/*
ENV SOLINT_PATH=/app/int/solint.py
ENV SOL2XML_PATH=/app/sol2xml/sol_to_xml.py
WORKDIR /app/tester
ENTRYPOINT ["node", "/app/tester/dist/tester.js"]
