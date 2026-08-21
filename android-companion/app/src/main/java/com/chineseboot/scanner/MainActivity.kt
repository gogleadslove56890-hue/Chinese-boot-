package com.chineseboot.scanner

import android.content.Intent
import android.net.Uri
import android.os.Bundle
import android.os.Build
import android.provider.Settings
import android.widget.Button
import android.widget.CompoundButton
import android.widget.LinearLayout
import android.widget.Switch
import android.widget.TextView
import androidx.appcompat.app.AppCompatActivity
import androidx.core.app.ActivityCompat

class MainActivity : AppCompatActivity() {
    private lateinit var status: TextView
    private lateinit var enableSwitch: Switch
    private lateinit var scanStatus: TextView

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val layout = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; setPadding(32, 48, 32, 32) }
        status = TextView(this).apply { textSize = 16f }
        scanStatus = TextView(this).apply { textSize = 14f; setPadding(0, 24, 0, 24) }
        val permission = Button(this).apply { text = "Enable Floating Scanner" }
        enableSwitch = Switch(this).apply { text = "Floating scanner enabled" }
        val manualNotice = TextView(this).apply {
            text = "Backend: ${BuildConfig.DEFAULT_BACKEND_URL}\nSignals use independently verified market data. AUTO trading remains disabled."
            setPadding(0, 24, 0, 24)
        }
        layout.addView(status)
        layout.addView(scanStatus)
        layout.addView(permission)
        layout.addView(enableSwitch)
        layout.addView(manualNotice)
        val scanOnce = Button(this).apply {
            text = "Scan Once Without Overlay"
            setOnClickListener {
                scanStatus.text = "Connecting to production backend..."
                Thread {
                    runCatching { ScannerApi.scan(BuildConfig.DEFAULT_BACKEND_URL, "EUR/USD", 60) }
                        .onSuccess { result -> runOnUiThread { scanStatus.text = formatResult(result) } }
                        .onFailure { error -> runOnUiThread { scanStatus.text = error.message ?: "Scanner request failed." } }
                }.start()
            }
        }
        layout.addView(scanOnce)
        setContentView(layout)

        permission.setOnClickListener {
            if (!Settings.canDrawOverlays(this)) {
                startActivity(Intent(Settings.ACTION_MANAGE_OVERLAY_PERMISSION, Uri.parse("package:$packageName")))
            } else {
                enableSwitch.isChecked = true
            }
        }
        enableSwitch.setOnCheckedChangeListener { _: CompoundButton, checked: Boolean ->
            getPreferences(MODE_PRIVATE).edit().putBoolean("overlay_enabled", checked).apply()
            if (checked && Settings.canDrawOverlays(this)) {
                OverlayService.start(this)
            } else {
                if (checked) status.text = "Grant Display over other apps permission first."
                stopService(Intent(this, OverlayService::class.java))
            }
        }
        if (Build.VERSION.SDK_INT >= 33) ActivityCompat.requestPermissions(this, arrayOf("android.permission.POST_NOTIFICATIONS"), 42)
    }

    private fun formatResult(result: org.json.JSONObject): String = buildString {
        append("HTTP 200\n")
        append("Data: ").append(result.optString("source_status", "unknown")).append('\n')
        append("Signal: ").append(result.optString("signal", "WAIT")).append('\n')
        append("Confidence: ").append(result.optInt("confidence", 0)).append("%\n")
        append("Price: ").append(result.optDouble("price", Double.NaN)).append('\n')
        append("Provider: ").append(result.optString("provider", "unknown")).append('\n')
        append("Candle: ").append(result.optString("candle_timestamp", "unknown"))
    }

    override fun onResume() {
        super.onResume()
        val enabled = getPreferences(MODE_PRIVATE).getBoolean("overlay_enabled", false)
        enableSwitch.isChecked = enabled && Settings.canDrawOverlays(this)
        status.text = if (Settings.canDrawOverlays(this) && enabled) {
            "Floating scanner is active."
        } else {
            "Overlay disabled. Manual scanner is available when enabled."
        }
    }
}
