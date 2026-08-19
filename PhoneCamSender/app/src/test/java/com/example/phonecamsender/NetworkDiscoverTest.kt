package com.example.phonecamsender

import com.sun.net.httpserver.HttpServer
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import java.net.InetSocketAddress

class NetworkDiscoverTest {

    @Test
    fun inputWithoutPortUsesServerDefault() {
        assertEquals(
            "http://192.168.1.20:8000",
            NetworkDiscover.inputToBaseUrlOrNull("192.168.1.20")
        )
    }

    @Test
    fun inputKeepsExplicitSchemeAndPort() {
        assertEquals(
            "https://camera.example.com:8443",
            NetworkDiscover.inputToBaseUrlOrNull("https://camera.example.com:8443/")
        )
    }

    @Test
    fun invalidOrUnsafeAddressesAreRejected() {
        assertNull(NetworkDiscover.inputToBaseUrlOrNull(""))
        assertNull(NetworkDiscover.inputToBaseUrlOrNull("ftp://192.168.1.20"))
        assertNull(NetworkDiscover.inputToBaseUrlOrNull("http://192.168.1.20/path"))
        assertNull(NetworkDiscover.inputToBaseUrlOrNull("http://user@192.168.1.20"))
        assertNull(NetworkDiscover.inputToBaseUrlOrNull("http://192.168.1.20:70000"))
    }

    @Test
    fun subnetCandidatesStayInsideLocal24Network() {
        val candidates = NetworkDiscover.buildSubnetCandidates(listOf("192.168.7.42"))

        assertEquals(253, candidates.size)
        assertTrue("192.168.7.1" in candidates)
        assertTrue("192.168.7.254" in candidates)
        assertFalse("192.168.7.42" in candidates)
        assertFalse("192.168.8.1" in candidates)
    }

    @Test
    fun subnetScanFindsSentinelPingEndpoint() {
        val server = HttpServer.create(InetSocketAddress("127.0.0.1", 0), 0)
        server.createContext("/ping") { exchange ->
            val body = "OK".toByteArray()
            exchange.sendResponseHeaders(200, body.size.toLong())
            exchange.responseBody.use { it.write(body) }
        }
        server.start()

        try {
            assertEquals(
                "http://127.0.0.1:${server.address.port}",
                NetworkDiscover.scanCandidates(listOf("127.0.0.1"), server.address.port)
            )
        } finally {
            server.stop(0)
        }
    }
}
