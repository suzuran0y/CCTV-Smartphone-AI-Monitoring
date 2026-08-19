package com.example.phonecamsender

import okhttp3.HttpUrl.Companion.toHttpUrlOrNull
import java.net.DatagramPacket
import java.net.DatagramSocket
import java.net.HttpURLConnection
import java.net.Inet4Address
import java.net.InetAddress
import java.net.NetworkInterface
import java.net.SocketTimeoutException
import java.net.URI
import java.net.URL
import java.util.Collections
import java.util.concurrent.Executors
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicReference

object NetworkDiscover {

    private const val DISCOVERY_PORT = 37020
    private const val DEFAULT_SERVER_PORT = 8000
    private const val UDP_ATTEMPTS = 3
    private const val UDP_ATTEMPT_TIMEOUT_MS = 700L
    private const val SCAN_TIMEOUT_MS = 350
    private const val SCAN_WORKERS = 32
    private const val SCAN_TOTAL_TIMEOUT_SEC = 6L

    // 输入：172.16.1.2 或 172.16.1.2:8000 -> 输出 baseUrl: http://172.16.1.2:8000
    fun inputToBaseUrlOrNull(input: String): String? {
        val raw = input.trim()
        if (raw.isBlank()) return null

        val candidate = if (raw.startsWith("http://", ignoreCase = true) ||
            raw.startsWith("https://", ignoreCase = true)
        ) {
            raw
        } else {
            "http://$raw"
        }

        val uri = try {
            URI(candidate)
        } catch (_: Exception) {
            return null
        }

        val scheme = uri.scheme?.lowercase() ?: return null
        if (scheme != "http" && scheme != "https") return null
        if (uri.rawUserInfo != null || uri.rawQuery != null || uri.rawFragment != null) return null
        if (!uri.rawPath.isNullOrEmpty() && uri.rawPath != "/") return null

        val host = uri.host ?: return null
        val port = if (uri.port == -1) 8000 else uri.port
        if (port !in 1..65535) return null

        val displayHost = if (host.contains(":")) "[$host]" else host
        val normalized = "$scheme://$displayHost:$port"
        return normalized.toHttpUrlOrNull()?.toString()?.removeSuffix("/")
    }

    // baseUrl: http://x.x.x.x:8000 -> 显示给用户：x.x.x.x:8000
    fun baseUrlToInput(baseUrl: String): String {
        return baseUrl.removePrefix("http://").removePrefix("https://").removeSuffix("/")
    }

    fun discoverServer(
        onProgress: (String) -> Unit = {},
        onFound: (String) -> Unit,
        onFail: () -> Unit
    ) {
        kotlin.concurrent.thread {
            try {
                onProgress("Discovering server via UDP...")
                val udpResult = discoverViaUdp()
                if (udpResult != null) {
                    onProgress("Server found via UDP")
                    onFound(udpResult)
                    return@thread
                }

                onProgress("Scanning local network...")
                val scanResult = scanLocalSubnets(DEFAULT_SERVER_PORT)
                if (scanResult != null) {
                    onProgress("Server found by LAN scan")
                    onFound(scanResult)
                    return@thread
                }

                onFail()
            } catch (_: Exception) {
                onFail()
            }
        }
    }

    private fun discoverViaUdp(): String? {
        DatagramSocket().use { socket ->
            socket.broadcast = true
            val message = "FIND_PHONECAM_SERVER".toByteArray()
            val targets = broadcastTargets()

            repeat(UDP_ATTEMPTS) {
                for (target in targets) {
                    try {
                        socket.send(DatagramPacket(message, message.size, target, DISCOVERY_PORT))
                    } catch (_: Exception) {}
                }

                val deadline = System.currentTimeMillis() + UDP_ATTEMPT_TIMEOUT_MS
                while (System.currentTimeMillis() < deadline) {
                    val remaining = deadline - System.currentTimeMillis()
                    socket.soTimeout = remaining.coerceIn(1L, 250L).toInt()
                    try {
                        val buffer = ByteArray(1024)
                        val response = DatagramPacket(buffer, buffer.size)
                        socket.receive(response)
                        val text = String(response.data, 0, response.length)
                        parseDiscoveryResponse(text)?.let { return it }
                    } catch (_: SocketTimeoutException) {}
                }
            }
        }
        return null
    }

