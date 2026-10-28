#!/usr/bin/env bash
# V194: test APK on a standard Android emulator, read-only UI inspection.
set -uo pipefail
mkdir -p v194_risultati
REPORT=v194_risultati/app_test.txt
{
echo "V194 app smoke test"
echo "Date UTC: $(date -u +%FT%TZ)"
echo "Emulator: $(adb shell getprop ro.build.version.release | tr -d '\r')"
echo "ABI: $(adb shell getprop ro.product.cpu.abilist | tr -d '\r')"
} > "$REPORT"
set +e
adb install -r MyLotteries-v194.apk >>"$REPORT" 2>&1
INSTALL_STATUS=$?
echo "adb_install_exit: $INSTALL_STATUS" >> "$REPORT"
if [[ "$INSTALL_STATUS" -ne 0 ]]; then
  echo "Installation failed, no further action." >>"$REPORT"
  exit 0
fi
AAPT=$(find "$ANDROID_HOME/build-tools" -maxdepth 2 -name aapt -type f 2>/dev/null | sort -V | tail -1)
if [[ -z "$AAPT" ]]; then
  echo "AAPT missing; package cannot be identified" >> "$REPORT"
  exit 0
fi
PKG=$("$AAPT" dump badging MyLotteries-v194.apk 2>/dev/null | sed -n "s/^package: name='\([^']*\)'.*/\1/p" | head -1)
if [[ -z "$PKG" ]]; then
  echo "Package name unavailable" >> "$REPORT"
  exit 0
fi
echo "package: $PKG" >> "$REPORT"
adb shell monkey -p "$PKG" -c android.intent.category.LAUNCHER 1 >>"$REPORT" 2>&1
echo "launch_exit: $?" >>"$REPORT"
# The first screenshot of V194 confirmed the optional privacy notice.
# Press its explicitly offered decline option; do not accept analytics or profiling.
sleep 5
adb shell input tap 230 251
echo "Clicked Continue without accepting optional cookies (screenshot-verified coordinates)." >>"$REPORT"
sleep 8
for i in 0 1 2; do
  if [[ "$i" != 0 ]]; then sleep 25; else sleep 15; fi
  adb exec-out screencap -p >"v194_risultati/screen_$i.png" 2>/dev/null
  echo "screen_$i $(wc -c <"v194_risultati/screen_$i.png") bytes" >>"$REPORT"
  adb shell uiautomator dump /sdcard/window_v194.xml >/dev/null 2>&1
  adb pull /sdcard/window_v194.xml "v194_risultati/ui_$i.xml" >/dev/null 2>&1
done
adb shell dumpsys activity activities | grep -E "(topResumedActivity|mResumedActivity|ResumedActivity)" | head -4 >>"$REPORT"
adb logcat -d -t 500 | grep -E "(FATAL EXCEPTION|AndroidRuntime|crash)" | tail -30 >>"$REPORT"
echo "Finished. A screenshot alone is not evidence of original draw order." >>"$REPORT"
exit 0
