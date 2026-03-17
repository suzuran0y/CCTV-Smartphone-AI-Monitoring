package com.example.phonecamsender

import android.app.Activity
import android.os.Bundle
import android.widget.*
import androidx.appcompat.app.AppCompatActivity
import okhttp3.*
import java.io.IOException

class SettingsActivity : AppCompatActivity() {

    private val prefs by lazy { getSharedPreferences("phonecam", MODE_PRIVATE) }
    private val okHttp = OkHttpClient()

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_settings)

        val addrInput = findViewById<EditText>(R.id.addrInput)
        val btnDiscover = findViewById<Button>(R.id.btnDiscover)
        val btnTest = findViewById<Button>(R.id.btnTest)
        val btnSave = findViewById<Button>(R.id.btnSave)
        val swDebug = findViewById<Switch>(R.id.switchShowDebug)
        val swHide = findViewById<Switch>(R.id.switchHidePreview)
        val swStop = findViewById<Switch>(R.id.switchStopCamera)
        val spinnerQuality = findViewById<Spinner>(R.id.spinnerImageQuality)
        val spinnerUploadRate = findViewById<Spinner>(R.id.spinnerUploadRate)
        val spinnerResolution = findViewById<Spinner>(R.id.spinnerResolution)

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
        btnDiscover.setOnClickListener {
            Toast.makeText(this, "Discovering...", Toast.LENGTH_SHORT).show()
            NetworkDiscover.discoverServer(
                onFound = { baseUrl ->
                    runOnUiThread {
                        addrInput.setText(NetworkDiscover.baseUrlToInput(baseUrl))
                        Toast.makeText(this, "Found: ${addrInput.text}", Toast.LENGTH_SHORT).show()
                    }
                },
                onFail = {
                    runOnUiThread {
                        Toast.makeText(this, "Discovery failed. Check that both devices are on the same network.", Toast.LENGTH_LONG).show()
                    }
                }
            )
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
        val req = Request.Builder()
            .url("${baseUrl.removeSuffix("/")}/ping")
            .get()
            .build()

        okHttp.newCall(req).enqueue(object : Callback {
            override fun onFailure(call: Call, e: IOException) = cb(false)
            override fun onResponse(call: Call, response: Response) {
                response.use { cb(it.isSuccessful) }
            }
        })
    }
}
