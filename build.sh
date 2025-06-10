#!/bin/bash

# 이미지 이름과 태그 설정
IMAGE_NAME="cookieshake/naraninyeo"
IMAGE_TAG="latest"
REGISTRY="docker.io"  # GitHub Container Registry 사용
FULL_IMAGE_NAME="${REGISTRY}/${IMAGE_NAME}:${IMAGE_TAG}"


# Docker 이미지 빌드 및 푸시
echo "🏗️ Building and pushing Docker image..."
docker buildx build \
    --platform linux/amd64,linux/arm64 \
    --push \
    -t ${FULL_IMAGE_NAME} \
    .


echo "✅ Done!"
echo "📦 Image pushed to ${FULL_IMAGE_NAME}"
