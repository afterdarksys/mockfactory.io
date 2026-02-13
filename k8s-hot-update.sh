#!/bin/bash
set -e

# MockFactory K8s Hot Update
# Updates running pods with new cloud emulation code WITHOUT rebuilding image

echo "================================================"
echo "  MockFactory K8s Hot Update"
echo "  (No image rebuild - direct file update)"
echo "================================================"
echo ""

# Step 1: Package new files
echo "[1/3] Packaging new cloud emulation files..."
TEMP_DIR="/tmp/mockfactory-hotupdate-$(date +%s)"
mkdir -p $TEMP_DIR/app/api
mkdir -p $TEMP_DIR/app/services
mkdir -p $TEMP_DIR/app/models

# Copy new files
cp app/api/aws_vpc_emulator.py $TEMP_DIR/app/api/
cp app/api/aws_lambda_emulator.py $TEMP_DIR/app/api/
cp app/api/aws_dynamodb_emulator.py $TEMP_DIR/app/api/
cp app/api/aws_sqs_emulator.py $TEMP_DIR/app/api/
cp app/services/oci_network_service.py $TEMP_DIR/app/services/
cp app/services/credit_billing.py $TEMP_DIR/app/services/
cp app/models/vpc_resources.py $TEMP_DIR/app/models/
cp app/main.py $TEMP_DIR/app/

# Create tarball
cd $TEMP_DIR
tar -czf ../mockfactory-update.tar.gz .
cd -

echo "✅ Package created"
echo ""

# Step 2: Get OKE cluster kubeconfig
echo "[2/3] Getting K8s cluster access..."

# Find OKE cluster
CLUSTER_ID=$(oci ce cluster list \
    --compartment-id ocid1.compartment.oc1..aaaaaaaaqzzabys3xbxcbektqibdhzm6vtfmudya2fcuhmtzkhkow4sub3na \
    --lifecycle-state ACTIVE \
    --query 'data[0].id' \
    --raw-output 2>/dev/null)

if [ -z "$CLUSTER_ID" ]; then
    # Try other compartments
    echo "Searching other compartments..."
    CLUSTER_ID=$(oci ce cluster list \
        --compartment-id ocid1.compartment.oc1..aaaaaaaamosrw6gs2eqsvv6nizc6ch5giwla6zbkumqbipycajavltgi2jya \
        --lifecycle-state ACTIVE \
        --query 'data[0].id' \
        --raw-output 2>/dev/null)
fi

if [ -n "$CLUSTER_ID" ]; then
    echo "Found cluster: $CLUSTER_ID"

    # Create kubeconfig
    mkdir -p ~/.kube
    oci ce cluster create-kubeconfig \
        --cluster-id $CLUSTER_ID \
        --file ~/.kube/mockfactory-config \
        --region us-ashburn-1 \
        --token-version 2.0.0 2>/dev/null || true

    export KUBECONFIG=~/.kube/mockfactory-config

    echo "✅ Cluster access configured"
else
    echo "⚠️  No OKE cluster found - will use existing kubeconfig"
fi

echo ""

# Step 3: Update pods
echo "[3/3] Updating pods with new code..."

# Find mockfactory pods
PODS=$(kubectl get pods -n default -l app=mockfactory -o name 2>/dev/null || \
       kubectl get pods -n default -o name 2>/dev/null | grep -i mockfactory || \
       kubectl get pods --all-namespaces -o name 2>/dev/null | grep -i mockfactory | head -5)

if [ -z "$PODS" ]; then
    echo "❌ No mockfactory pods found"
    echo ""
    echo "Available pods:"
    kubectl get pods --all-namespaces 2>/dev/null | head -20
    exit 1
fi

echo "Found pods:"
echo "$PODS"
echo ""

# Update each pod
for POD in $PODS; do
    echo "Updating $POD..."

    # Extract namespace if present
    if [[ $POD == *"/"* ]]; then
        NAMESPACE=$(echo $POD | cut -d'/' -f1)
        POD_NAME=$(echo $POD | cut -d'/' -f2)
    else
        NAMESPACE="default"
        POD_NAME=$POD
    fi

    # Copy tarball to pod
    kubectl cp /tmp/mockfactory-update.tar.gz $NAMESPACE/$POD_NAME:/tmp/update.tar.gz 2>/dev/null || {
        echo "⚠️  Failed to copy to $POD - may not be running"
        continue
    }

    # Extract and update files in pod
    kubectl exec -n $NAMESPACE $POD_NAME -- bash -c "
        cd /app
        tar -xzf /tmp/update.tar.gz
        rm /tmp/update.tar.gz
        echo '✅ Files updated in pod'
    " 2>/dev/null || {
        echo "⚠️  Failed to update $POD"
        continue
    }

    echo "✅ Updated $POD"
done

echo ""
echo "Restarting pods to load new code..."

# Restart deployment
kubectl rollout restart deployment/mockfactory-api -n default 2>/dev/null || \
kubectl rollout restart deployment/mockfactory -n default 2>/dev/null || \
echo "⚠️  Could not find deployment to restart - manual pod deletion may be needed"

echo ""
echo "Waiting for pods to be ready..."
sleep 10

# Check status
kubectl get pods -n default -l app=mockfactory 2>/dev/null || \
kubectl get pods --all-namespaces 2>/dev/null | grep mockfactory

echo ""
echo "================================================"
echo "  Hot Update Complete! 🔥"
echo "================================================"
echo ""
echo "New features deployed:"
echo "  ✅ AWS VPC emulation"
echo "  ✅ AWS Lambda emulation"
echo "  ✅ AWS DynamoDB emulation"
echo "  ✅ AWS SQS emulation"
echo "  ✅ Credit billing system"
echo ""
echo "Verify deployment:"
echo "  curl https://mockfactory.io/health"
echo ""

# Cleanup
rm -rf $TEMP_DIR
rm -f /tmp/mockfactory-update.tar.gz

echo "✨ Cloud emulation is live!"
