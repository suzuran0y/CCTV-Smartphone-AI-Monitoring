package com.example.phonecamsender

import androidx.test.platform.app.InstrumentationRegistry
import androidx.test.ext.junit.runners.AndroidJUnit4
import org.junit.Assert.*
import org.junit.Test
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class DeviceCredentialsTest {
    @Test fun encryptedRoundTripIsServerBoundAndRevocable() {
        // This test clears credentials: run only on a dedicated test emulator/device.
        val context = InstrumentationRegistry.getInstrumentation().targetContext
        val server = "http://127.0.0.1:8765"
        val token = "instrumentation-test-token-00000000000001"
        try {
            DeviceCredentials.save(context, server, token)
            assertEquals(token, DeviceCredentials.tokenFor(context, server))
            assertNull(DeviceCredentials.tokenFor(context, "http://127.0.0.1:9999"))
            val saved = java.io.File(context.noBackupFilesDir, "device-credentials.json").readText()
            assertFalse(saved.contains(token))
            DeviceCredentials.clearIfCurrent(context, server, "old-token")
            assertEquals(token, DeviceCredentials.tokenFor(context, server))
            DeviceCredentials.clearIfCurrent(context, server, token)
            assertNull(DeviceCredentials.tokenFor(context, server))
        } finally {
            DeviceCredentials.clear(context)
        }
    }
}
