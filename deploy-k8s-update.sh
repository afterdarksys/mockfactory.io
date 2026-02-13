#!/bin/bash
set -e

# MockFactory Cloud Emulation K8s Deployment
# Deploys new cloud emulation features to OKE cluster

echo "================================================"
echo "  MockFactory Cloud Emulation K8s Deployment"
echo "================================================"
echo ""

# Configuration
NAMESPACE="idd2oizp8xvc"
REGION="us-ashburn-1"
REGISTRY="${REGION}.ocir.io"
IMAGE_NAME="mockfactory"
IMAGE_TAG="cloud-emulation-$(date +%Y%m%d-%H%M%S)"
FULL_IMAGE="${REGISTRY}/${NAMESPACE}/${IMAGE_NAME}:${IMAGE_TAG}"

echo "Configuration:"
echo "  Registry: ${REGISTRY}"
echo "  Image: ${FULL_IMAGE}"
echo ""

# Step 1: Create tarball of new files
echo "[1/5] Creating deployment package..."
PACKAGE_DIR="/tmp/mockfactory-cloud-deploy-$(date +%s)"
mkdir -p $PACKAGE_DIR

# Copy new cloud emulation files
mkdir -p $PACKAGE_DIR/app/api
mkdir -p $PACKAGE_DIR/app/services

cp app/api/aws_vpc_emulator.py $PACKAGE_DIR/app/api/
cp app/api/aws_lambda_emulator.py $PACKAGE_DIR/app/api/
cp app/api/aws_dynamodb_emulator.py $PACKAGE_DIR/app/api/
cp app/api/aws_sqs_emulator.py $PACKAGE_DIR/app/api/
cp app/services/oci_network_service.py $PACKAGE_DIR/app/services/
cp app/services/credit_billing.py $PACKAGE_DIR/app/services/
cp app/main.py $PACKAGE_DIR/app/
cp app/models/vpc_resources.py $PACKAGE_DIR/app/models/

# Copy full app for Docker build
cp -r app $PACKAGE_DIR/app_full
cp -r alembic $PACKAGE_DIR/
cp alembic.ini $PACKAGE_DIR/
cp requirements.txt $PACKAGE_DIR/
cp Dockerfile $PACKAGE_DIR/

# Create deployment script for K8s node
cat > $PACKAGE_DIR/deploy-on-node.sh << 'EOF'
#!/bin/bash
set -e

echo "Building Docker image on K8s node..."

# Build image
docker build -t FULL_IMAGE_PLACEHOLDER .

echo "Pushing to OCIR..."
# Login to OCIR (assumes auth token is configured)
docker push FULL_IMAGE_PLACEHOLDER

echo "Updating K8s deployment..."
# Update the deployment
kubectl set image deployment/mockfactory-api mockfactory-api=FULL_IMAGE_PLACEHOLDER -n default

# Wait for rollout
kubectl rollout status deployment/mockfactory-api -n default

echo "Deployment complete!"
kubectl get pods -n default -l app=mockfactory

EOF

# Replace placeholder with actual image name
sed -i.bak "s|FULL_IMAGE_PLACEHOLDER|${FULL_IMAGE}|g" $PACKAGE_DIR/deploy-on-node.sh
rm $PACKAGE_DIR/deploy-on-node.sh.bak
chmod +x $PACKAGE_DIR/deploy-on-node.sh

# Create tarball
cd $PACKAGE_DIR/..
tar -czf mockfactory-cloud-deploy.tar.gz $(basename $PACKAGE_DIR)

echo "✅ Package created: mockfactory-cloud-deploy.tar.gz"
echo ""

# Step 2: Upload to OCI Object Storage (temporary storage)
echo "[2/5] Uploading to OCI Object Storage..."

BUCKET_NAME="mockfactory-deploy-tmp"
oci os bucket create --compartment-id ocid1.compartment.oc1..aaaaaaaaqzzabys3xbxcbektqibdhzm6vtfmudya2fcuhmtzkhkow4sub3na --name $BUCKET_NAME 2>/dev/null || echo "Bucket already exists"

