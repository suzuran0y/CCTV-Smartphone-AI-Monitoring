package com.example.phonecamsender

import org.junit.Assert.*
import org.junit.Test

class ResolutionStatusTest {
    @Test fun displaysOnlyObservedDimensionsForEachPreference() {
        val status = ResolutionStatus()
        for (label in listOf("Low", "Medium", "High")) {
            val ticket = status.start(label)
            status.record(ticket, 480, 480)
            assertEquals("Resolution preference: $label\nFrame size: 480x480", status.summary(label))
        }
    }

    @Test fun changingPreferenceClearsOldSizeAndRejectsLateFrames() {
        val status = ResolutionStatus()
        val old = status.start("Low")
        status.record(old, 480, 480)
        assertTrue(status.summary("High").endsWith("waiting for frame"))
        val current = status.start("High")
        status.record(old, 480, 480)
        assertTrue(status.summary("High").endsWith("waiting for frame"))
        status.record(current, 1280, 960)
        assertTrue(status.summary("High").endsWith("1280x960"))
    }

    @Test fun stopClearsDimensionsAndRestartWaitsForNewFrame() {
        val status = ResolutionStatus()
        val old = status.start("Low")
        status.record(old, 480, 480)
        status.stop()
        status.record(old, 480, 480)
        assertTrue(status.summary("Low").endsWith("camera stopped"))
        status.start("Low")
        assertTrue(status.summary("Low").endsWith("waiting for frame"))
    }

    @Test fun unknownAndInvalidSizesAreNotReportedAsMeasurements() {
        val status = ResolutionStatus()
        assertTrue(status.summary("Medium").endsWith("waiting for frame"))
        val ticket = status.start("Medium")
        status.record(ticket, 0, 480)
        status.record(ticket, 640, -1)
        assertTrue(status.summary("Medium").endsWith("waiting for frame"))
    }
}
