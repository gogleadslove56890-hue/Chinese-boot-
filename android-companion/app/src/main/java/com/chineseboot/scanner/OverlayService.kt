package com.chineseboot.scanner

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.Service
import android.content.Context
import android.content.Intent
import android.graphics.Color
import android.graphics.PixelFormat
import android.os.Handler
import android.os.IBinder
import android.os.Looper
import android.provider.Settings
import android.view.Gravity
import android.view.MotionEvent
import android.view.View
import android.view.ViewGroup
import android.view.WindowManager
import android.widget.ArrayAdapter
import android.widget.Button
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.Spinner
import android.widget.TextView
import androidx.core.content.ContextCompat
import java.util.Locale
import java.util.concurrent.ScheduledExecutorService
import java.util.concurrent.ScheduledFuture
import java.util.concurrent.Executors
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicBoolean

class OverlayService : Service() {
    private var windowManager: WindowManager? = null
    private var bubble: TextView? = null
    private var panel: View? = null
    private var statusView: TextView? = null
    private var panelParams: WindowManager.LayoutParams? = null
    private val executor: ScheduledExecutorService = Executors.newScheduledThreadPool(2)
    private val mainHandler = Handler(Looper.getMainLooper())
    private val scanning = AtomicBoolean(false)
    private var scanFuture: ScheduledFuture<*>? = null
    @Volatile private var latestStatus = "Data: NOT CONNECTED\nSignal: WAIT\nConfidence: 0%\nMode: IDLE"
    @Volatile private var latestResult: org.json.JSONObject? = null
    @Volatile private var scanBaseUrl = ""
    @Volatile private var scanSymbol = ""
    @Volatile private var scanTimeframe = 60

    companion object {
        fun start(context: Context) {
            ContextCompat.startForegroundService(context, Intent(context, OverlayService::class.java))
        }
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        if (!Settings.canDrawOverlays(this)) { stopSelf(); return START_NOT_STICKY }
        startForeground(7, notification())
        showBubble()
        return START_STICKY
    }

    private fun showBubble() {
        windowManager = getSystemService(WINDOW_SERVICE) as WindowManager
        if (bubble != null) return
        bubble = TextView(this).apply {
            textSize = 11f
            setTypeface(typeface, android.graphics.Typeface.BOLD)
            setTextColor(Color.WHITE)
            gravity = Gravity.CENTER
            setPadding(8, 4, 8, 4)
            minWidth = 58.dp()
            minHeight = 36.dp()
        }
        val params = WindowManager.LayoutParams(
            WindowManager.LayoutParams.WRAP_CONTENT, 42.dp(),
            WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY,
            WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE,
            PixelFormat.TRANSLUCENT
        ).apply { gravity = Gravity.TOP or Gravity.END; x = 12.dp(); y = 180.dp() }
        bubble?.setOnTouchListener(DragListener(params))
        windowManager?.addView(bubble, params)
        renderBubble()
    }

