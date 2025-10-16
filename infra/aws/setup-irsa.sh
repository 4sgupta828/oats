#!/bin/bash
# Setup IRSA (IAM Roles for Service Accounts) for OATS Infra-Copilot
# This script creates an IAM role with account-wide read permissions and associates it with the K8s service account

set -e

# ==========================================
# Configuration
# ==========================================
AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
AWS_REGION=${AWS_REGION:-us-west-2}
CLUSTER_NAME=${CLUSTER_NAME:-oats-cluster}
NAMESPACE="default"
SERVICE_ACCOUNT_NAME="oats-backend"
IAM_ROLE_NAME="oats-infra-copilot-role"
IAM_POLICY_NAME="OATSInfraCopilotPolicy"

echo "=========================================="
echo "OATS Infra-Copilot IRSA Setup"
echo "=========================================="
echo "AWS Account ID: $AWS_ACCOUNT_ID"
echo "AWS Region: $AWS_REGION"
echo "EKS Cluster: $CLUSTER_NAME"
echo "Namespace: $NAMESPACE"
echo "Service Account: $SERVICE_ACCOUNT_NAME"
echo "IAM Role: $IAM_ROLE_NAME"
echo "IAM Policy: $IAM_POLICY_NAME"
echo "=========================================="

# ==========================================
# Step 1: Get OIDC provider for the cluster
# ==========================================
echo ""
echo "[Step 1/5] Getting OIDC provider for EKS cluster..."
OIDC_ID=$(aws eks describe-cluster --name $CLUSTER_NAME --region $AWS_REGION --query "cluster.identity.oidc.issuer" --output text | cut -d '/' -f 5)
echo "OIDC Provider ID: $OIDC_ID"

# Check if OIDC provider exists
OIDC_PROVIDER_ARN="arn:aws:iam::${AWS_ACCOUNT_ID}:oidc-provider/oidc.eks.${AWS_REGION}.amazonaws.com/id/${OIDC_ID}"
if aws iam get-open-id-connect-provider --open-id-connect-provider-arn $OIDC_PROVIDER_ARN &>/dev/null; then
    echo "✓ OIDC provider exists"
else
    echo "❌ OIDC provider does not exist. Creating it..."
    eksctl utils associate-iam-oidc-provider --cluster=$CLUSTER_NAME --region=$AWS_REGION --approve
    echo "✓ OIDC provider created"
fi

# ==========================================
# Step 2: Create IAM policy
# ==========================================
echo ""
echo "[Step 2/5] Creating IAM policy..."
POLICY_ARN="arn:aws:iam::${AWS_ACCOUNT_ID}:policy/${IAM_POLICY_NAME}"

# Check if policy exists
if aws iam get-policy --policy-arn $POLICY_ARN &>/dev/null; then
    echo "⚠ Policy already exists. Getting existing policy ARN..."
else
    echo "Creating new policy from iam-infra-copilot-policy.json..."
    POLICY_ARN=$(aws iam create-policy \
        --policy-name $IAM_POLICY_NAME \
        --policy-document file://$(dirname $0)/iam-infra-copilot-policy.json \
        --description "Account-wide read access for OATS Infra-Copilot agent" \
        --query 'Policy.Arn' \
        --output text)
    echo "✓ Policy created: $POLICY_ARN"
fi

# ==========================================
# Step 3: Create IAM trust policy
# ==========================================
echo ""
echo "[Step 3/5] Creating IAM trust policy..."
cat > /tmp/trust-policy.json <<EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Federated": "arn:aws:iam::${AWS_ACCOUNT_ID}:oidc-provider/oidc.eks.${AWS_REGION}.amazonaws.com/id/${OIDC_ID}"
      },
      "Action": "sts:AssumeRoleWithWebIdentity",
      "Condition": {
        "StringEquals": {
          "oidc.eks.${AWS_REGION}.amazonaws.com/id/${OIDC_ID}:sub": "system:serviceaccount:${NAMESPACE}:${SERVICE_ACCOUNT_NAME}",
          "oidc.eks.${AWS_REGION}.amazonaws.com/id/${OIDC_ID}:aud": "sts.amazonaws.com"
        }
      }
    }
  ]
}
EOF

# ==========================================
# Step 4: Create IAM role
# ==========================================
echo ""
echo "[Step 4/5] Creating IAM role..."
IAM_ROLE_ARN="arn:aws:iam::${AWS_ACCOUNT_ID}:role/${IAM_ROLE_NAME}"

# Check if role exists
if aws iam get-role --role-name $IAM_ROLE_NAME &>/dev/null; then
    echo "⚠ Role already exists. Updating trust policy..."
    aws iam update-assume-role-policy \
        --role-name $IAM_ROLE_NAME \
        --policy-document file:///tmp/trust-policy.json
    echo "✓ Trust policy updated"
else
    echo "Creating new IAM role..."
    IAM_ROLE_ARN=$(aws iam create-role \
        --role-name $IAM_ROLE_NAME \
        --assume-role-policy-document file:///tmp/trust-policy.json \
        --description "IAM role for OATS Infra-Copilot with account-wide read access" \
        --query 'Role.Arn' \
        --output text)
    echo "✓ Role created: $IAM_ROLE_ARN"
fi

# Attach policy to role
echo "Attaching policy to role..."
aws iam attach-role-policy \
    --role-name $IAM_ROLE_NAME \
    --policy-arn $POLICY_ARN
echo "✓ Policy attached to role"

# ==========================================
# Step 5: Annotate Kubernetes service account
# ==========================================
echo ""
echo "[Step 5/5] Annotating Kubernetes service account..."
kubectl annotate serviceaccount $SERVICE_ACCOUNT_NAME \
    -n $NAMESPACE \
    eks.amazonaws.com/role-arn=$IAM_ROLE_ARN \
    --overwrite
echo "✓ Service account annotated"

# ==========================================
# Verification
# ==========================================
echo ""
echo "=========================================="
echo "✓ IRSA Setup Complete!"
echo "=========================================="
echo ""
echo "Configuration Summary:"
echo "  IAM Role ARN: $IAM_ROLE_ARN"
echo "  IAM Policy ARN: $POLICY_ARN"
echo "  Service Account: $NAMESPACE/$SERVICE_ACCOUNT_NAME"
echo ""
echo "Next Steps:"
echo "  1. Verify the annotation on the service account:"
echo "     kubectl describe serviceaccount $SERVICE_ACCOUNT_NAME -n $NAMESPACE"
echo ""
echo "  2. Update the rbac.yaml to include the role-arn annotation (already added)"
echo ""
echo "  3. Redeploy the backend pods to pick up the new IAM role:"
echo "     kubectl rollout restart deployment/oats-backend-api -n $NAMESPACE"
echo ""
echo "  4. Verify AWS credentials in the pod:"
echo "     kubectl exec -it <pod-name> -- aws sts get-caller-identity"
echo ""
echo "  5. Test account-wide access:"
echo "     kubectl exec -it <pod-name> -- aws ec2 describe-instances --region $AWS_REGION"
echo "     kubectl exec -it <pod-name> -- aws rds describe-db-instances --region $AWS_REGION"
echo ""
echo "=========================================="

# Clean up temp file
rm -f /tmp/trust-policy.json
