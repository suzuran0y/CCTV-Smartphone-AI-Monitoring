package com.example.phonecamsender

import org.junit.Assert.*
import org.junit.Test

class CameraStartGuardTest {
    @Test fun duplicateStartAndStaleCallbackAreIgnored() {
        val guard = CameraStartGuard()
        val first = guard.begin()!!
        assertNull(guard.begin())
        guard.stop()
        val second = guard.begin()!!
        assertFalse(guard.isCurrent(first))
        guard.complete(first, true)
        assertFalse(guard.running)
        guard.complete(second, true)
        assertTrue(guard.running)
        assertNull(guard.begin())
    }

    @Test fun failureCanRestartAndStopInvalidatesRunningCamera() {
        val guard = CameraStartGuard()
        guard.complete(guard.begin()!!, false)
        val retry = guard.begin()!!
        guard.complete(retry, true)
        guard.stop()
        assertFalse(guard.running)
        assertNotNull(guard.begin())
    }
}