    private fun showPanel() {
        if (panel != null) { renderPanel(); return }
        val preferences = getSharedPreferences("scanner", MODE_PRIVATE)
        val content = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(28.dp(), 24.dp(), 28.dp(), 24.dp())
            setBackgroundColor(Color.WHITE)
        }
        content.addView(TextView(this).apply { text = "Floating Scanner"; textSize = 20f; setTextColor(Color.BLACK) })
        val backend = TextView(this).apply {
            text = "Backend: ${BuildConfig.DEFAULT_BACKEND_URL}"
            setTextColor(Color.DKGRAY)
            setPadding(0, 8.dp(), 0, 8.dp())
        }
        val backendUrl = BuildConfig.DEFAULT_BACKEND_URL
        val asset = EditText(this).apply {
            hint = "Asset, e.g. EUR/USD"
            setSingleLine(true)
            setText(preferences.getString("asset", "EUR/USD"))
        }
        val backendEndpoint = backendUrl
        val timeframe = Spinner(this).apply {
            adapter = ArrayAdapter(this@OverlayService, android.R.layout.simple_spinner_dropdown_item, arrayOf("1 minute", "5 minutes", "15 minutes", "30 minutes", "1 hour"))
            setSelection(arrayOf(60, 300, 900, 1800, 3600).indexOf(preferences.getInt("timeframe_seconds", 60)).coerceAtLeast(0))
        }
        statusView = TextView(this).apply { setTextColor(Color.DKGRAY); setPadding(0, 16.dp(), 0, 16.dp()) }
        content.addView(backend)
        content.addView(asset)
        content.addView(timeframe)
        content.addView(statusView)
        content.addView(Button(this).apply {
            text = "Automatic Scan"
            setOnClickListener {
                val seconds = intArrayOf(60, 300, 900, 1800, 3600)[timeframe.selectedItemPosition]
                val url = backendEndpoint
                val symbol = asset.text.toString().trim()
                preferences.edit().putString("backend_url", url).putString("asset", symbol).putInt("timeframe_seconds", seconds).apply()
                startAutomaticScan(url, symbol, seconds)
            }
        })
        content.addView(Button(this).apply {
            text = "Scan Once"
            setOnClickListener {
                val seconds = intArrayOf(60, 300, 900, 1800, 3600)[timeframe.selectedItemPosition]
                scanOnce(backendEndpoint, asset.text.toString().trim(), seconds)
            }
        })
        content.addView(Button(this).apply {
            text = "Stop Scan"
            setOnClickListener { stopScan(backendEndpoint) }
        })
        content.addView(Button(this).apply {
            text = "Emergency Stop"
            setOnClickListener { emergencyStop(backendEndpoint) }
        })
        content.addView(Button(this).apply { text = "Close"; setOnClickListener { hidePanel() } })
        panel = ScrollView(this).apply { addView(content) }
        panelParams = WindowManager.LayoutParams(
            320.dp(), ViewGroup.LayoutParams.WRAP_CONTENT,
            WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY,
            WindowManager.LayoutParams.FLAG_NOT_TOUCH_MODAL, PixelFormat.TRANSLUCENT
        ).apply { gravity = Gravity.CENTER }
        windowManager?.addView(panel, panelParams)
        renderPanel()
    }

    private fun startAutomaticScan(baseUrl: String, symbol: String, timeframe: Int) {
        if (symbol.isBlank()) { setStatus("Data: UNAVAILABLE\nSignal: WAIT\nConfidence: 0%\nReason: Enter a currency pair such as EUR/USD"); return }
        if (!scanning.compareAndSet(false, true)) { hidePanel(); return }
        scanBaseUrl = baseUrl; scanSymbol = symbol; scanTimeframe = timeframe
        setStatus("Data: CONNECTING\nSignal: WAIT\nConfidence: 0%\nMode: SCANNING")
        executor.execute {
            try {
                mainHandler.post { hidePanel() }
                scanFuture = executor.scheduleWithFixedDelay({ scanOnceOnWorker() }, 0, timeframe.toLong(), TimeUnit.SECONDS)
            } catch (error: Exception) {
                scanning.set(false)
                mainHandler.post { setStatus("Data: UNAVAILABLE\nSignal: WAIT\nConfidence: 0%\nReason: ${error.message ?: "Backend connection failed."}") }
            }
        }
    }

    private fun scanOnce(baseUrl: String, symbol: String, timeframe: Int) {
        if (scanning.get()) return
        if (symbol.isBlank()) { setStatus("Data: UNAVAILABLE\nSignal: WAIT\nConfidence: 0%\nReason: Enter a currency pair such as EUR/USD"); return }
        scanBaseUrl = baseUrl; scanSymbol = symbol; scanTimeframe = timeframe
        setStatus("Data: CONNECTING\nSignal: WAIT\nConfidence: 0%\nMode: MANUAL")
        executor.execute {
            runCatching { ScannerApi.scan(baseUrl, symbol, timeframe) }
                .onSuccess { result -> mainHandler.post { renderResult(result) } }
                .onFailure { error -> mainHandler.post { setStatus("Data: UNAVAILABLE\nSignal: WAIT\nConfidence: 0%\nReason: ${error.message ?: "Backend connection failed."}") } }
        }
    }

    private fun scanOnceOnWorker() {
        if (!scanning.get()) return
        runCatching { ScannerApi.scan(scanBaseUrl, scanSymbol, scanTimeframe) }
            .onSuccess { result -> mainHandler.post { renderResult(result) } }
            .onFailure { error -> mainHandler.post { setStatus("Data: UNAVAILABLE\nSignal: WAIT\nConfidence: 0%\nReason: ${error.message ?: "Backend connection failed."}\nMode: SCANNING") } }
    }

    private fun stopScan(baseUrl: String) {
        if (!scanning.compareAndSet(true, false)) { latestResult = null; removeBubble(); setStatus("Data: STOPPED\nSignal: WAIT\nConfidence: 0%\nMode: IDLE"); return }
        scanFuture?.cancel(true); scanFuture = null
        removeBubble()
        executor.execute {
            runCatching { ScannerApi.stop(baseUrl) }
            mainHandler.post { latestResult = null; setStatus("Data: STOPPED\nSignal: WAIT\nConfidence: 0%\nMode: IDLE") }
        }
    }

    private fun emergencyStop(baseUrl: String) {
        scanning.set(false); scanFuture?.cancel(true); scanFuture = null
        removeBubble()
        executor.execute {
            runCatching { ScannerApi.emergencyStop(baseUrl) }
            mainHandler.post { latestResult = null; setStatus("Data: STOPPED\nSignal: WAIT\nConfidence: 0%\nEMERGENCY STOP ACTIVE") }
        }
    }

    private fun renderResult(result: org.json.JSONObject) {
        latestResult = result
        val available = result.optString("source_status") == "verified" && result.optString("status") == "ready"
        if (!available) {
            setStatus("Data: UNAVAILABLE\nSignal: WAIT\nConfidence: 0%\nReason: ${result.optString("reason", "Verified market data unavailable.")}\nMode: ${if (scanning.get()) "SCANNING" else "MANUAL"}")
            return
        }
        val price = result.optDouble("price", Double.NaN)
        val priceText = if (price.isFinite()) String.format(Locale.US, "%.5f", price) else "--"
        val signal = result.optString("signal", "WAIT").uppercase(Locale.US)
        val confidence = result.optInt("confidence", 0)
        val reasons = result.optJSONArray("reasons")
        val against = result.optJSONArray("reasons_against")
        val reasonText = buildString {
            append("\nSupporting:")
            for (index in 0 until (reasons?.length() ?: 0)) append("\n- ").append(reasons?.optString(index))
            append("\nAgainst:")
            for (index in 0 until (against?.length() ?: 0)) append("\n- ").append(against?.optString(index))
        }
        val current = result.optJSONObject("current_candle")
        val candleText = "O ${current?.optDouble("open", Double.NaN)} H ${current?.optDouble("high", Double.NaN)} L ${current?.optDouble("low", Double.NaN)} C ${current?.optDouble("close", Double.NaN)}"
        val dataStatus = result.optJSONObject("data_status")
        val freshness = dataStatus?.optString("status", "unknown") ?: "unknown"
        setStatus("Data: VERIFIED\nSymbol: ${result.optString("symbol")}\nPrice: $priceText\nCandle: $candleText\nTimeframe: ${result.optInt("timeframe_seconds")}s\nTrend: ${result.optString("trend", "UNKNOWN")}\nMomentum: ${result.optJSONObject("momentum")?.optString("direction", "MIXED")}\nSupport: ${result.optJSONObject("levels")?.optDouble("support", Double.NaN)}\nResistance: ${result.optJSONObject("levels")?.optDouble("resistance", Double.NaN)}\nVolatility: ${result.optJSONObject("volatility")?.optDouble("average_range", Double.NaN)}\nData freshness: $freshness\nCurrent UTC: ${dataStatus?.optString("current_utc", "unknown")}\nCandle UTC: ${dataStatus?.optString("latest_candle_timestamp", "unknown")}\nCandle age: ${dataStatus?.optDouble("age_seconds", Double.NaN)}s\nCandle closed: ${dataStatus?.optBoolean("closed", false)}\n\nSIGNAL\nDirection: $signal\nConfidence: $confidence%\nEntry: ${result.optString("entry_direction", "WAIT")}\nReason:$reasonText\n\n${result.optString("trade_decision", "NO TRADE")}\nProvider: ${result.optString("provider", "unknown")}\nMode: ${if (scanning.get()) "SCANNING" else "MANUAL"}")
    }

    private fun setStatus(message: String) {
        latestStatus = message
        statusView?.text = message
        renderBubble()
    }

    private fun renderPanel() { statusView?.text = latestStatus; renderBubble() }

    private fun renderBubble() {
        val view = bubble ?: return
        val result = latestResult
        val signal = result?.optString("signal", "WAIT")?.uppercase(Locale.US) ?: "WAIT"
        val confidence = result?.optInt("confidence", 0) ?: 0
        val icon = "●"
        view.text = if (scanning.get()) "$icon $signal\n$confidence%" else "SCAN"
        view.setBackgroundColor(when (signal) { "UP" -> Color.rgb(35, 145, 75); "DOWN" -> Color.rgb(190, 55, 55); "WAIT" -> Color.DKGRAY; else -> Color.DKGRAY })
    }

    private fun hidePanel() {
        panel?.let { runCatching { windowManager?.removeView(it) } }
        panel = null; statusView = null
    }

    private fun removeBubble() {
        bubble?.let { runCatching { windowManager?.removeView(it) } }
        bubble = null
    }

    private fun Int.dp(): Int = (this * resources.displayMetrics.density).toInt()

    private fun notification(): Notification {
        val channel = NotificationChannel("scanner", "Scanner overlay", NotificationManager.IMPORTANCE_LOW)
        getSystemService(NotificationManager::class.java).createNotificationChannel(channel)
        return Notification.Builder(this, "scanner").setContentTitle("Chinese-boot scanner").setContentText("Floating scanner active").setSmallIcon(android.R.drawable.ic_menu_search).build()
    }

    override fun onDestroy() {
        scanning.set(false); scanFuture?.cancel(true); hidePanel()
        bubble?.let { runCatching { windowManager?.removeView(it) } }
        bubble = null; executor.shutdownNow(); super.onDestroy()
    }

    override fun onBind(intent: Intent?): IBinder? = null

    private inner class DragListener(private val params: WindowManager.LayoutParams) : View.OnTouchListener {
        private var downX = 0f; private var downY = 0f; private var startX = 0; private var startY = 0
        override fun onTouch(view: View, event: MotionEvent): Boolean {
            when (event.action) {
                MotionEvent.ACTION_DOWN -> { downX = event.rawX; downY = event.rawY; startX = params.x; startY = params.y; return true }
                MotionEvent.ACTION_MOVE -> { params.x = startX + (downX - event.rawX).toInt(); params.y = startY + (event.rawY - downY).toInt(); windowManager?.updateViewLayout(view, params); return true }
                MotionEvent.ACTION_UP -> { if (kotlin.math.abs(event.rawX - downX) < 12 && kotlin.math.abs(event.rawY - downY) < 12) showPanel(); return true }
            }
            return false
        }
    }
}
