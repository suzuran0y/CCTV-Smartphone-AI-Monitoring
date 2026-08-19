package com.example.phonecamsender
import android.Manifest
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Bundle
import android.util.Size
import android.widget.TextView
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import androidx.camera.core.*
import androidx.camera.lifecycle.ProcessCameraProvider
import androidx.camera.view.PreviewView
import androidx.core.app.ActivityCompat
import androidx.core.content.ContextCompat
import okhttp3.*
import java.io.IOException
import java.util.concurrent.Executors
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicBoolean
import java.util.concurrent.atomic.AtomicLong
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.RequestBody.Companion.toRequestBody
import android.widget.ImageButton
import android.view.View

class MainActivity : AppCompatActivity() {
    private lateinit var blackScreen: View
    private lateinit var previewView: PreviewView
    private lateinit var statusText: TextView
    private val cameraExecutor = Executors.newSingleThreadExecutor()
    private val okHttp = OkHttpClient.Builder()
        .connectTimeout(5, TimeUnit.SECONDS)
        .writeTimeout(10, TimeUnit.SECONDS)
        .readTimeout(10, TimeUnit.SECONDS)
        .build()
    private val prefs by lazy { getSharedPreferences("phonecam", MODE_PRIVATE) }
    private var baseUrl: String? = null
    private var lastSentTs = 0L
    private val uploadInFlight = AtomicBoolean(false)
    private val uploadSuccessCount = AtomicLong(0)
    private val uploadFailureCount = AtomicLong(0)
    private val uploadDroppedCount = AtomicLong(0)

    @Volatile
    private var lastUploadStatus = "Not started"

    @Volatile
    private var lastUploadLatencyMs = 0L

    @Volatile
    private var lastCameraError = ""

