package com.joescrepes.courtside

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.SystemBarStyle
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.runtime.CompositionLocalProvider
import com.joescrepes.courtside.ui.LocalGraph
import com.joescrepes.courtside.ui.Root
import com.joescrepes.courtside.ui.theme.CourtsideTheme

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge(
            statusBarStyle = SystemBarStyle.dark(android.graphics.Color.TRANSPARENT),
            navigationBarStyle = SystemBarStyle.dark(android.graphics.Color.TRANSPARENT),
        )
        val graph = (application as CourtsideApp).graph
        if (BuildConfig.DEBUG) {
            // adb shell am start -n com.joescrepes.courtside/.MainActivity -e dev_api_key <key>
            intent.getStringExtra("dev_api_key")?.let(graph.auth::useDevApiKey)
        }
        setContent {
            CourtsideTheme {
                CompositionLocalProvider(LocalGraph provides graph) {
                    Root()
                }
            }
        }
    }
}
