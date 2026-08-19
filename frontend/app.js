"use strict";

const state = {
  symbol: "EUR/USD",
  timeframe: 60,
  limit: 100,
  candles: [],
  timer: null
};

const $ = (selector) => document.querySelector(selector);

function findElement(...selectors) {
  for (const selector of selectors) {
    const element = $(selector);
    if (element) return element;
  }
  return null;
}

async function api(url) {
  const response = await fetch(url);

  if (!response.ok) {
    throw new Error(`API error: ${response.status}`);
  }

  return response.json();
}

async function loadAssets() {
  try {
    const data = await api("/api/assets");

    state.assets = data.assets || [];
    state.timeframes = data.timeframes || [];

    const symbolSelect = findElement(
      "#symbol",
      "#symbolSelect",
      "select[name='symbol']",
      ".symbol-select"
    );

    if (symbolSelect && state.assets.length) {
      symbolSelect.innerHTML = "";

      state.assets.forEach((asset) => {
        const option = document.createElement("option");
        option.value = asset;
        option.textContent = asset;
        symbolSelect.appendChild(option);
      });

      symbolSelect.value = state.symbol;
    }
  } catch (error) {
    console.error("Failed to load assets:", error);
  }
}

async function loadMarketData() {
  try {
    const quote = await api(
      `/api/quote?symbol=${encodeURIComponent(state.symbol)}`
    );

    updateQuote(quote);

    const candles = await api(
      `/api/candles?symbol=${encodeURIComponent(
        state.symbol
      )}&timeframe_seconds=${state.timeframe}&limit=${state.limit}`
    );

    state.candles = candles.candles || [];

    renderChart(state.candles);
    updateSignal(state.candles);
  } catch (error) {
    console.error("Market data error:", error);
    showStatus("Market data unavailable");
  }
}

function updateQuote(data) {
  const price = data.price;

  const priceElement = findElement(
    "#price",
    "#currentPrice",
    ".price",
    "[data-price]"
  );

  const symbolElement = findElement(
    "#currentSymbol",
    "#selectedSymbol",
    ".current-symbol",
    "[data-symbol]"
  );

  if (symbolElement) {
    symbolElement.textContent = data.symbol || state.symbol;
  }

  if (priceElement) {
    if (price !== null && price !== undefined) {
      priceElement.textContent = Number(price).toFixed(5);
    } else {
      priceElement.textContent = "--";
    }
  }
}

function renderChart(candles) {
  let canvas = findElement(
    "#chart",
    "#priceChart",
    "canvas[data-chart]"
  );

  if (!canvas) {
    const container = findElement(
      "#chartContainer",
      ".chart-container",
      ".chart",
      ".app"
    );

    if (!container) return;

    canvas = document.createElement("canvas");
    canvas.id = "priceChart";
    canvas.dataset.chart = "true";

    canvas.style.width = "100%";
    canvas.style.height = "420px";
    canvas.style.display = "block";

    container.appendChild(canvas);
  }

  const rect = canvas.getBoundingClientRect();
  const width = Math.max(rect.width, 300);
  const height = Math.max(rect.height, 300);
  const dpr = window.devicePixelRatio || 1;

  canvas.width = width * dpr;
  canvas.height = height * dpr;

  const ctx = canvas.getContext("2d");

  if (!ctx || !candles.length) {
    return;
  }

  ctx.scale(dpr, dpr);
  ctx.clearRect(0, 0, width, height);

  const prices = candles.flatMap((c) => [
    Number(c.high),
    Number(c.low)
  ]);

  const maxPrice = Math.max(...prices);
  const minPrice = Math.min(...prices);

  const range = maxPrice - minPrice || 1;

  const padding = 30;
  const chartHeight = height - padding * 2;
  const chartWidth = width - padding * 2;

  const candleWidth = Math.max(
    4,
    Math.min(18, chartWidth / candles.length * 0.7)
  );

  candles.forEach((candle, index) => {
    const open = Number(candle.open);
    const high = Number(candle.high);
    const low = Number(candle.low);
    const close = Number(candle.close);

    if (
      !Number.isFinite(open) ||
      !Number.isFinite(high) ||
      !Number.isFinite(low) ||
      !Number.isFinite(close)
    ) {
      return;
    }

    const x =
      padding +
      (index / Math.max(candles.length - 1, 1)) * chartWidth;

    const y = (price) =>
      padding +
      ((maxPrice - price) / range) * chartHeight;

    const openY = y(open);
    const closeY = y(close);
    const highY = y(high);
    const lowY = y(low);

    const bullish = close >= open;

    ctx.beginPath();
    ctx.moveTo(x, highY);
    ctx.lineTo(x, lowY);

    ctx.strokeStyle = bullish ? "#22c55e" : "#ef4444";
    ctx.lineWidth = 1;
    ctx.stroke();

    const bodyTop = Math.min(openY, closeY);
    const bodyHeight = Math.max(
      Math.abs(closeY - openY),
      2
    );

    ctx.fillStyle = bullish ? "#22c55e" : "#ef4444";

    ctx.fillRect(
      x - candleWidth / 2,
      bodyTop,
      candleWidth,
      bodyHeight
    );
  });
}

function updateSignal(candles) {
  const signalElement = findElement(
    "#signal",
    "#marketSignal",
    ".signal",
    "[data-signal]"
  );

  if (!signalElement || candles.length < 2) {
    return;
  }

  const previous = candles[candles.length - 2];
  const latest = candles[candles.length - 1];

  const previousClose = Number(previous.close);
  const latestClose = Number(latest.close);

  if (!Number.isFinite(previousClose) || !Number.isFinite(latestClose)) {
    signalElement.textContent = "WAIT";
    return;
  }

  if (latestClose > previousClose) {
    signalElement.textContent = "UP";
  } else if (latestClose < previousClose) {
    signalElement.textContent = "DOWN";
  } else {
    signalElement.textContent = "WAIT";
  }
}

function showStatus(message) {
  const statusElement = findElement(
    "#status",
    ".status",
    "[data-status]"
  );

  if (statusElement) {
    statusElement.textContent = message;
  }
}

function setupControls() {
  const symbolSelect = findElement(
    "#symbol",
    "#symbolSelect",
    "select[name='symbol']",
    ".symbol-select"
  );

  if (symbolSelect) {
    symbolSelect.addEventListener("change", () => {
      state.symbol = symbolSelect.value || "EUR/USD";
      loadMarketData();
    });
  }

  const timeframeSelect = findElement(
    "#timeframe",
    "#timeframeSelect",
    "select[name='timeframe']",
    ".timeframe-select"
  );

  if (timeframeSelect) {
    timeframeSelect.addEventListener("change", () => {
      const value = Number(timeframeSelect.value);

      if (Number.isFinite(value) && value > 0) {
        state.timeframe = value;
        loadMarketData();
      }
    });
  }

  window.addEventListener("resize", () => {
    if (state.candles.length) {
      renderChart(state.candles);
    }
  });
}

function startLiveUpdates() {
  if (state.timer) {
    clearInterval(state.timer);
  }

  state.timer = setInterval(() => {
    loadMarketData();
  }, 10000);
}

async function init() {
  console.log("Chinese-Boot dashboard starting...");

  setupControls();

  await loadAssets();
  await loadMarketData();

  startLiveUpdates();

  showStatus("LIVE");
}

document.addEventListener("DOMContentLoaded", init);