    private var lastAppliedResolutionLabel: String? = null

// ===== Debug / Power control state =====
    private var dbgEnabledFlag = false
    private var powerSaveFlag = false
    // ===== CameraX provider control =====
    private var camProviderRef: ProcessCameraProvider? = null
    private var camRunningFlag = false
    // ===== Debug UI updater =====
    private val mainHandler = android.os.Handler(android.os.Looper.getMainLooper())
    private val debugUpdater = object : Runnable {
        override fun run() {
            if (dbgEnabledFlag) {
                overlayText.text = generateDebugText()
                overlayText.visibility = android.view.View.VISIBLE
                mainHandler.postDelayed(this, 500)
            } else {
                overlayText.visibility = android.view.View.GONE
            }
        }
    }
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)
        overlayText = findViewById(R.id.overlayText)
        previewView = findViewById(R.id.previewView)
        statusText = findViewById(R.id.statusText)
        blackScreen = findViewById(R.id.blackScreen)

        setStatus("Status: Connecting...")
        findViewById<ImageButton>(R.id.btnSettings).setOnClickListener {
            startActivityForResult(Intent(this, SettingsActivity::class.java), 2001)
        }
        connectAndStart()
    }
    override fun onResume() {
        super.onResume()
        applySettingsFromPrefs()
    }
    private fun applySettingsFromPrefs() {
        dbgEnabledFlag = prefs.getBoolean("showDebug", false)

        val hidePreviewFlag = prefs.getBoolean("hidePreview", true)
        val stopCameraFlag = prefs.getBoolean("stopCamera", false)
        val currentResolutionLabel = getResolutionLabel()
        val resolutionChanged = currentResolutionLabel != lastAppliedResolutionLabel

        powerSaveFlag = stopCameraFlag
        mainHandler.removeCallbacks(debugUpdater)
        mainHandler.post(debugUpdater)

        if (stopCameraFlag) {
            stopCameraEngine()
            previewView.visibility = View.GONE
            blackScreen.visibility = View.VISIBLE
            setStatus("Status: Camera stopped")
            lastAppliedResolutionLabel = currentResolutionLabel
            return
        }

        if (!camRunningFlag || resolutionChanged) {
            if (!hasCameraPermission()) {
                setStatus("Status: Camera permission required")
                lastAppliedResolutionLabel = currentResolutionLabel
                return
            }
            stopCameraEngine()
            startCamera()
            lastAppliedResolutionLabel = currentResolutionLabel
        }

        if (hidePreviewFlag) {
            previewView.visibility = View.GONE
            blackScreen.visibility = View.VISIBLE
            setStatus("Status: Preview hidden")
        } else {
            previewView.visibility = View.VISIBLE
            blackScreen.visibility = View.GONE

            val url = baseUrl
            if (url == null) setStatus("Status: Not connected")
            else setStatus("Status: Connected ${NetworkDiscover.baseUrlToInput(url)}")
        }
    }

    // ==========================
    // Connection process
    // ==========================
    private fun connectAndStart() {
        val savedBaseUrl = prefs.getString("baseUrl", null)

        if (!savedBaseUrl.isNullOrBlank()) {
            setStatus("Status: Testing saved connection...")
            verifyPing(savedBaseUrl) { ok ->
                if (ok) {
                    onServerReady(savedBaseUrl)
                } else {
                    setStatus("Status: Saved server unavailable")
                    showManualInputDialog()
                }
            }
        } else {
            setStatus("Status: Server address required")
            showManualInputDialog()
        }
    }

    private fun onServerReady(url: String) {
        baseUrl = url
        prefs.edit().putString("baseUrl", url).apply()

        runOnUiThread {
            setStatus("Status: Connected ${NetworkDiscover.baseUrlToInput(url)}")
            Toast.makeText(this, "Connected", Toast.LENGTH_SHORT).show()

            if (hasCameraPermission()) {
                if (!camRunningFlag) startCamera()
            } else {
                ActivityCompat.requestPermissions(
                    this,
                    arrayOf(Manifest.permission.CAMERA),
                    1001
                )
            }
        }
    }

    // ==========================
    // Manual input pop-up window
    // ==========================

    private fun showManualInputDialog() {
        runOnUiThread {
            val input = android.widget.EditText(this)
            input.hint = "e.g. 192.168.1.10:8000"
            input.setText(prefs.getString("serverInput", "") ?: "")

            androidx.appcompat.app.AlertDialog.Builder(this)
                .setTitle("Enter Sentinel server address")
                .setMessage("Run server.py on the PC, then enter the CamFlow address shown in its startup output.")
                .setView(input)
                .setCancelable(false)
                .setPositiveButton("Connect") { _, _ ->
                    val text = input.text.toString().trim()
                    val normalized = NetworkDiscover.inputToBaseUrlOrNull(text)

                    if (normalized == null) {
                        Toast.makeText(
                            this,
                            "Invalid format. Please enter IP or IP:port.",
                            Toast.LENGTH_LONG
                        ).show()
                        showManualInputDialog()
                        return@setPositiveButton
                    }

                    verifyPing(normalized) { ok ->
                        if (ok) {
                            prefs.edit()
                                .putString("serverInput", text)
                                .putString("baseUrl", normalized)
                                .apply()

                            onServerReady(normalized)
                        } else {
                            setStatus("Status: Connection failed")
                            Toast.makeText(
                                this,
                                "Still failed. Make sure your phone and PC are on the same network.",
                                Toast.LENGTH_LONG
                            ).show()
                        }
                    }
                }
                .show()
        }
    }

    // ==========================
    // Network testing
    // ==========================

    private fun verifyPing(url: String, callback: (Boolean) -> Unit) {
        val request = try {
            Request.Builder()
                .url("${url.removeSuffix("/")}/ping")
                .get()
                .build()
        } catch (_: IllegalArgumentException) {
            callback(false)
            return
        }

        okHttp.newCall(request).enqueue(object : Callback {
            override fun onFailure(call: Call, e: IOException) {
                callback(false)
            }
            override fun onResponse(call: Call, response: Response) {
                response.use {
                    callback(it.isSuccessful)
                }
            }
        })
    }

    // ==========================
    // Camera
    // ==========================

    private fun hasCameraPermission(): Boolean =
        ContextCompat.checkSelfPermission(
            this,
            Manifest.permission.CAMERA
        ) == PackageManager.PERMISSION_GRANTED

    override fun onRequestPermissionsResult(
        requestCode: Int,
        permissions: Array<out String>,
        grantResults: IntArray
    ) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults)

        if (requestCode == 1001) {
            val granted = grantResults.isNotEmpty() &&
                    grantResults[0] == PackageManager.PERMISSION_GRANTED
            if (granted) {
                startCamera()
            } else {
                Toast.makeText(this, "Camera permission denied", Toast.LENGTH_LONG).show()
            }
        }
    }

    private fun startCamera() {
        val cameraProviderFuture = ProcessCameraProvider.getInstance(this)

        cameraProviderFuture.addListener({
            try {
                val cameraProvider = cameraProviderFuture.get()
                camProviderRef = cameraProvider

                val preview = Preview.Builder().build().also {
                    it.setSurfaceProvider(previewView.surfaceProvider)
                }

                val analysis = ImageAnalysis.Builder()
                    .setBackpressureStrategy(ImageAnalysis.STRATEGY_KEEP_ONLY_LATEST)
                    .setTargetResolution(getTargetResolutionSize())
                    .build()

                analysis.setAnalyzer(cameraExecutor) { imageProxy ->

                    if (powerSaveFlag) {
                        imageProxy.close()
                        return@setAnalyzer
                    }

                    try {
                        val now = System.currentTimeMillis()
                        val uploadIntervalMs = getUploadIntervalMs()

                        if (now - lastSentTs >= uploadIntervalMs) {
                            lastSentTs = now
                            val jpegQuality = getImageQualityValue()
                            val jpeg = ImageUtil.yuvToJpeg(imageProxy, jpegQuality)
                            uploadFrame(jpeg)
                        }
                    } catch (e: Exception) {
                        lastCameraError = e.javaClass.simpleName
                    } finally {
                        imageProxy.close()
                    }
                }

                cameraProvider.unbindAll()
                cameraProvider.bindToLifecycle(
                    this,
                    CameraSelector.DEFAULT_BACK_CAMERA,
                    preview,
                    analysis
                )

                camRunningFlag = true
                lastCameraError = ""
                val url = baseUrl
                if (url != null) {
                    setStatus("Status: Connected ${NetworkDiscover.baseUrlToInput(url)}")
                } else {
                    setStatus("Status: Not connected")
                }
            } catch (e: Exception) {
                camRunningFlag = false
                lastCameraError = e.javaClass.simpleName
                setStatus("Status: Camera unavailable")
            }

        }, ContextCompat.getMainExecutor(this))
    }

    private fun uploadFrame(jpegBytes: ByteArray) {
        val url = baseUrl ?: return
        if (!uploadInFlight.compareAndSet(false, true)) {
            uploadDroppedCount.incrementAndGet()
            return
        }

        val startedAt = System.currentTimeMillis()
        val uploadUrl = "${url.removeSuffix("/")}/upload"

        val body = MultipartBody.Builder()
            .setType(MultipartBody.FORM)
            .addFormDataPart(
                "image",
                "frame.jpg",
                jpegBytes.toRequestBody("image/jpeg".toMediaType())
            )
            .build()

        val request = try {
            Request.Builder()
                .url(uploadUrl)
                .post(body)
                .build()
        } catch (_: IllegalArgumentException) {
            uploadFailureCount.incrementAndGet()
            lastUploadStatus = "Invalid server URL"
            uploadInFlight.set(false)
            return
        }

        okHttp.newCall(request).enqueue(object : Callback {
            override fun onFailure(call: Call, e: IOException) {
                lastUploadLatencyMs = System.currentTimeMillis() - startedAt
                uploadFailureCount.incrementAndGet()
                lastUploadStatus = "Failed: ${e.javaClass.simpleName}"
                uploadInFlight.set(false)
            }

            override fun onResponse(call: Call, response: Response) {
                try {
                    lastUploadLatencyMs = System.currentTimeMillis() - startedAt
                    if (response.isSuccessful) {
                        uploadSuccessCount.incrementAndGet()
                        lastUploadStatus = "OK (${response.code})"
                    } else {
                        uploadFailureCount.incrementAndGet()
                        lastUploadStatus = "HTTP ${response.code}"
                    }
                } finally {
                    response.close()
                    uploadInFlight.set(false)
                }
            }
        })
    }

    private lateinit var overlayText: TextView

    private fun setStatus(text: String) {
        runOnUiThread { statusText.text = text }
    }
    private fun stopCameraEngine() {
        camProviderRef?.unbindAll()
        camRunningFlag = false
    }
    override fun onPause() {
        super.onPause()
        mainHandler.removeCallbacks(debugUpdater)
    }
    override fun onDestroy() {
        super.onDestroy()
        mainHandler.removeCallbacks(debugUpdater)
        stopCameraEngine()
        cameraExecutor.shutdown()
    }
    override fun onActivityResult(requestCode: Int, resultCode: Int, data: Intent?) {
        super.onActivityResult(requestCode, resultCode, data)
        if (requestCode == 2001) {
            applySettingsFromPrefs()
        }
    }
    private fun generateDebugText(): String {
        val url = baseUrl?.let { NetworkDiscover.baseUrlToInput(it) } ?: "Not connected"
        val hidePreviewFlag = prefs.getBoolean("hidePreview", false)
        val stopCameraFlag = prefs.getBoolean("stopCamera", false)

        val qualityLabel = getImageQualityLabel()
        val qualityValue = getImageQualityValue()

        val uploadRateLabel = getUploadRateLabel()
        val uploadIntervalMs = getUploadIntervalMs()

        val resolutionText = getResolutionText()

        val mode = when {
            stopCameraFlag -> "Camera stopped"
            hidePreviewFlag -> "Preview hidden"
            else -> "Normal"
        }

        val cameraErrorText = if (lastCameraError.isBlank()) "none" else lastCameraError
        return "Server: $url\nMode: $mode\nResolution: $resolutionText\n" +
                "Upload rate: $uploadRateLabel (${uploadIntervalMs}ms)\n" +
                "Quality: $qualityLabel ($qualityValue)\n" +
                "Upload status: $lastUploadStatus (${lastUploadLatencyMs}ms)\n" +
                "Uploads: ok=${uploadSuccessCount.get()} failed=${uploadFailureCount.get()} " +
                "dropped=${uploadDroppedCount.get()}\nCamera error: $cameraErrorText"
    }

    private fun getImageQualityLabel(): String {
        return prefs.getString("imageQualityLabel", "Medium") ?: "Medium"
    }

    private fun getImageQualityValue(): Int {
        return when (getImageQualityLabel()) {
            "Low" -> 35
            "High" -> 75
            else -> 55
        }
    }

    private fun getUploadRateLabel(): String {
        return prefs.getString("uploadRateLabel", "High") ?: "High"
    }

    private fun getUploadIntervalMs(): Long {
        return when (getUploadRateLabel()) {
            "Low" -> 500L
            "Medium" -> 250L
            else -> 120L
        }
    }

    private fun getResolutionLabel(): String {
        return prefs.getString("resolutionLabel", "Medium") ?: "Medium"
    }

    private fun getTargetResolutionSize(): Size {
        return when (getResolutionLabel()) {
            "Low" -> Size(320, 240)
            "High" -> Size(1280, 960)
            else -> Size(640, 480)
        }
    }

    private fun getResolutionText(): String {
        val size = getTargetResolutionSize()
        return "${getResolutionLabel()} (${size.width}x${size.height})"
    }
}
