package com.chineseboot.scanner

import org.json.JSONObject
import java.io.BufferedReader
import java.io.InputStreamReader
import java.net.HttpURLConnection
import java.net.URL

object ScannerApi {
    private fun request(baseUrl: String, path: String, method: String, body: JSONObject? = null): JSONObject {
        val normalized = baseUrl.trim().removeSuffix("/")
        require(normalized.startsWith("http://") || normalized.startsWith("https://")) {
            "Backend URL must start with http:// or https://."
        }
        val endpoint = normalized + path
        val connection = URL(endpoint).openConnection() as HttpURLConnection
        connection.requestMethod = method
        connection.connectTimeout = 8000
        connection.readTimeout = 12000
        connection.setRequestProperty("Accept", "application/json")
        if (body != null) {
            connection.doOutput = true
            connection.setRequestProperty("Content-Type", "application/json")
            connection.outputStream.use { it.write(body.toString().toByteArray(Charsets.UTF_8)) }
        }
        val stream = if (connection.responseCode in 200..299) connection.inputStream else connection.errorStream
        val response = stream?.use { input -> BufferedReader(InputStreamReader(input)).readText() }.orEmpty()
        if (connection.responseCode !in 200..299) {
            val detail = runCatching { JSONObject(response).optString("detail") }.getOrNull().orEmpty()
            val reason = detail.ifBlank { response.trim().ifBlank { "No response body." } }
            throw IllegalStateException("Backend request failed (${connection.responseCode}) at $endpoint: $reason")
        }
        return runCatching { JSONObject(response) }.getOrElse {
            throw IllegalStateException("Backend returned invalid JSON.")
        }
    }

    fun scan(baseUrl: String, symbol: String, timeframeSeconds: Int, limit: Int = 100): JSONObject {
        return request(baseUrl, "/api/scanner/scan", "POST", JSONObject()
            .put("symbol", symbol)
            .put("timeframe_seconds", timeframeSeconds)
            .put("limit", limit))
    }

    fun stop(baseUrl: String): JSONObject = request(baseUrl, "/api/scanner/stop", "POST")

    fun emergencyStop(baseUrl: String): JSONObject = request(baseUrl, "/api/scanner/emergency-stop", "POST")
}
