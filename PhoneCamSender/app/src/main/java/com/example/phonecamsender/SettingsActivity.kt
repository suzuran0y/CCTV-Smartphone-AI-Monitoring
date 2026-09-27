package com.example.phonecamsender

import android.app.Activity
import android.os.Bundle
import android.widget.*
import androidx.appcompat.app.AppCompatActivity
import okhttp3.*
import java.io.IOException
import java.util.concurrent.TimeUnit
import org.json.JSONObject
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.RequestBody.Companion.toRequestBody

class SettingsActivity : AppCompatActivity() {

    private val prefs by lazy { getSharedPreferences("phonecam", MODE_PRIVATE) }
    private val okHttp = OkHttpClient.Builder()
        .followRedirects(false)
        .followSslRedirects(false)
        .connectTimeout(5, TimeUnit.SECONDS)
        .readTimeout(10, TimeUnit.SECONDS)
        .build()

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_settings)

        val addrInput = findViewById<EditText>(R.id.addrInput)
        val btnTest = findViewById<Button>(R.id.btnTest)
        val btnSave = findViewById<Button>(R.id.btnSave)
        val swDebug = findViewById<Switch>(R.id.switchShowDebug)
        val swHide = findViewById<Switch>(R.id.switchHidePreview)
        val swStop = findViewById<Switch>(R.id.switchStopCamera)
        val spinnerQuality = findViewById<Spinner>(R.id.spinnerImageQuality)
        val spinnerUploadRate = findViewById<Spinner>(R.id.spinnerUploadRate)
        val spinnerResolution = findViewById<Spinner>(R.id.spinnerResolution)
        findViewById<TextView>(R.id.textVersion).text =
            getString(R.string.camflow_version_format, BuildConfig.VERSION_NAME)

        swHide.isChecked = prefs.getBoolean("hidePreview", false)
        swStop.isChecked = prefs.getBoolean("stopCamera", false)
        swStop.setOnCheckedChangeListener { _, isChecked ->
            if (isChecked) swHide.isChecked = true
        }

        val qualityOptions = listOf("Low", "Medium", "High")
        val qualityAdapter = ArrayAdapter(
            this,
            android.R.layout.simple_spinner_item,
            qualityOptions
        )
        qualityAdapter.setDropDownViewResource(android.R.layout.simple_spinner_dropdown_item)
        spinnerQuality.adapter = qualityAdapter

        val savedQuality = prefs.getString("imageQualityLabel", "Medium") ?: "Medium"
        val savedIndex = qualityOptions.indexOf(savedQuality).takeIf { it >= 0 } ?: 1
        spinnerQuality.setSelection(savedIndex)

        val uploadRateOptions = listOf("Low", "Medium", "High")
        val uploadRateAdapter = ArrayAdapter(
            this,
            android.R.layout.simple_spinner_item,
            uploadRateOptions
        )
        uploadRateAdapter.setDropDownViewResource(android.R.layout.simple_spinner_dropdown_item)
        spinnerUploadRate.adapter = uploadRateAdapter

        val savedUploadRate = prefs.getString("uploadRateLabel", "High") ?: "High"
        val savedUploadRateIndex = uploadRateOptions.indexOf(savedUploadRate).takeIf { it >= 0 } ?: 2
        spinnerUploadRate.setSelection(savedUploadRateIndex)

        val resolutionOptions = listOf("Low", "Medium", "High")
        val resolutionAdapter = ArrayAdapter(
            this,
            android.R.layout.simple_spinner_item,
            resolutionOptions
        )
        resolutionAdapter.setDropDownViewResource(android.R.layout.simple_spinner_dropdown_item)
        spinnerResolution.adapter = resolutionAdapter

        val savedResolution = prefs.getString("resolutionLabel", "Medium") ?: "Medium"
        val savedResolutionIndex = resolutionOptions.indexOf(savedResolution).takeIf { it >= 0 } ?: 1
        spinnerResolution.setSelection(savedResolutionIndex)


