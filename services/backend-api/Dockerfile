# Use a slim Python base image
FROM python:3.9-slim

WORKDIR /app

# Ensure Python can import agent modules
ENV PYTHONPATH=/app:/app/agent

# ==========================================
# Install Infrastructure & Cloud Tools
# ==========================================
# This image needs to be a powerful infra-copilot with comprehensive tooling
RUN apt-get update && apt-get install -y --no-install-recommends \
    # Build essentials for some tools
    build-essential \
    ca-certificates \
    gnupg \
    lsb-release \
    apt-transport-https \
    unzip \
    # HTTP clients
    curl \
    wget \
    # Process and system tools
    procps \
    lsof \
    htop \
    strace \
    # Network utilities
    netcat-openbsd \
    dnsutils \
    iproute2 \
    iputils-ping \
    traceroute \
    tcpdump \
    nmap \
    # Text processing and editors
    jq \
    vim-tiny \
    nano \
    less \
    # Version control
    git \
    # Database clients
    postgresql-client \
    default-mysql-client \
    redis-tools \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# ==========================================
# Install Kubernetes CLI (kubectl)
# ==========================================
RUN curl -LO "https://dl.k8s.io/release/$(curl -L -s https://dl.k8s.io/release/stable.txt)/bin/linux/amd64/kubectl" \
    && chmod +x kubectl \
    && mv kubectl /usr/local/bin/kubectl

# ==========================================
# Install Helm (Kubernetes package manager)
# ==========================================
RUN curl https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-3 | bash

# ==========================================
# Install AWS CLI v2
# ==========================================
RUN curl "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o "awscliv2.zip" \
    && unzip awscliv2.zip \
    && ./aws/install \
    && rm -rf aws awscliv2.zip

# ==========================================
# Install eksctl (EKS cluster management)
# ==========================================
RUN curl --silent --location "https://github.com/weaveworks/eksctl/releases/latest/download/eksctl_$(uname -s)_amd64.tar.gz" | tar xz -C /tmp \
    && mv /tmp/eksctl /usr/local/bin

# ==========================================
# Install k9s (Kubernetes CLI to manage clusters)
# ==========================================
RUN curl -Lo k9s.tar.gz "https://github.com/derailed/k9s/releases/latest/download/k9s_Linux_amd64.tar.gz" \
    && tar -xzf k9s.tar.gz -C /usr/local/bin k9s \
    && rm k9s.tar.gz \
    && chmod +x /usr/local/bin/k9s

# ==========================================
# Install kubectx and kubens (context/namespace switching)
# ==========================================
RUN curl -Lo kubectx https://raw.githubusercontent.com/ahmetb/kubectx/master/kubectx \
    && curl -Lo kubens https://raw.githubusercontent.com/ahmetb/kubectx/master/kubens \
    && chmod +x kubectx kubens \
    && mv kubectx kubens /usr/local/bin/

# ==========================================
# Install yq (YAML processor)
# ==========================================
RUN wget -qO /usr/local/bin/yq https://github.com/mikefarah/yq/releases/latest/download/yq_linux_amd64 \
    && chmod +x /usr/local/bin/yq

# ==========================================
# Install stern (multi-pod log tailing)
# ==========================================
RUN STERN_VERSION=$(curl -s https://api.github.com/repos/stern/stern/releases/latest | grep '"tag_name"' | sed -E 's/.*"v([^"]+)".*/\1/') \
    && curl -Lo stern.tar.gz "https://github.com/stern/stern/releases/download/v${STERN_VERSION}/stern_${STERN_VERSION}_linux_amd64.tar.gz" \
    && tar -xzf stern.tar.gz stern \
    && mv stern /usr/local/bin/ \
    && chmod +x /usr/local/bin/stern \
    && rm stern.tar.gz

# ==========================================
# Install additional Python packages for agent
# ==========================================
# Copy Python requirements first
COPY ./services/backend-api/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install additional useful Python packages
RUN pip install --no-cache-dir \
    kubernetes \
    boto3 \
    botocore \
    requests \
    urllib3 \
    PyYAML \
    tabulate \
    rich \
    click

# ==========================================
# Verify all critical tools are installed
# ==========================================
RUN echo "Verifying tool installations..." && \
    kubectl version --client && \
    helm version && \
    aws --version && \
    eksctl version && \
    k9s version && \
    which kubectx && \
    which kubens && \
    jq --version && \
    yq --version && \
    stern --version && \
    curl --version && \
    psql --version && \
    mysql --version && \
    redis-cli --version && \
    git --version && \
    ps --version && \
    echo "✓ All tools installed successfully!"

# ==========================================
# Copy application code
# ==========================================
# Copy the agent code (needed by backend)
COPY ./services/agent/ ./agent/

# Copy the backend source code
COPY ./services/backend-api/app/ ./app/

# Copy database package used by backend
COPY ./services/backend-api/database/ ./database/

# ==========================================
# Runtime configuration
# ==========================================
# Create directories for agent artifacts
RUN mkdir -p /app/agent/.ufflow_temp /app/reports /app/artifacts

# Expose the port the API will run on
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Start the Uvicorn server
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]