#!/bin/bash
# Auto-deploy: push → server rebuild → build iOS → install on phone
set -e

DEVICE_ID="76087B8C-A0B5-5E84-A664-5BC5CE7471FD"
BUNDLE_ID="com.robertwang.cozypup.dev"
PROJECT_DIR="/Users/robert/Projects/CozyPup"
IOS_DIR="$PROJECT_DIR/ios-app"
DERIVED_DATA="/Users/robert/Library/Developer/Xcode/DerivedData/CozyPup-aytzmofgduwiydchoubneqbkekdg"
APP_PATH="$DERIVED_DATA/Build/Products/Debug-iphoneos/CozyPup.app"
SSH_KEY="$HOME/Projects/OracleCloud/ssh-key-2026-03-12.key"
SERVER="ubuntu@168.138.75.153"

cd "$PROJECT_DIR"

# 1. Push to GitHub
git push origin main 2>/dev/null || true

# 2. Server deploy + iOS build in parallel
ssh -i "$SSH_KEY" -o StrictHostKeyChecking=accept-new -o ConnectTimeout=10 "$SERVER" \
  "cd ~/cozypup && git fetch origin main --quiet && git reset --hard origin/main --quiet && cd backend && docker compose up -d --build --quiet-pull" 2>/dev/null &
SERVER_PID=$!

cd "$IOS_DIR"
xcodebuild -project CozyPup.xcodeproj -scheme CozyPup \
  -destination "platform=iOS,id=$DEVICE_ID" \
  build -quiet 2>/dev/null

wait $SERVER_PID 2>/dev/null || true

# 4. Install on phone
xcrun devicectl device install app --device "$DEVICE_ID" "$APP_PATH" 2>/dev/null

# 5. Launch
xcrun devicectl device process launch --device "$DEVICE_ID" "$BUNDLE_ID" 2>/dev/null

echo '{"systemMessage": "Deployed to server + iPhone"}'
