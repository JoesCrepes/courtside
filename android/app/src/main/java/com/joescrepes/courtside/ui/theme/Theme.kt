package com.joescrepes.courtside.ui.theme

import androidx.compose.material3.LocalContentColor
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Typography
import androidx.compose.material3.darkColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.Font
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.sp
import com.joescrepes.courtside.R

/** Night-game palette: dark court, hardwood orange, scoreboard green. */
object Palette {
    val Court = Color(0xFF0A0D12)
    val Panel = Color(0xFF121821)
    val PanelHigh = Color(0xFF1A2230)
    val Line = Color(0xFF232D3C)
    val Text = Color(0xFFEAF0F7)
    val TextDim = Color(0xFF8B98AA)
    val TextFaint = Color(0xFF566273)
    val Hardwood = Color(0xFFFF7A1A)
    val HardwoodDeep = Color(0xFFE85D00)
    val Live = Color(0xFF2BD99F)
    val Out = Color(0xFFFF5A6A)
    val DayToDay = Color(0xFFFFB547)
    val Sky = Color(0xFF5AA9FF)
}

// Static files per weight: Android caches a font resource's typeface, so one
// variable font file can't serve several weights.
val Grotesk = FontFamily(
    Font(R.font.space_grotesk_regular, FontWeight.Normal),
    Font(R.font.space_grotesk_medium, FontWeight.Medium),
    Font(R.font.space_grotesk_semibold, FontWeight.SemiBold),
    Font(R.font.space_grotesk_bold, FontWeight.Bold),
)

val Inter = FontFamily(
    Font(R.font.inter_regular, FontWeight.Normal),
    Font(R.font.inter_medium, FontWeight.Medium),
    Font(R.font.inter_semibold, FontWeight.SemiBold),
    Font(R.font.inter_bold, FontWeight.Bold),
)

/** Scoreboard numbers: tabular figures so columns line up. */
val Numeric = TextStyle(fontFamily = Grotesk, fontWeight = FontWeight.Bold, fontFeatureSettings = "tnum")

private val type = Typography(
    displayLarge = TextStyle(fontFamily = Grotesk, fontWeight = FontWeight.Bold, fontSize = 56.sp, lineHeight = 60.sp, letterSpacing = (-1.5).sp),
    displayMedium = TextStyle(fontFamily = Grotesk, fontWeight = FontWeight.Bold, fontSize = 44.sp, lineHeight = 48.sp, letterSpacing = (-1).sp),
    displaySmall = TextStyle(fontFamily = Grotesk, fontWeight = FontWeight.Bold, fontSize = 34.sp, lineHeight = 40.sp, letterSpacing = (-0.5).sp),
    headlineMedium = TextStyle(fontFamily = Grotesk, fontWeight = FontWeight.Bold, fontSize = 28.sp, lineHeight = 34.sp, letterSpacing = (-0.5).sp),
    headlineSmall = TextStyle(fontFamily = Grotesk, fontWeight = FontWeight.Bold, fontSize = 22.sp, lineHeight = 28.sp),
    titleLarge = TextStyle(fontFamily = Grotesk, fontWeight = FontWeight.SemiBold, fontSize = 20.sp, lineHeight = 26.sp),
    titleMedium = TextStyle(fontFamily = Inter, fontWeight = FontWeight.SemiBold, fontSize = 16.sp, lineHeight = 22.sp),
    titleSmall = TextStyle(fontFamily = Inter, fontWeight = FontWeight.SemiBold, fontSize = 14.sp, lineHeight = 20.sp),
    bodyLarge = TextStyle(fontFamily = Inter, fontWeight = FontWeight.Normal, fontSize = 16.sp, lineHeight = 24.sp),
    bodyMedium = TextStyle(fontFamily = Inter, fontWeight = FontWeight.Normal, fontSize = 14.sp, lineHeight = 20.sp),
    bodySmall = TextStyle(fontFamily = Inter, fontWeight = FontWeight.Normal, fontSize = 12.sp, lineHeight = 16.sp),
    labelLarge = TextStyle(fontFamily = Inter, fontWeight = FontWeight.SemiBold, fontSize = 14.sp, lineHeight = 20.sp),
    labelMedium = TextStyle(fontFamily = Inter, fontWeight = FontWeight.Medium, fontSize = 12.sp, lineHeight = 16.sp),
    labelSmall = TextStyle(fontFamily = Grotesk, fontWeight = FontWeight.SemiBold, fontSize = 11.sp, lineHeight = 14.sp, letterSpacing = 1.sp),
)

private val colors = darkColorScheme(
    primary = Palette.Hardwood,
    onPrimary = Color(0xFF1A0B00),
    primaryContainer = Palette.Hardwood.copy(alpha = 0.16f),
    onPrimaryContainer = Palette.Hardwood,
    secondary = Palette.Live,
    onSecondary = Color(0xFF00281B),
    tertiary = Palette.Sky,
    background = Palette.Court,
    onBackground = Palette.Text,
    surface = Palette.Court,
    onSurface = Palette.Text,
    surfaceVariant = Palette.PanelHigh,
    onSurfaceVariant = Palette.TextDim,
    surfaceContainerLowest = Palette.Court,
    surfaceContainerLow = Palette.Panel,
    surfaceContainer = Palette.Panel,
    surfaceContainerHigh = Palette.PanelHigh,
    surfaceContainerHighest = Palette.PanelHigh,
    outline = Palette.Line,
    outlineVariant = Palette.Line,
    error = Palette.Out,
    onError = Color(0xFF2A0006),
)

@Composable
fun CourtsideTheme(content: @Composable () -> Unit) {
    MaterialTheme(colorScheme = colors, typography = type) {
        // Text outside a Surface would otherwise default to black.
        CompositionLocalProvider(LocalContentColor provides Palette.Text, content = content)
    }
}
