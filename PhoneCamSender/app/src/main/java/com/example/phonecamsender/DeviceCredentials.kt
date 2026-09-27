package com.example.phonecamsender

import android.content.Context
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import android.util.AtomicFile
import android.util.Base64
import org.json.JSONObject
import java.io.File
import java.security.KeyStore
import javax.crypto.Cipher
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey
import javax.crypto.spec.GCMParameterSpec

/** Encrypted credentials are excluded from backup and bound to one server URL. */
object DeviceCredentials {
    private const val ALIAS = "camflow-device-token-v1"
    private var cachedServer: String? = null
    private var cachedToken: String? = null
    private fun file(context: Context) = AtomicFile(File(context.noBackupFilesDir, "device-credentials.json"))

    private fun key(): SecretKey {
        val store = KeyStore.getInstance("AndroidKeyStore").apply { load(null) }
        (store.getKey(ALIAS, null) as? SecretKey)?.let { return it }
        return KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, "AndroidKeyStore").run {
            init(KeyGenParameterSpec.Builder(ALIAS, KeyProperties.PURPOSE_ENCRYPT or KeyProperties.PURPOSE_DECRYPT)
                .setBlockModes(KeyProperties.BLOCK_MODE_GCM)
                .setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE).build())
            generateKey()
        }
    }

    @Synchronized
    fun save(context: Context, server: String, token: String) {
        require(token.length in 32..256)
        val cipher = Cipher.getInstance("AES/GCM/NoPadding")
        cipher.init(Cipher.ENCRYPT_MODE, key())
        cipher.updateAAD(server.toByteArray(Charsets.UTF_8))
        val json = JSONObject().put("server", server)
            .put("iv", Base64.encodeToString(cipher.iv, Base64.NO_WRAP))
            .put("data", Base64.encodeToString(cipher.doFinal(token.toByteArray(Charsets.UTF_8)), Base64.NO_WRAP))
        val target = file(context)
        val output = target.startWrite()
        try {
            output.write(json.toString().toByteArray(Charsets.UTF_8))
            target.finishWrite(output)
        } catch (e: Exception) {
            target.failWrite(output)
            throw e
        }
        // Force the next use through decryption, including after a fresh pairing.
        cachedServer = null
        cachedToken = null
    }

    @Synchronized
    fun tokenFor(context: Context, server: String): String? {
        if (server == cachedServer) return cachedToken
        return try {
            val json = JSONObject(String(file(context).readFully(), Charsets.UTF_8))
            if (json.getString("server") != server) return null
            val cipher = Cipher.getInstance("AES/GCM/NoPadding")
            cipher.init(Cipher.DECRYPT_MODE, key(), GCMParameterSpec(128, Base64.decode(json.getString("iv"), Base64.NO_WRAP)))
            cipher.updateAAD(server.toByteArray(Charsets.UTF_8))
            val token = String(cipher.doFinal(Base64.decode(json.getString("data"), Base64.NO_WRAP)), Charsets.UTF_8)
            cachedServer = server
            cachedToken = token
            token
        } catch (_: Exception) { null }
    }

    @Synchronized
    fun clear(context: Context) {
        file(context).delete()
        cachedServer = null
        cachedToken = null
    }

    @Synchronized
    fun clearIfCurrent(context: Context, server: String, token: String) {
        if (tokenFor(context, server) == token) clear(context)
    }
}