// Initialize the switch status
        swDebug.isChecked = prefs.getBoolean("showDebug", false)
        addrInput.setText(prefs.getString("serverInput", "") ?: "")
        val pairStatus = findViewById<TextView>(R.id.pairStatus)
        val pairButton = findViewById<Button>(R.id.btnPair)
        val pairCode = findViewById<EditText>(R.id.pairCode)
        val deviceName = findViewById<EditText>(R.id.deviceName)
        deviceName.setText(prefs.getString("deviceName", android.os.Build.MODEL))
        fun refreshPairStatus() {
            val server = NetworkDiscover.inputToBaseUrlOrNull(addrInput.text.toString().trim())
            val context = applicationContext
            kotlin.concurrent.thread {
                val paired = server != null && DeviceCredentials.tokenFor(context, server) != null
                val last = prefs.getLong("lastUploadSuccess", 0)
                runOnUiThread {
                    pairStatus.text = (if (paired) "Paired locally; revoked devices must pair again." else "Not paired — ask the administrator for a code.") +
                        "\nLast upload: " + if (last > 0) java.text.DateFormat.getDateTimeInstance().format(java.util.Date(last)) else "none"
                }
            }
        }
        refreshPairStatus()
        findViewById<Button>(R.id.btnClearPairing).setOnClickListener {
            DeviceCredentials.clear(applicationContext)
            refreshPairStatus()
        }
        pairButton.setOnClickListener {
            val server = NetworkDiscover.inputToBaseUrlOrNull(addrInput.text.toString().trim())
            val code = pairCode.text.toString().trim()
            val name = deviceName.text.toString().trim()
            if (server == null || !code.matches(Regex("[A-Fa-f0-9]{8}")) || name.isEmpty() || name.length > 80) {
                pairStatus.text = "Enter a valid server, 8-character pairing code and device name."
                return@setOnClickListener
            }
            pairButton.isEnabled = false
            val payload = JSONObject().put("code", code).put("name", name)
            val req = Request.Builder().url("${server.removeSuffix("/")}/api/devices/pair")
                .header("X-Sentinel-Request", "1")
                .post(payload.toString().toRequestBody("application/json".toMediaType())).build()
            okHttp.newCall(req).enqueue(object : Callback {
                override fun onFailure(call: Call, e: IOException) {
                    runOnUiThread { pairButton.isEnabled = true; pairStatus.text = "Cannot reach server. Request a new code if needed." }
                }
                override fun onResponse(call: Call, response: Response) {
                    val message = response.use {
                        try {
                            if (!it.isSuccessful) {
                                if (it.code == 429) "Too many attempts — retry in 60 seconds." else "Invalid or expired code. Generate a new code in Dashboard."
                            } else {
                                val body = JSONObject(it.body?.string() ?: "{}")
                                DeviceCredentials.save(applicationContext, server, body.getString("device_token"))
                                prefs.edit().putString("deviceName", name).apply()
                                "Paired. Tap Save to use this server."
                            }
                        } catch (_: Exception) { "Could not save credentials. Generate a new pairing code and retry." }
                    }
                    runOnUiThread { pairButton.isEnabled = true; pairCode.text.clear(); pairStatus.text = message }
                }
            })
        }

        btnTest.setOnClickListener {
            val input = addrInput.text.toString().trim()
            val baseUrl = NetworkDiscover.inputToBaseUrlOrNull(input)
            if (baseUrl == null) {
                Toast.makeText(this, "Invalid format. Please enter IP or IP:port.", Toast.LENGTH_LONG).show()
                return@setOnClickListener
            }
            verifyPing(baseUrl) { ok ->
                runOnUiThread {
                    Toast.makeText(
                        this,
                        if (ok) "Connected" else "Still failed. Make sure your phone and PC are on the same network.",
                        Toast.LENGTH_LONG
                    ).show()
                }
            }
        }

        btnSave.setOnClickListener {
            val input = addrInput.text.toString().trim()
            val baseUrl = NetworkDiscover.inputToBaseUrlOrNull(input)
            if (baseUrl == null) {
                Toast.makeText(this, "Invalid format. Please enter IP or IP:port.", Toast.LENGTH_LONG).show()
                return@setOnClickListener
            }
            prefs.edit()
                .putString("serverInput", input)
                .putString("baseUrl", baseUrl)
                .putBoolean("showDebug", swDebug.isChecked)
                .putBoolean("hidePreview", swHide.isChecked)
                .putBoolean("stopCamera", swStop.isChecked)
                .putString("imageQualityLabel", spinnerQuality.selectedItem.toString())
                .putString("uploadRateLabel", spinnerUploadRate.selectedItem.toString())
                .putString("resolutionLabel", spinnerResolution.selectedItem.toString())
                .apply()

            setResult(Activity.RESULT_OK)
            finish()
        }
    }

    private fun verifyPing(baseUrl: String, cb: (Boolean) -> Unit) {
        val req = try {
            Request.Builder()
                .url("${baseUrl.removeSuffix("/")}/ping")
                .get()
                .build()
        } catch (_: IllegalArgumentException) {
            cb(false)
            return
        }

        okHttp.newCall(req).enqueue(object : Callback {
            override fun onFailure(call: Call, e: IOException) = cb(false)
            override fun onResponse(call: Call, response: Response) {
                response.use { cb(it.isSuccessful) }
            }
        })
    }
}
