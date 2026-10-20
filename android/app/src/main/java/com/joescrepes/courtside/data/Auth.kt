package com.joescrepes.courtside.data

import android.content.Context
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import android.util.Base64
import com.joescrepes.courtside.BuildConfig
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import kotlinx.coroutines.withContext
import kotlinx.serialization.Serializable
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import kotlinx.serialization.json.long
import kotlinx.serialization.json.longOrNull
import kotlinx.serialization.json.put
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import java.security.KeyStore
import javax.crypto.Cipher
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey
import javax.crypto.spec.GCMParameterSpec

@Serializable
data class Session(
    val accessToken: String,
    val refreshToken: String,
    // Epoch seconds.
    val expiresAt: Long,
    val email: String,
)

class AuthException(message: String) : Exception(message)

/** Keeps the session encrypted with a key that never leaves the Android Keystore. */
class TokenStore(context: Context) {
    private val prefs = context.getSharedPreferences("auth", Context.MODE_PRIVATE)

    private fun key(): SecretKey {
        val ks = KeyStore.getInstance("AndroidKeyStore").apply { load(null) }
        (ks.getKey(ALIAS, null) as? SecretKey)?.let { return it }
        val gen = KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, "AndroidKeyStore")
        gen.init(
            KeyGenParameterSpec.Builder(ALIAS, KeyProperties.PURPOSE_ENCRYPT or KeyProperties.PURPOSE_DECRYPT)
                .setBlockModes(KeyProperties.BLOCK_MODE_GCM)
                .setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE)
                .build()
        )
        return gen.generateKey()
    }

    fun save(session: Session?) {
        if (session == null) {
            prefs.edit().remove(PREF).apply()
            return
        }
        val cipher = Cipher.getInstance(CIPHER).apply { init(Cipher.ENCRYPT_MODE, key()) }
        val sealed = cipher.iv + cipher.doFinal(Json.encodeToString(Session.serializer(), session).toByteArray())
        prefs.edit().putString(PREF, Base64.encodeToString(sealed, Base64.NO_WRAP)).apply()
    }

    fun load(): Session? = runCatching {
        val sealed = Base64.decode(prefs.getString(PREF, null) ?: return null, Base64.NO_WRAP)
        val cipher = Cipher.getInstance(CIPHER).apply {
            init(Cipher.DECRYPT_MODE, key(), GCMParameterSpec(128, sealed, 0, IV_BYTES))
        }
        val plain = cipher.doFinal(sealed, IV_BYTES, sealed.size - IV_BYTES)
        Json.decodeFromString(Session.serializer(), String(plain))
    }.getOrNull()

    private companion object {
        const val ALIAS = "courtside-session"
        const val PREF = "session"
        const val CIPHER = "AES/GCM/NoPadding"
        const val IV_BYTES = 12
    }
}

/** Supabase email/password sign-in, with silent refresh of the hourly access token. */
class Auth(private val store: TokenStore, private val http: OkHttpClient) {
    private val _session = MutableStateFlow(store.load())
    val session: StateFlow<Session?> = _session
    private val lock = Mutex()

    suspend fun signIn(email: String, password: String) {
        set(token("password", buildJsonObject { put("email", email.trim()); put("password", password) }))
    }

    fun signOut() = set(null)

    /**
     * Debug builds only: act on a read-only server API key instead of a Supabase
     * session, so screens can be checked on an emulator without a password.
     */
    fun useDevApiKey(key: String) {
        check(BuildConfig.DEBUG)
        _session.value = Session(accessToken = key, refreshToken = "", expiresAt = Long.MAX_VALUE, email = "dev")
    }

    /** A usable access token, refreshed first if it expires within a minute. Null when signed out. */
    suspend fun accessToken(forceRefresh: Boolean = false): String? = lock.withLock {
        val current = _session.value ?: return null
        if (!forceRefresh && current.expiresAt - 60 > nowSeconds()) return current.accessToken
        try {
            token("refresh_token", buildJsonObject { put("refresh_token", current.refreshToken) })
                .also(::set).accessToken
        } catch (e: AuthException) {
            // Supabase refused the refresh token: the session is over. (Network
            // errors propagate instead, so a dead connection doesn't sign you out.)
            set(null)
            null
        }
    }

    private fun set(session: Session?) {
        store.save(session)
        _session.value = session
    }

    private suspend fun token(grant: String, body: JsonObject): Session = withContext(Dispatchers.IO) {
        val request = Request.Builder()
            .url("${BuildConfig.SUPABASE_URL}/auth/v1/token?grant_type=$grant")
            .header("apikey", BuildConfig.SUPABASE_ANON_KEY)
            .post(body.toString().toRequestBody("application/json".toMediaType()))
            .build()
        http.newCall(request).execute().use { r ->
            val text = r.body?.string().orEmpty()
            val json = runCatching { Json.parseToJsonElement(text).jsonObject }.getOrNull()
            if (!r.isSuccessful) {
                val msg = json?.get("msg") ?: json?.get("error_description") ?: json?.get("message")
                throw AuthException(msg?.jsonPrimitive?.content ?: "Sign-in failed (${r.code})")
            }
            checkNotNull(json)
            Session(
                accessToken = json.getValue("access_token").jsonPrimitive.content,
                refreshToken = json.getValue("refresh_token").jsonPrimitive.content,
                expiresAt = json["expires_at"]?.jsonPrimitive?.longOrNull
                    ?: (nowSeconds() + (json["expires_in"]?.jsonPrimitive?.long ?: 3600)),
                email = json["user"]?.jsonObject?.get("email")?.jsonPrimitive?.content.orEmpty(),
            )
        }
    }

    private fun nowSeconds() = System.currentTimeMillis() / 1000
}
