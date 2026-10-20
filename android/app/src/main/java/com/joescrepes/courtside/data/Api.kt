package com.joescrepes.courtside.data

import com.joescrepes.courtside.BuildConfig
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import kotlinx.serialization.ExperimentalSerializationApi
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonNamingStrategy
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.contentOrNull
import kotlinx.serialization.json.encodeToJsonElement
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import okhttp3.HttpUrl.Companion.toHttpUrl
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody

class ApiException(val status: Int, message: String) : Exception(message)

/** The server re-planned a write and got something different from the preview. */
class PlanChanged(val preview: Preview) : Exception("Your roster changed since the preview.")

class Api(private val http: OkHttpClient, private val auth: Auth) {
    @OptIn(ExperimentalSerializationApi::class)
    val json = Json {
        ignoreUnknownKeys = true
        explicitNulls = false
        coerceInputValues = true
        namingStrategy = JsonNamingStrategy.SnakeCase
    }

    suspend fun context(): LeagueContext = get("/context")
    suspend fun league(): League = get("/league")
    suspend fun roster(day: Int? = null): Roster = get("/roster", "day" to day)
    suspend fun team(id: Int, day: Int? = null): Roster = get("/teams/$id", "day" to day)
    suspend fun scoreboard(week: Int? = null): Scoreboard = get("/scoreboard", "week" to week)
    suspend fun activity(limit: Int = 30): ActivityFeed = get("/activity", "limit" to limit)

    suspend fun players(query: String?, position: String?, available: Boolean, limit: Int = 50): PlayerList =
        get("/players", "q" to query?.takeIf { it.isNotBlank() }, "pos" to position, "available" to available, "limit" to limit)

    suspend fun previewLineup(intent: LineupIntent): Preview = post("/lineup/preview", json.encodeToJsonElement(intent))
    suspend fun confirmLineup(intent: LineupIntent, preview: Preview): Confirmed =
        post("/lineup/confirm", confirmation(json.encodeToJsonElement(intent), preview))

    suspend fun previewRoster(intent: RosterIntent): Preview = post("/roster/preview", json.encodeToJsonElement(intent))
    suspend fun confirmRoster(intent: RosterIntent, preview: Preview): Confirmed =
        post("/roster/confirm", confirmation(json.encodeToJsonElement(intent), preview))

    private fun confirmation(intent: JsonElement, preview: Preview) = JsonObject(
        intent.jsonObject + mapOf("expect" to JsonArray(preview.expect), "scoring_period" to JsonPrimitive(preview.scoringPeriod))
    )

    private suspend inline fun <reified T> get(path: String, vararg params: Pair<String, Any?>): T {
        val url = (BuildConfig.API_URL + path).toHttpUrl().newBuilder().apply {
            params.forEach { (k, v) -> if (v != null) addQueryParameter(k, v.toString()) }
        }.build()
        return json.decodeFromString(send(Request.Builder().url(url).get()))
    }

    private suspend inline fun <reified T> post(path: String, body: JsonElement): T {
        val request = Request.Builder()
            .url(BuildConfig.API_URL + path)
            .post(body.toString().toRequestBody("application/json".toMediaType()))
        return json.decodeFromString(send(request))
    }

    /** Sends with the current access token; on a 401, refreshes once and retries. */
    private suspend fun send(request: Request.Builder): String = withContext(Dispatchers.IO) {
        var token = auth.accessToken() ?: throw ApiException(401, "Signed out")
        repeat(2) { attempt ->
            http.newCall(request.header("Authorization", "Bearer $token").build()).execute().use { r ->
                val text = r.body?.string().orEmpty()
                if (r.isSuccessful) return@withContext text
                if (r.code == 401 && attempt == 0) {
                    token = auth.accessToken(forceRefresh = true) ?: throw ApiException(401, "Signed out")
                } else {
                    throw failure(r.code, text)
                }
            }
        }
        throw ApiException(401, "Signed out")
    }

    private fun failure(status: Int, text: String): Exception {
        val detail = runCatching { json.parseToJsonElement(text).jsonObject["detail"] }.getOrNull()
        if (status == 409 && detail is JsonObject) {
            detail["preview"]?.let { return PlanChanged(json.decodeFromJsonElement(Preview.serializer(), it)) }
        }
        val message = when (detail) {
            is JsonPrimitive -> detail.contentOrNull
            is JsonObject -> detail["message"]?.jsonPrimitive?.contentOrNull
            else -> null
        }
        return ApiException(status, message ?: "Server error ($status)")
    }
}
