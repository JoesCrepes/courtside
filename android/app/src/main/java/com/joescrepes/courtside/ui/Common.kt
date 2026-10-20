package com.joescrepes.courtside.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.rounded.ArrowForward
import androidx.compose.material.icons.rounded.CloudOff
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.SnackbarHostState
import androidx.compose.material3.Text
import androidx.compose.material3.rememberModalBottomSheetState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.staticCompositionLocalOf
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import coil3.compose.AsyncImage
import com.joescrepes.courtside.AppGraph
import com.joescrepes.courtside.data.ApiException
import com.joescrepes.courtside.data.AuthException
import com.joescrepes.courtside.data.Game
import com.joescrepes.courtside.ui.theme.Grotesk
import com.joescrepes.courtside.ui.theme.Numeric
import com.joescrepes.courtside.ui.theme.Palette
import kotlinx.coroutines.CancellationException
import java.io.IOException
import java.time.Instant
import java.time.LocalDate
import java.time.ZoneId
import java.time.format.DateTimeFormatter
import java.util.Locale

val LocalGraph = staticCompositionLocalOf<AppGraph> { error("no AppGraph") }
val LocalSnackbar = staticCompositionLocalOf { SnackbarHostState() }

// ---- results and errors -----------------------------------------------------

/** runCatching that doesn't swallow coroutine cancellation. */
suspend fun <T> attempt(block: suspend () -> T): Result<T> = try {
    Result.success(block())
} catch (e: CancellationException) {
    throw e
} catch (e: Exception) {
    Result.failure(e)
}

fun Throwable.friendly(): String = when (this) {
    is ApiException, is AuthException -> message ?: "Something went wrong"
    is IOException -> "Can't reach courtside. Check your connection."
    else -> message ?: "Something went wrong"
}

// ---- formatting --------------------------------------------------------------

fun Double.pts(): String = String.format(Locale.US, "%.1f", this)

private val clock = DateTimeFormatter.ofPattern("h:mm a", Locale.US)
private val shortDate = DateTimeFormatter.ofPattern("EEE, MMM d", Locale.US)

fun gameTime(epochMs: Long): String = clock.format(Instant.ofEpochMilli(epochMs).atZone(ZoneId.systemDefault()))

fun Game.label(): String = "${if (home) "vs" else "@"} $opponent · ${gameTime(start)}"

/** Basketball scoring periods are calendar days, so a day id maps to a date by offset from today. */
fun dateFor(day: Int, today: Int): LocalDate = LocalDate.now().plusDays((day - today).toLong())

fun dayLabel(day: Int, today: Int): String = when (day - today) {
    0 -> "Today"
    1 -> "Tomorrow"
    -1 -> "Yesterday"
    else -> shortDate.format(dateFor(day, today))
}

fun timeAgo(epochMs: Long): String {
    val minutes = (System.currentTimeMillis() - epochMs) / 60_000
    return when {
        minutes < 1 -> "just now"
        minutes < 60 -> "${minutes}m ago"
        minutes < 24 * 60 -> "${minutes / 60}h ago"
        minutes < 7 * 24 * 60 -> "${minutes / (24 * 60)}d ago"
        else -> DateTimeFormatter.ofPattern("MMM d", Locale.US).format(Instant.ofEpochMilli(epochMs).atZone(ZoneId.systemDefault()))
    }
}

fun initials(name: String): String =
    name.split(" ").mapNotNull { w -> w.firstOrNull { it.isLetterOrDigit() } }.take(2).joinToString("") { it.uppercase() }

// ---- images ------------------------------------------------------------------

private fun headshotUrl(playerId: Int) =
    "https://a.espncdn.com/combiner/i?img=/i/headshots/nba/players/full/$playerId.png&w=160&h=116"

/** A player's ESPN headshot in a circle, over their initials (shown if the image is missing). */
@Composable
fun Headshot(playerId: Int, name: String, size: Dp = 44.dp, ring: Color = Color.Transparent) {
    Box(
        Modifier
            .size(size)
            .clip(CircleShape)
            .background(Palette.PanelHigh)
            .border(1.5.dp, ring, CircleShape),
        contentAlignment = Alignment.Center,
    ) {
        Text(initials(name), style = MaterialTheme.typography.labelMedium, color = Palette.TextDim)
        AsyncImage(
            model = headshotUrl(playerId),
            contentDescription = null,
            contentScale = ContentScale.Crop,
            alignment = Alignment.TopCenter,
            modifier = Modifier.fillMaxSize().padding(top = size * 0.08f),
        )
    }
}

