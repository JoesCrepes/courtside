import java.util.Properties

plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
    id("org.jetbrains.kotlin.plugin.compose")
    id("org.jetbrains.kotlin.plugin.serialization")
}

// Client settings come from the repo's .env. Everything read here ends up in
// the APK, so only public values belong in this list (the Supabase anon key
// is public by design).
val dotenv = Properties().apply {
    rootProject.file("../.env").takeIf { it.exists() }?.forEachLine { raw ->
        val line = raw.trim()
        if (line.isNotEmpty() && !line.startsWith("#") && "=" in line) {
            val (k, v) = line.split("=", limit = 2)
            setProperty(k.trim(), v.trim().trim('"', '\''))
        }
    }
}

fun setting(key: String, default: String = ""): String =
    (System.getenv(key) ?: dotenv.getProperty(key))?.takeIf { it.isNotBlank() } ?: default

android {
    namespace = "com.joescrepes.courtside"
    compileSdk = 36

    defaultConfig {
        applicationId = "com.joescrepes.courtside"
        minSdk = 28
        targetSdk = 36
        versionCode = 1
        versionName = "0.1.0"
        buildConfigField("String", "API_URL", "\"${setting("COURTSIDE_API_URL", "https://courtside-azure-six.vercel.app")}\"")
        buildConfigField("String", "SUPABASE_URL", "\"${setting("SUPABASE_URL")}\"")
        buildConfigField("String", "SUPABASE_ANON_KEY", "\"${setting("SUPABASE_ANON_KEY")}\"")
    }

    buildTypes {
        release {
            isMinifyEnabled = false
            // Sideloaded personal build: the debug key is fine.
            signingConfig = signingConfigs.getByName("debug")
        }
    }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    buildFeatures {
        compose = true
        buildConfig = true
    }
}

kotlin {
    compilerOptions {
        jvmTarget.set(org.jetbrains.kotlin.gradle.dsl.JvmTarget.JVM_17)
    }
}

dependencies {
    implementation(platform("androidx.compose:compose-bom:2025.09.00"))
    implementation("androidx.compose.ui:ui")
    implementation("androidx.compose.material3:material3")
    implementation("androidx.compose.material:material-icons-extended")
    implementation("androidx.compose.ui:ui-tooling-preview")
    debugImplementation("androidx.compose.ui:ui-tooling")

    implementation("androidx.core:core-ktx:1.17.0")
    implementation("androidx.activity:activity-compose:1.11.0")
    implementation("androidx.lifecycle:lifecycle-viewmodel-compose:2.9.4")
    implementation("androidx.lifecycle:lifecycle-runtime-compose:2.9.4")

    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-android:1.10.2")
    implementation("org.jetbrains.kotlinx:kotlinx-serialization-json:1.9.0")
    implementation("com.squareup.okhttp3:okhttp:4.12.0")
    implementation("io.coil-kt.coil3:coil-compose:3.3.0")
    implementation("io.coil-kt.coil3:coil-network-okhttp:3.3.0")

    testImplementation("junit:junit:4.13.2")
}
