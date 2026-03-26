#!/bin/bash
# Hook: build iOS app and install to phone after .swift file changes
# Reads PostToolUse JSON from stdin, checks if file is .swift under ios-app/
set -e

FILE=$(jq -r '.tool_input.file_path // .tool_response.filePath // ""')

# Only trigger for .swift files under ios-app/
echo "$FILE" | grep -q '\.swift$' || exit 0
echo "$FILE" | grep -q 'ios-app/' || exit 0

DEVICE_ID="00008130-00026CA611F8001C"
IOS_DIR="/Users/robert/Projects/CozyPup/ios-app"
DERIVED_DATA="/tmp/cozypup-build"
APP_PATH="$DERIVED_DATA/Build/Products/Debug-iphoneos/CozyPup.app"

cd "$IOS_DIR"

xcodebuild -project CozyPup.xcodeproj -scheme CozyPup \
  -destination "id=$DEVICE_ID" \
  -derivedDataPath "$DERIVED_DATA" \
  build -quiet 2>/dev/null

devicectl device install app --device "$DEVICE_ID" "$APP_PATH" 2>/dev/null

echo '{"systemMessage": "Built and installed to iPhone"}'
