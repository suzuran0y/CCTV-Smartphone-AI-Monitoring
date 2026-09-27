package com.example.phonecamsender

import okhttp3.*
import okhttp3.RequestBody.Companion.toRequestBody
import org.junit.Assert.*
import org.junit.Test
import java.io.IOException
import java.net.ServerSocket
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicReference
import kotlin.concurrent.thread

class UploadSlotsTest {
    @Test fun onlyTwoSlotsAndRepeatedReleaseIsSafe() {
        val slots = UploadSlots(2)
        val first = slots.tryAcquire()!!
        val second = slots.tryAcquire()!!
        assertNull(slots.tryAcquire())
        assertEquals(2, slots.count())
        second.close(); second.close()
        assertEquals(1, slots.count())
        val replacement = slots.tryAcquire()!!
        first.close(); replacement.close()
        assertEquals(0, slots.count())
    }

    @Test fun stopRejectsNewWorkAndAllowsOutstandingWorkToRelease() {
        val slots = UploadSlots(2)
        val first = slots.tryAcquire()!!
        slots.stopAccepting()
        assertNull(slots.tryAcquire())
        first.close()
        assertEquals(0, slots.count())
    }

    @Test fun concurrentAcquisitionsNeverExceedLimit() {
        val slots = UploadSlots(2)
        val start = CountDownLatch(1)
        val allAttempted = CountDownLatch(12)
        val release = CountDownLatch(1)
        val workers = (1..12).map {
            thread {
                start.await()
                val lease = slots.tryAcquire()
                allAttempted.countDown()
                release.await(3, TimeUnit.SECONDS)
                lease?.close()
            }
        }
        try {
            start.countDown()
            assertTrue(allAttempted.await(2, TimeUnit.SECONDS))
            assertEquals(2, slots.count())
        } finally { release.countDown(); workers.forEach { it.join(3000) } }
        assertEquals(0, slots.count())
    }

    @Test fun secondUploadCompletesWhileFirstResponseIsStillPending() {
        val slots = UploadSlots(2)
        val client = UploadHttp.client() // Exactly the same timeouts/retry policy as build 7.
        val slowArrived = CountDownLatch(1)
        val releaseSlow = CountDownLatch(1)
        val fastDone = CountDownLatch(1)
        val allDone = CountDownLatch(2)
        val error = AtomicReference<Throwable?>(null)
        ServerSocket(0).use { server ->
            server.soTimeout = 3000
            val responder = thread(isDaemon = true) {
                try {
                    server.accept().use { slow ->
                        slow.soTimeout = 3000
                        val input = slow.getInputStream().bufferedReader()
                        while (!input.readLine().isNullOrEmpty()) { }
                        input.read() // one-byte image placeholder
                        slowArrived.countDown()
                        server.accept().use { fast ->
                            fast.soTimeout = 3000
                            val second = fast.getInputStream().bufferedReader()
                            while (!second.readLine().isNullOrEmpty()) { }
                            second.read()
                            fast.getOutputStream().write("HTTP/1.1 200 OK\r\nContent-Length: 2\r\nConnection: close\r\n\r\nOK".toByteArray())
                        }
                        releaseSlow.await(3, TimeUnit.SECONDS)
                        slow.getOutputStream().write("HTTP/1.1 200 OK\r\nContent-Length: 2\r\nConnection: close\r\n\r\nOK".toByteArray())
                    }
                } catch (e: Throwable) { error.compareAndSet(null, e) }
            }
            fun send(fast: Boolean) {
                val slot = slots.tryAcquire()!!
                val request = Request.Builder().url("http://127.0.0.1:${server.localPort}/upload")
                    .post(byteArrayOf(1).toRequestBody()).build()
                client.newCall(request).enqueue(object : Callback {
                    override fun onFailure(call: Call, e: IOException) {
                        error.compareAndSet(null, e)
                        slot.close(); allDone.countDown()
                        if (fast) fastDone.countDown()
                    }
                    override fun onResponse(call: Call, response: Response) {
                        try { response.use { assertEquals(200, it.code); assertEquals("OK", it.body!!.string()) } }
                        catch (e: Throwable) { error.compareAndSet(null, e) }
                        finally {
                            slot.close(); allDone.countDown()
                            if (fast) fastDone.countDown()
                        }
                    }
                })
            }
            try {
                send(false)
                assertTrue(slowArrived.await(2, TimeUnit.SECONDS))
                send(true)
                assertTrue(fastDone.await(2, TimeUnit.SECONDS))
                assertNull(error.get())
                assertEquals(1, slots.count()) // The first request is still waiting.
            } finally {
                releaseSlow.countDown()
                assertTrue(allDone.await(6, TimeUnit.SECONDS))
                responder.join(3000)
            }
            assertNull(error.get())
            assertEquals(0, slots.count())
        }
    }
}
