package com.example.phonecamsender

import okhttp3.Call
import okhttp3.Connection
import okhttp3.EventListener
import okhttp3.OkHttpClient
import okhttp3.Protocol
import okhttp3.Response
import java.io.IOException
import java.net.InetSocketAddress
import java.net.Proxy
import java.util.UUID
import java.util.concurrent.TimeUnit

/** Only timings and an opaque correlation ID; never retain headers, URLs or credentials. */
class UploadTrace(val bytes: Int, private val clock: () -> Long = { System.nanoTime() / 1_000_000 }) : EventListener() {
    val id: String = UUID.randomUUID().toString().replace("-", "").take(12)
    private val started = clock()
    private var phase = "queued"
    private var phaseStarted = started
    private var ended: Long? = null
    private var failed = false
    private var serverMs: String = "unknown"

    @Synchronized private fun move(next: String) {
        if (ended != null) return
        phase = next
        phaseStarted = clock()
    }
    @Synchronized private fun finish(error: Boolean) {
        if (ended == null) { ended = clock(); failed = error }
    }
    @Synchronized fun elapsedMs(): Long = (ended ?: clock()) - started
    @Synchronized fun summary(): String {
        val now = ended ?: clock()
        return "ID: $id | JPEG: $bytes B\n" +
            "Network: $phase${if (failed) " (failed)" else ""} ${now - phaseStarted}ms | total ${now - started}ms\n" +
            "Server processing: ${serverMs}ms"
    }
    override fun dnsStart(call: Call, domainName: String) = move("DNS")
    override fun connectStart(call: Call, inetSocketAddress: InetSocketAddress, proxy: Proxy) = move("connecting")
    override fun connectEnd(call: Call, inetSocketAddress: InetSocketAddress, proxy: Proxy, protocol: Protocol?) = move("connected")
    override fun connectionAcquired(call: Call, connection: Connection) = move("connected")
    override fun requestHeadersStart(call: Call) = move("sending headers")
    override fun requestBodyStart(call: Call) = move("sending image")
    override fun requestBodyEnd(call: Call, byteCount: Long) = move("waiting response")
    override fun responseHeadersEnd(call: Call, response: Response) {
        synchronized(this) {
            serverMs = response.header("X-Sentinel-Upload-Ms")
                ?.takeIf { it.matches(Regex("[0-9]{1,8}(\\.[0-9]{1,3})?")) } ?: "unknown"
        }
        move("response received")
    }
    override fun callEnd(call: Call) = finish(false)
    override fun callFailed(call: Call, ioe: IOException) = finish(true)
}

object UploadHttp {
    const val CALL_TIMEOUT_MS = 5000L
    fun client(): OkHttpClient = OkHttpClient.Builder()
        .followRedirects(false).followSslRedirects(false)
        // An old frame is expendable; do not replay it on a recovered connection.
        .retryOnConnectionFailure(false)
        .connectTimeout(3, TimeUnit.SECONDS)
        .writeTimeout(4, TimeUnit.SECONDS)
        .readTimeout(4, TimeUnit.SECONDS)
        .callTimeout(CALL_TIMEOUT_MS, TimeUnit.MILLISECONDS)
        .eventListenerFactory { it.request().tag(UploadTrace::class.java) ?: EventListener.NONE }
        .build()
}
