# Chinese-boot

Independent real-time market scanner. Olymp Trade remains outside the scanner's
data path and is never controlled automatically.

## Timeframes
- 1 minute
- 5 minutes
- 15 minutes
- 30 minutes
- 1 hour

## Initial Forex Assets
- EUR/USD
- GBP/USD
- USD/JPY
- AUD/USD
- USD/CAD
- NZD/USD
- GBP/JPY

## Project Goal
Real-time market scanning, candle analysis and UP/DOWN signals based on verified market data.

## Important
The project must not generate fake market data or fake signals.

## Setup

1. Create a virtual environment and install dependencies:

	```bash
	python -m venv .venv
	. .venv/bin/activate
	pip install -r requirements.txt
	```

2. The scanner uses Yahoo Finance as an independent public fallback. If a
	Twelve Data credential is configured, Twelve Data is tried first and Yahoo
	Finance is tried after provider errors, rate limits, malformed data, or stale
	candles. Set the credential in the environment; never commit it:

	```bash
	export TWELVE_DATA_API_KEY=your_key
	```

	An alternate API base URL can be supplied with `TWELVE_DATA_BASE_URL` for
	testing or an approved deployment. For a separately hosted frontend,
	provide its comma-separated origins with `FRONTEND_ORIGINS`.

3. Start the application:

	```bash
	uvicorn backend.app:app --reload
	```

### Render deployment

The repository includes `render.yaml` for a Render web service. Connect this
GitHub repository in the Render dashboard and use the blueprint configuration.
Render supplies the public HTTPS URL and `PORT` automatically. The production
start command is:

```bash
uvicorn backend.app:app --host 0.0.0.0 --port $PORT
```

Set `TWELVE_DATA_API_KEY` as a Render secret when Twelve Data access is
available. `TWELVE_DATA_BASE_URL` and `FRONTEND_ORIGINS` are service settings;
the latter should contain the deployed frontend origin when hosted separately.
Never commit these values or put them in the Android APK.

Open `http://127.0.0.1:8000/`. The dashboard uses the same origin by default;
set `window.API_BASE` before the frontend script when hosting it separately.

## API

- `GET /api/health` reports application and provider configuration status.
- `GET /api/assets` returns the documented assets and timeframes.
- `GET /api/quote?symbol=EUR/USD` returns a quote from the configured provider
	with provider and verification metadata.
- `GET /api/candles?symbol=EUR/USD&timeframe_seconds=60&limit=100` returns
  validated OHLC candles.
- The equivalent `timeframe=1min&seconds=60` form is also accepted; the two
	values must agree.
- `POST /api/analyze` analyzes a supplied set of verified candles.

Missing credentials, stale/malformed responses, provider failures, and source
mismatches never create replacement prices, candles, or signals. All candles
are normalized to UTC and must be closed and fresh. The scanner uses the next
higher timeframe as confirmation and returns `WAIT` on a conflict.

## Scanner safety

The floating web scanner is Manual-only while Olymp Trade live data and
authorized execution are unavailable. It exposes `/api/scanner/scan`,
`/api/scanner/start`, `/api/scanner/stop`, `/api/scanner/emergency-stop`,
`/api/scanner/status`, and `/api/scanner/live`. Every unavailable scan returns
`WAIT` with no price. Auto mode is rejected until Olymp Trade supplies an
authorized trading API or partner integration.

`android-companion/` contains the Android overlay companion source. It asks the
user for explicit Display over other apps permission and runs a visible
foreground service with a draggable bubble. An Android SDK is required to build
the APK; no APK is produced in this repository environment.

