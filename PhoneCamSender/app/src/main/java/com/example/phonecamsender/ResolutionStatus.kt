package com.example.phonecamsender

/** Reports observed frame dimensions, never the camera's requested fallback size. */
class ResolutionStatus {
    private var generation = 0
    private var preference: String? = null
    private var frameSize: String? = null
    private var stopped = false

    @Synchronized fun start(label: String): Int {
        preference = label
        frameSize = null
        stopped = false
        return ++generation
    }

    @Synchronized fun record(ticket: Int, width: Int, height: Int) {
        if (ticket != generation || stopped || width <= 0 || height <= 0) return
        frameSize = "${width}x${height}"
    }

    @Synchronized fun stop() {
        generation++
        frameSize = null
        stopped = true
    }

    @Synchronized fun summary(selectedPreference: String): String {
        val observed = when {
            stopped -> "camera stopped"
            preference != selectedPreference || frameSize == null -> "waiting for frame"
            else -> frameSize
        }
        return "Resolution preference: $selectedPreference\nFrame size: $observed"
    }
}
