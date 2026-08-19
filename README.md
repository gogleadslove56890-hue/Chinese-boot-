# Chinese-boot

Olymp Trade real-time market signal generator.

## Timeframes
- 5 seconds
- 10 seconds
- 15 seconds
- 30 seconds
- 1 minute
- 2 minutes
- 3 minutes
- 5 minutes

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

2. Set the Twelve Data credential in the environment. Never put it in source
	files or commit it:

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

Open `http://127.0.0.1:8000/`. The dashboard uses the same origin by default;
set `window.API_BASE` before the frontend script when hosting it separately.

## API

- `GET /api/health` reports application and provider configuration status.
- `GET /api/assets` returns the documented assets and timeframes.
- `GET /api/quote?symbol=EUR/USD` returns a verified Twelve Data quote.
- `GET /api/candles?symbol=EUR/USD&timeframe_seconds=60&limit=100` returns
  validated OHLC candles.
- The equivalent `timeframe=1min&seconds=60` form is also accepted; the two
	values must agree.
- `POST /api/analyze` analyzes a supplied set of verified candles.

Twelve Data is queried directly for 1-minute and 5-minute candles. The
documented 5-, 10-, 15-, 30-second and 2-/3-minute choices are shown honestly
but return an unsupported-timeframe response until a verified aggregation
strategy is added. Missing credentials and provider failures never create
replacement prices or signals.