    private fun broadcastTargets(): Set<InetAddress> {
        val targets = linkedSetOf(InetAddress.getByName("255.255.255.255"))
        try {
            val interfaces = NetworkInterface.getNetworkInterfaces() ?: return targets
            for (networkInterface in Collections.list(interfaces)) {
                if (!networkInterface.isUp || networkInterface.isLoopback) continue
                for (interfaceAddress in networkInterface.interfaceAddresses) {
                    interfaceAddress.broadcast?.let(targets::add)
                }
            }
        } catch (_: Exception) {}
        return targets
    }

    private fun parseDiscoveryResponse(text: String): String? {
        if (!text.startsWith("PHONECAM_SERVER ")) return null
        val url = text.removePrefix("PHONECAM_SERVER ").trim().removeSuffix("/")
        return inputToBaseUrlOrNull(url)
    }

    private fun localIpv4Addresses(): List<String> {
        val addresses = mutableListOf<String>()
        try {
            val interfaces = NetworkInterface.getNetworkInterfaces() ?: return emptyList()
            for (networkInterface in Collections.list(interfaces)) {
                if (!networkInterface.isUp || networkInterface.isLoopback) continue
                for (address in Collections.list(networkInterface.inetAddresses)) {
                    if (address is Inet4Address && address.isSiteLocalAddress) {
                        addresses.add(address.hostAddress ?: continue)
                    }
                }
            }
        } catch (_: Exception) {}
        return addresses.distinct()
    }

    internal fun buildSubnetCandidates(localAddresses: List<String>): List<String> {
        val localSet = localAddresses.toSet()
        val candidates = linkedSetOf<String>()
        for (localAddress in localAddresses) {
            val parts = localAddress.split(".")
            if (parts.size != 4 || parts.any { it.toIntOrNull() !in 0..255 }) continue
            val prefix = parts.take(3).joinToString(".")
            for (host in 1..254) {
                val candidate = "$prefix.$host"
                if (candidate !in localSet) candidates.add(candidate)
            }
        }
        return candidates.toList()
    }

    private fun scanLocalSubnets(port: Int): String? {
        val candidates = buildSubnetCandidates(localIpv4Addresses())
        return scanCandidates(candidates, port)
    }

    internal fun scanCandidates(candidates: List<String>, port: Int): String? {
        if (candidates.isEmpty()) return null

        val found = AtomicReference<String?>(null)
        val executor = Executors.newFixedThreadPool(SCAN_WORKERS)
        try {
            for (host in candidates) {
                executor.submit {
                    if (found.get() != null) return@submit
                    val baseUrl = "http://$host:$port"
                    var connection: HttpURLConnection? = null
                    try {
                        connection = URL("$baseUrl/ping").openConnection() as HttpURLConnection
                        connection.requestMethod = "GET"
                        connection.connectTimeout = SCAN_TIMEOUT_MS
                        connection.readTimeout = SCAN_TIMEOUT_MS
                        connection.instanceFollowRedirects = false
                        connection.useCaches = false
                        if (connection.responseCode == 200) {
                            val body = connection.inputStream.bufferedReader().use { it.readText().trim() }
                            if (body == "OK") found.compareAndSet(null, baseUrl)
                        }
                    } catch (_: Exception) {
                    } finally {
                        connection?.disconnect()
                    }
                }
            }
        } finally {
            executor.shutdown()
            try {
                executor.awaitTermination(SCAN_TOTAL_TIMEOUT_SEC, TimeUnit.SECONDS)
            } catch (_: InterruptedException) {
                Thread.currentThread().interrupt()
            } finally {
                executor.shutdownNow()
            }
        }
        return found.get()
    }
}