@Composable
fun TeamLogo(url: String?, name: String, size: Dp = 40.dp) {
    Box(
        Modifier.size(size).clip(RoundedCornerShape(size * 0.3f)).background(Palette.PanelHigh),
        contentAlignment = Alignment.Center,
    ) {
        Text(initials(name), style = MaterialTheme.typography.labelMedium, color = Palette.TextDim)
        if (!url.isNullOrBlank()) {
            AsyncImage(model = url, contentDescription = null, contentScale = ContentScale.Crop, modifier = Modifier.fillMaxSize())
        }
    }
}

@Composable
fun NbaLogo(abbrev: String?, size: Dp = 16.dp) {
    if (abbrev.isNullOrBlank()) return
    AsyncImage(
        model = "https://a.espncdn.com/combiner/i?img=/i/teamlogos/nba/500/${abbrev.lowercase()}.png&w=64&h=64",
        contentDescription = abbrev,
        modifier = Modifier.size(size),
    )
}

// ---- small pieces ------------------------------------------------------------

@Composable
fun Panel(modifier: Modifier = Modifier, padding: PaddingValues = PaddingValues(16.dp), content: @Composable ColumnScope.() -> Unit) {
    Column(
        modifier
            .clip(RoundedCornerShape(20.dp))
            .background(Palette.Panel)
            .border(1.dp, Palette.Line, RoundedCornerShape(20.dp))
            .padding(padding),
        content = content,
    )
}

@Composable
fun SectionLabel(text: String, modifier: Modifier = Modifier, trailing: String? = null) {
    Row(modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
        Text(text.uppercase(), style = MaterialTheme.typography.labelSmall, color = Palette.TextDim, modifier = Modifier.weight(1f))
        if (trailing != null) Text(trailing, style = MaterialTheme.typography.labelSmall, color = Palette.TextFaint)
    }
}

/** A small rounded tag: slot names, WA, injury status. */
@Composable
fun Tag(text: String, color: Color, modifier: Modifier = Modifier, filled: Boolean = false) {
    Box(
        modifier
            .clip(RoundedCornerShape(6.dp))
            .background(if (filled) color else color.copy(alpha = 0.14f))
            .padding(horizontal = 6.dp, vertical = 2.dp),
    ) {
        Text(
            text, color = if (filled) Palette.Court else color,
            fontFamily = Grotesk, fontWeight = FontWeight.Bold, fontSize = 10.sp, letterSpacing = 0.6.sp,
        )
    }
}

@Composable
fun InjuryTag(status: String) {
    when (status) {
        "OUT", "INJURY_RESERVE" -> Tag("OUT", Palette.Out)
        "DAY_TO_DAY" -> Tag("DTD", Palette.DayToDay)
        "SUSPENSION" -> Tag("SUSP", Palette.Out)
    }
}

@Composable
fun StatColumn(value: String, label: String, modifier: Modifier = Modifier, color: Color = Palette.Text) {
    Column(modifier, horizontalAlignment = Alignment.End) {
        Text(value, style = Numeric.copy(fontSize = 17.sp), color = color)
        Text(label, style = MaterialTheme.typography.labelSmall.copy(fontSize = 9.sp), color = Palette.TextFaint)
    }
}

@Composable
fun LoadingPane(modifier: Modifier = Modifier) {
    Box(modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
        CircularProgressIndicator(color = Palette.Hardwood, strokeWidth = 3.dp, modifier = Modifier.size(36.dp))
    }
}

