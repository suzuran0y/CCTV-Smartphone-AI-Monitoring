package com.example.phonecamsender
import android.Manifest
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Bundle
import android.os.SystemClock
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
import java.util.concurrent.ConcurrentHashMap
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
        .followRedirects(false)
        .followSslRedirects(false)
        .connectTimeout(5, TimeUnit.SECONDS)
        .writeTimeout(10, TimeUnit.SECONDS)
        .readTimeout(10, TimeUnit.SECONDS)
        .build()
    private val prefs by lazy { getSharedPreferences("phonecam", MODE_PRIVATE) }
    private val uploadHttp = UploadHttp.client()
    private val activeUploads = ConcurrentHashMap<Call, UploadTrace>()
    private val uploadSlots = UploadSlots(2)
    @Volatile private var uploadsStopped = false
    private data class UploadResult(val status: String, val latencyMs: Long, val trace: UploadTrace?)
    @Volatile private var lastUpload = UploadResult("Not started", 0, null)
    @Volatile private var lastEncodeMs = 0L
    private val resolutionStatus = ResolutionStatus()
    @Volatile
    private var baseUrl: String? = null
    private var lastSentTs = 0L
    private var lastSuccessPersisted = 0L
    private val uploadSuccessCount = AtomicLong(0)
    private val uploadFailureCount = AtomicLong(0)
    private val uploadDroppedCount = AtomicLong(0)

    @Volatile
    private var lastCameraError = ""

    private var lastAppliedResolutionLabel: String? = null

