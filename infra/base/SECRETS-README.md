# Secrets Management

## Overview

This directory contains Kubernetes secret configurations. **Real secrets should NEVER be committed to Git.**

## Files

- `secrets.yaml` - Template file with placeholders (committed to Git)
- `secrets.local.yaml` - Your actual secrets with real values (git-ignored, NOT committed)

## Setup for Local Development

1. Copy the template and add your real secrets:
   ```bash
   cd infra/base
   cp secrets.yaml secrets.local.yaml
   ```

2. Encode your secrets to base64:
   ```bash
   echo -n "your-github-token" | base64
   echo -n "your-openai-key" | base64
   echo -n "your-anthropic-key" | base64
   ```

3. Edit `secrets.local.yaml` and replace the placeholders with your base64-encoded values

4. Apply to your Kubernetes cluster:
   ```bash
   kubectl apply -f secrets.local.yaml
   ```

## Setup for Cloud/Production

For production deployments, use external secret management:

- **AWS**: Use [External Secrets Operator](https://external-secrets.io/) with AWS Secrets Manager
- **GCP**: Use Google Secret Manager
- **Azure**: Use Azure Key Vault
- **Generic**: Use sealed-secrets or SOPS

## Current Secrets

The `oats-api-keys` secret contains:
- `openai-api-key` - OpenAI API key
- `anthropic-api-key` - Anthropic/Claude API key
- `github-token` - GitHub Personal Access Token for code search

## Security Notes

- ✅ `secrets.local.yaml` is in `.gitignore`
- ✅ Never commit real secrets to Git
- ✅ Rotate secrets regularly
- ✅ Use minimal permissions for tokens
- ✅ Base64 is NOT encryption - it's just encoding for YAML format
