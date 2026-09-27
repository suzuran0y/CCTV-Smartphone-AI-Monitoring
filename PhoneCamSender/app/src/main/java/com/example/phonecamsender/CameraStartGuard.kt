package com.example.phonecamsender

/** Main-thread lifecycle guard: ignore duplicate starts and obsolete provider callbacks. */
class CameraStartGuard {
    private var generation = 0
    private var pending = false
    var running = false
        private set
    fun begin(): Int? {
        if (pending || running) return null
        pending = true
        return ++generation
    }
    fun isCurrent(ticket: Int): Boolean = ticket == generation && pending
    fun complete(ticket: Int, success: Boolean) {
        if (!isCurrent(ticket)) return
        pending = false
        running = success
    }
    fun stop() {
        generation++
        pending = false
        running = false
    }
}
