"use strict";

const API_BASE = window.API_BASE || "";

async function fetchJson(path, options) {
  const response = await fetch(`${API_BASE}${path}`, options);
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(data.detail || `API error: ${response.status}`);
  }
  return data;
}

function formatNumber(value) {
  return Number.isFinite(Number(value)) ? Number(value).toFixed(5) : "--";
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

window.ChineseBootApi = { fetchJson, formatNumber, escapeHtml };