@Composable
fun ErrorPane(message: String, onRetry: () -> Unit, modifier: Modifier = Modifier) {
    Column(
        modifier.fillMaxSize().padding(32.dp),
        verticalArrangement = Arrangement.Center,
        horizontalAlignment = Alignment.CenterHorizontally,
    ) {
        Icon(Icons.Rounded.CloudOff, null, tint = Palette.TextFaint, modifier = Modifier.size(40.dp))
        Spacer(Modifier.height(12.dp))
        Text(message, style = MaterialTheme.typography.bodyMedium, color = Palette.TextDim, textAlign = TextAlign.Center)
        Spacer(Modifier.height(16.dp))
        OutlinedButton(onClick = onRetry) { Text("Try again") }
    }
}

// ---- preview -> confirm sheet ---------------------------------------------------

/** One line of a server summary, e.g. "Jalen Duren: BE -> C" or "Add Seth Curry". */
@Composable
private fun SummaryLine(line: String) {
    val (who, move) = line.split(": ", limit = 2).let { if (it.size == 2) it[0] to it[1] else it[0] to null }
    Row(
        Modifier
            .fillMaxWidth()
            .clip(RoundedCornerShape(14.dp))
            .background(Palette.PanelHigh)
            .padding(horizontal = 14.dp, vertical = 12.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Text(who, style = MaterialTheme.typography.titleSmall, modifier = Modifier.weight(1f), maxLines = 1, overflow = TextOverflow.Ellipsis)
        if (move != null) {
            val (from, to) = move.split(" -> ").let { it.first() to it.last() }
            Tag(from, Palette.TextDim)
            Icon(Icons.AutoMirrored.Rounded.ArrowForward, null, tint = Palette.TextFaint, modifier = Modifier.padding(horizontal = 6.dp).size(14.dp))
            Tag(to, Palette.Hardwood)
        }
    }
}

/**
 * Bottom sheet for every write: shows the server's preview and confirms it.
 * `summary` is null while the preview loads.
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun ConfirmSheet(
    title: String,
    summary: List<String>?,
    busy: Boolean,
    error: String?,
    note: String?,
    confirmLabel: String,
    onConfirm: () -> Unit,
    onDismiss: () -> Unit,
    header: @Composable ColumnScope.() -> Unit = {},
) {
    ModalBottomSheet(
        onDismissRequest = onDismiss,
        sheetState = rememberModalBottomSheetState(skipPartiallyExpanded = true),
        containerColor = Palette.Panel,
        contentColor = Palette.Text,
    ) {
        Column(Modifier.fillMaxWidth().padding(horizontal = 20.dp).navigationBarsPadding().padding(bottom = 16.dp)) {
            Text(title, style = MaterialTheme.typography.headlineSmall)
            Spacer(Modifier.height(12.dp))
            header()
            if (note != null) {
                Text(note, style = MaterialTheme.typography.bodySmall, color = Palette.DayToDay, modifier = Modifier.padding(bottom = 10.dp))
            }
            if (summary == null && error == null) {
                Box(Modifier.fillMaxWidth().height(96.dp), contentAlignment = Alignment.Center) {
                    CircularProgressIndicator(color = Palette.Hardwood, strokeWidth = 3.dp, modifier = Modifier.size(28.dp))
                }
            } else if (summary != null) {
                Column(verticalArrangement = Arrangement.spacedBy(8.dp)) { summary.forEach { SummaryLine(it) } }
            }
            if (error != null) {
                Text(error, style = MaterialTheme.typography.bodySmall, color = Palette.Out, modifier = Modifier.padding(top = 12.dp))
            }
            Spacer(Modifier.height(20.dp))
            Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                OutlinedButton(onClick = onDismiss, modifier = Modifier.weight(1f).height(52.dp), shape = RoundedCornerShape(16.dp)) {
                    Text("Cancel")
                }
                Button(
                    onClick = onConfirm,
                    enabled = summary != null && !busy,
                    modifier = Modifier.weight(1.4f).height(52.dp),
                    shape = RoundedCornerShape(16.dp),
                    colors = ButtonDefaults.buttonColors(containerColor = Palette.Hardwood, contentColor = Palette.Court),
                ) {
                    if (busy && summary != null) {
                        CircularProgressIndicator(color = Palette.Court, strokeWidth = 2.dp, modifier = Modifier.size(18.dp))
                        Spacer(Modifier.width(10.dp))
                    }
                    Text(confirmLabel, fontWeight = FontWeight.Bold)
                }
            }
        }
    }
}