oci os object put --bucket-name $BUCKET_NAME --file mockfactory-cloud-deploy.tar.gz --name mockfactory-cloud-deploy.tar.gz --force

# Create pre-authenticated request for download
PAR_URL=$(oci os preauth-request create \
    --bucket-name $BUCKET_NAME \
    --name "deploy-$(date +%s)" \
    --access-type ObjectRead \
    --time-expires "$(date -u -v+1H '+%Y-%m-%dT%H:%M:%SZ' 2>/dev/null || date -u -d '+1 hour' '+%Y-%m-%dT%H:%M:%SZ')" \
    --object-name mockfactory-cloud-deploy.tar.gz \
    --query 'data."access-uri"' \
    --raw-output)

DOWNLOAD_URL="https://objectstorage.${REGION}.oraclecloud.com${PAR_URL}"

echo "✅ Package uploaded"
echo "   Download URL: ${DOWNLOAD_URL}"
echo ""

# Step 3: Find a K8s node to run the build
echo "[3/5] Finding K8s worker node..."

# Get first running instance in undateable compartment
NODE_IP=$(oci compute instance list \
    --compartment-id ocid1.compartment.oc1..aaaaaaaaqzzabys3xbxcbektqibdhzm6vtfmudya2fcuhmtzkhkow4sub3na \
    --lifecycle-state RUNNING \
    --query 'data[?starts_with("display-name", `oke-`)].{"ip":"public-ip"}' \
    --raw-output 2>/dev/null | head -1)

if [ -z "$NODE_IP" ]; then
    echo "❌ No K8s worker nodes found"
    exit 1
fi

echo "✅ Found worker node: ${NODE_IP}"
echo ""

# Step 4: Deploy on K8s node
echo "[4/5] Deploying on K8s node..."

# SSH to node and execute deployment
ssh -o StrictHostKeyChecking=no opc@${NODE_IP} << ENDSSH
set -e

# Download package
echo "Downloading deployment package..."
curl -sL "${DOWNLOAD_URL}" -o mockfactory-cloud-deploy.tar.gz

# Extract
tar -xzf mockfactory-cloud-deploy.tar.gz
cd mockfactory-cloud-deploy-*

# Copy app files to Dockerfile location
rm -rf app
mv app_full app

# Run deployment script
chmod +x deploy-on-node.sh
sudo ./deploy-on-node.sh

# Cleanup
cd ..
rm -rf mockfactory-cloud-deploy-* mockfactory-cloud-deploy.tar.gz

echo "✅ Deployment complete on node"
ENDSSH

echo "✅ Deployment executed on K8s node"
echo ""

# Step 5: Verify deployment
echo "[5/5] Verifying deployment..."

sleep 5

# Test health endpoint
if curl -s https://mockfactory.io/health | grep -q "healthy"; then
    echo "✅ Service is healthy!"
else
    echo "⚠️  Service may still be starting..."
fi

echo ""
echo "================================================"
echo "  Deployment Complete! 🎉"
echo "================================================"
echo ""
echo "New features deployed:"
echo "  ✅ AWS VPC emulation (real OCI VCNs)"
echo "  ✅ AWS Lambda emulation (Docker containers)"
echo "  ✅ AWS DynamoDB emulation (PostgreSQL JSONB)"
echo "  ✅ AWS SQS emulation (Redis queues)"
echo "  ✅ Credit billing system (AWS-style per-second)"
echo ""
echo "Test endpoints:"
echo "  POST https://env-{ID}.mockfactory.io/aws/vpc?Action=CreateVpc"
echo "  POST https://env-{ID}.mockfactory.io/aws/lambda"
echo "  POST https://env-{ID}.mockfactory.io/aws/dynamodb"
echo "  POST https://env-{ID}.mockfactory.io/aws/sqs"
echo ""
echo "Monitor pods:"
echo "  kubectl get pods -n default -l app=mockfactory -w"
echo ""

# Cleanup
rm -rf $PACKAGE_DIR
rm -f mockfactory-cloud-deploy.tar.gz

echo "✨ Enjoy your cloud emulation platform!"