// ===== Debug / Power control state =====
    private var dbgEnabledFlag = false
    @Volatile private var powerSaveFlag = false
    // ===== CameraX provider control =====
    private var camProviderRef: ProcessCameraProvider? = null
    private val cameraStart = CameraStartGuard()
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
            startActivity(Intent(this, SettingsActivity::class.java))
        }
        connectAndStart()
    }
    override fun onResume() {
        super.onResume()
        applySettingsFromPrefs()
    }
    private fun applySettingsFromPrefs() {
        baseUrl = prefs.getString("baseUrl", null)
        dbgEnabledFlag = prefs.getBoolean("showDebug", false)

        val hidePreviewFlag = prefs.getBoolean("hidePreview", false)
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

        if (!cameraStart.running || resolutionChanged) {
            if (!hasCameraPermission()) {
                setStatus("Status: Camera permission required")
                lastAppliedResolutionLabel = currentResolutionLabel
                return
            }
            if (resolutionChanged) stopCameraEngine()
            startCamera()
            lastAppliedResolutionLabel = currentResolutionLabel
        }

        if (hidePreviewFlag) {
            // Keep the CameraX preview surface alive; the opaque overlay hides it.
            previewView.visibility = View.VISIBLE
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
                startCamera()
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
        if (isDestroyed || isFinishing || prefs.getBoolean("stopCamera", false)) return
        val ticket = cameraStart.begin() ?: return
        val resolutionTicket = resolutionStatus.start(getResolutionLabel())
        val cameraProviderFuture = ProcessCameraProvider.getInstance(this)

        cameraProviderFuture.addListener({
            if (!cameraStart.isCurrent(ticket) || isDestroyed || isFinishing) return@addListener
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

                    resolutionStatus.record(resolutionTicket, imageProxy.cropRect.width(), imageProxy.cropRect.height())

                    if (powerSaveFlag) {
                        imageProxy.close()
                        return@setAnalyzer
                    }

                    try {
                        val now = SystemClock.elapsedRealtime()
                        val uploadIntervalMs = getUploadIntervalMs()

                        if (now - lastSentTs >= uploadIntervalMs) {
                            lastSentTs = now
                            // Check before YUV conversion/JPEG compression, not after doing wasted work.
                            val slot = uploadSlots.tryAcquire()
                            if (slot == null) {
                                uploadDroppedCount.incrementAndGet()
                                return@setAnalyzer
                            }
                            try {
                                val jpegQuality = getImageQualityValue()
                                val encodeStarted = SystemClock.elapsedRealtime()
                                val jpeg = ImageUtil.yuvToJpeg(imageProxy, jpegQuality)
                                lastEncodeMs = SystemClock.elapsedRealtime() - encodeStarted
                                uploadFrame(jpeg, slot)
                            } catch (e: Exception) {
                                slot.close()
                                throw e
                            }
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

                cameraStart.complete(ticket, true)
                lastCameraError = ""
                val url = baseUrl
                if (url != null) {
                    setStatus("Status: Connected ${NetworkDiscover.baseUrlToInput(url)}")
                } else {
                    setStatus("Status: Not connected")
                }
            } catch (e: Exception) {
                cameraStart.complete(ticket, false)
                resolutionStatus.stop()
                lastCameraError = e.javaClass.simpleName
                setStatus("Status: Camera unavailable")
            }

        }, ContextCompat.getMainExecutor(this))
    }

    private fun uploadFrame(jpegBytes: ByteArray, slot: UploadSlots.Lease) {
        val url = baseUrl
        if (url == null || uploadsStopped) { slot.close(); return }
        val token = DeviceCredentials.tokenFor(applicationContext, url)
        if (token == null) {
            lastUpload = UploadResult("Pairing required — open Settings", 0, null)
            setStatus("Status: Pairing required — open Settings")
            slot.close()
            return
        }

        val trace = UploadTrace(jpegBytes.size)
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
                .header("Authorization", "Bearer $token")
                .header("X-CamFlow-Upload-ID", trace.id)
                .tag(UploadTrace::class.java, trace)
                .post(body)
                .build()
        } catch (_: IllegalArgumentException) {
            uploadFailureCount.incrementAndGet()
            lastUpload = UploadResult("Invalid server URL", 0, null)
            slot.close()
            return
        }

        val uploadCall = uploadHttp.newCall(request)
        activeUploads[uploadCall] = trace
        // Covers destruction between reserving a slot and registering the call.
        if (uploadsStopped) uploadCall.cancel()
        try {
            uploadCall.enqueue(object : Callback {
                override fun onFailure(call: Call, e: IOException) {
                    uploadFailureCount.incrementAndGet()
                    lastUpload = UploadResult("Failed: ${e.javaClass.simpleName}", trace.elapsedMs(), trace)
                    activeUploads.remove(call)
                    slot.close()
                }

                override fun onResponse(call: Call, response: Response) {
                    try {
                        if (response.isSuccessful) {
                            uploadSuccessCount.incrementAndGet()
                            lastUpload = UploadResult("OK (${response.code})", trace.elapsedMs(), trace)
                            persistUploadSuccess()
                        } else {
                            uploadFailureCount.incrementAndGet()
                            val status = when (response.code) {
                                401, 403 -> "Pairing revoked or invalid — pair again in Settings"
                                503 -> "Ingest disabled — ask administrator to enable it"
                                else -> "HTTP ${response.code}"
                            }
                            lastUpload = UploadResult(status, trace.elapsedMs(), trace)
                            if (response.code == 401 || response.code == 403) {
                                DeviceCredentials.clearIfCurrent(applicationContext, url, token)
                                setStatus("Status: Pairing required — open Settings")
                            }
                        }
                    } finally {
                        try { response.close() } finally {
                            activeUploads.remove(call)
                            slot.close()
                        }
                    }
                }
            })
        } catch (e: Exception) {
            activeUploads.remove(uploadCall)
            slot.close()
            throw e
        }
    }

    @Synchronized private fun persistUploadSuccess() {
        val now = System.currentTimeMillis()
        if (now - lastSuccessPersisted >= 10000) {
            lastSuccessPersisted = now
            prefs.edit().putLong("lastUploadSuccess", now).apply()
        }
    }

    private lateinit var overlayText: TextView

    private fun setStatus(text: String) {
        runOnUiThread { statusText.text = text }
    }
    private fun stopCameraEngine() {
        cameraStart.stop()
        resolutionStatus.stop()
        camProviderRef?.unbindAll()
    }
    override fun onPause() {
        super.onPause()
        mainHandler.removeCallbacks(debugUpdater)
    }
    override fun onDestroy() {
        super.onDestroy()
        mainHandler.removeCallbacks(debugUpdater)
        stopCameraEngine()
        uploadsStopped = true
        uploadSlots.stopAccepting()
        activeUploads.keys.forEach { it.cancel() }
        cameraExecutor.shutdown()
    }
    private fun generateDebugText(): String {
        val url = baseUrl?.let { NetworkDiscover.baseUrlToInput(it) } ?: "Not connected"
        val hidePreviewFlag = prefs.getBoolean("hidePreview", false)
        val stopCameraFlag = prefs.getBoolean("stopCamera", false)

        val qualityLabel = getImageQualityLabel()
        val qualityValue = getImageQualityValue()

        val uploadRateLabel = getUploadRateLabel()
        val uploadIntervalMs = getUploadIntervalMs()

        val resolutionText = resolutionStatus.summary(getResolutionLabel())

        val mode = when {
            stopCameraFlag -> "Camera stopped"
            hidePreviewFlag -> "Preview hidden"
            else -> "Normal"
        }

        val cameraErrorText = if (lastCameraError.isBlank()) "none" else lastCameraError
        val completed = lastUpload
        val active = activeUploads.values.toList().sortedBy { it.id }
        return "CamFlow ${BuildConfig.VERSION_NAME} build ${BuildConfig.VERSION_CODE}\n" +
                "Server: $url\nMode: $mode\n$resolutionText\n" +
                "Upload rate: $uploadRateLabel (${uploadIntervalMs}ms)\n" +
                "Quality: $qualityLabel ($qualityValue)\n" +
                "Upload status: ${completed.status} (${completed.latencyMs}ms)\n" +
                "Concurrency: ${uploadSlots.count()}/${uploadSlots.limit} (no queue)\n" +
                "Encode: ${lastEncodeMs}ms | limit: ${UploadHttp.CALL_TIMEOUT_MS}ms\n" +
                (completed.trace?.let { "Last completed — ${it.summary()}\n" } ?: "") +
                active.joinToString("") { "Active — ${it.summary()}\n" } +
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

}
