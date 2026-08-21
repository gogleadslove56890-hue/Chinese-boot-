# Chinese-boot Android Companion

This companion is a permission-aware overlay shell for the scanner website. It does not automate Olymp Trade, inspect platform UI, click DOM elements, use private endpoints, or handle credentials.

## Build

Open this directory in Android Studio with an Android SDK installed. The app targets Android 8.0+ and uses a foreground service only after the user explicitly enables the overlay. Configure a stable, deployed backend before syncing or building:

```bash
export SCANNER_BACKEND_URL=https://scanner.example.com
gradle :app:assembleRelease
```

`-PscannerBackendUrl=https://scanner.example.com` can be used instead of the environment variable. The build intentionally fails when neither value is supplied; a Codespaces URL must not be embedded as a production default.

## Behavior

- Requests `SYSTEM_ALERT_WINDOW` through the Android settings screen.
- Shows a draggable scanner bubble after explicit enablement.
- Tapping the bubble opens a manual scanner panel with asset, timeframe, verified-data status, signal, confidence, mode, start, stop, and emergency-stop controls.
- The panel reports `WAIT` when no verified market source is available; it never invents prices or signals.
- The overlay can be disabled from the app and is removed when the service stops.
- AUTO execution remains unavailable until an official authorized Olymp Trade trading integration exists.
