package com.joescrepes.courtside

import android.app.Application
import android.content.Context
import com.joescrepes.courtside.data.Api
import com.joescrepes.courtside.data.Auth
import com.joescrepes.courtside.data.TokenStore
import okhttp3.OkHttpClient
import java.util.concurrent.TimeUnit

class CourtsideApp : Application() {
    lateinit var graph: AppGraph
        private set

    override fun onCreate() {
        super.onCreate()
        graph = AppGraph(this)
    }
}

/** The app's long-lived objects, built once. */
class AppGraph(context: Context) {
    private val http = OkHttpClient.Builder()
        .connectTimeout(15, TimeUnit.SECONDS)
        .callTimeout(30, TimeUnit.SECONDS)
        .build()
    val auth = Auth(TokenStore(context), http)
    val api = Api(http, auth)
}
