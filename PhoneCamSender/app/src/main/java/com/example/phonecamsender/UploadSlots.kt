package com.example.phonecamsender

/** Bounds encoding + outstanding uploads; never queues old frames. */
class UploadSlots(val limit: Int) {
    init { require(limit > 0) }
    private var used = 0
    private var accepting = true

    @Synchronized fun tryAcquire(): Lease? {
        if (!accepting || used >= limit) return null
        used++
        return Lease()
    }
    @Synchronized fun count(): Int = used
    @Synchronized fun stopAccepting() { accepting = false }

    inner class Lease internal constructor() : AutoCloseable {
        private var released = false
        override fun close() = synchronized(this@UploadSlots) {
            if (!released) { released = true; used-- }
        }
    }
}
