package com.example.phonecamsender

import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import org.junit.Assert.*
import org.junit.Test
import java.io.IOException
import java.net.ServerSocket
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit
import kotlin.concurrent.thread

class UploadDiagnosticsTest {
    @Test fun configurationBoundsWholeUploadAndDoesNotReplayFrames() {
        val client = UploadHttp.client()
        assertEquals(5000, client.callTimeoutMillis)
        assertFalse(client.retryOnConnectionFailure)
        assertFalse(client.followRedirects)
        assertFalse(client.followSslRedirects)
    }

    @Test fun traceFreezesFailureStageAndDoesNotExposeCredentials() {
        var now = 100L
        val trace = UploadTrace(123) { now }
        val call = UploadHttp.client().newCall(Request.Builder().url("http://localhost/").header("Authorization", "secret-token").build())
        trace.requestBodyEnd(call, 123)
        now = 650L
        trace.callFailed(call, IOException("secret-message"))
        now = 900L
        assertEquals(550L, trace.elapsedMs())
        assertTrue(trace.summary().contains("waiting response (failed) 550ms"))
        assertFalse(trace.summary().contains("secret"))
        assertTrue(trace.id.matches(Regex("[a-f0-9]{12}")))
    }

    @Test fun stalledResponseTimesOutAndNextUploadSucceeds() {
        val client = UploadHttp.client().newBuilder().callTimeout(250, TimeUnit.MILLISECONDS).build()
        ServerSocket(0).use { server ->
            val release = CountDownLatch(1)
            val worker = thread(isDaemon = true) {
                server.accept().use { socket ->
                    val reader = socket.getInputStream().bufferedReader()
                    while (!reader.readLine().isNullOrEmpty()) { /* consume headers */ }
                    release.await(2, TimeUnit.SECONDS) // Deliberately no response.
                }
            }
            val trace = UploadTrace(1)
            val req = Request.Builder().url("http://127.0.0.1:${server.localPort}/upload")
                .tag(UploadTrace::class.java, trace).post(byteArrayOf(1).toRequestBody()).build()
            try {
                client.newCall(req).execute().use { fail("Expected a whole-call timeout") }
            } catch (_: IOException) {
                assertTrue(trace.elapsedMs() < 2000)
                assertTrue(trace.summary().contains("failed"))
            } finally {
                release.countDown()
                worker.join(2500)
            }
            val responder = thread(isDaemon = true) {
                server.accept().use { socket ->
                    val reader = socket.getInputStream().bufferedReader()
                    while (!reader.readLine().isNullOrEmpty()) { }
                    socket.getOutputStream().write("HTTP/1.1 200 OK\r\nContent-Length: 2\r\nX-Sentinel-Upload-Ms: 12.3\r\nConnection: close\r\n\r\nOK".toByteArray())
                }
            }
            val next = UploadTrace(1)
            client.newCall(req.newBuilder().tag(UploadTrace::class.java, next).build()).execute().use {
                assertEquals(200, it.code)
                assertEquals("OK", it.body!!.string())
            }
            responder.join(2500)
            assertTrue(next.summary().contains("Server processing: 12.3ms"))
        }
    }
}
