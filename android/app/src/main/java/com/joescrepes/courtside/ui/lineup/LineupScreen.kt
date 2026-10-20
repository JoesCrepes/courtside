package com.joescrepes.courtside.ui.lineup

import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.animateColorAsState
import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.animation.expandVertically
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.animation.shrinkVertically
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.itemsIndexed
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.rounded.KeyboardArrowLeft
import androidx.compose.material.icons.automirrored.rounded.KeyboardArrowRight
import androidx.compose.material.icons.rounded.Close
import androidx.compose.material.icons.rounded.Lock
import androidx.compose.material.icons.rounded.SwapVert
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.pulltorefresh.PullToRefreshBox
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.alpha
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewmodel.compose.viewModel
import com.joescrepes.courtside.data.Matchup
import com.joescrepes.courtside.data.Player
import com.joescrepes.courtside.data.TeamSummary
import com.joescrepes.courtside.ui.ConfirmSheet
import com.joescrepes.courtside.ui.ErrorPane
import com.joescrepes.courtside.ui.Headshot
import com.joescrepes.courtside.ui.InjuryTag
import com.joescrepes.courtside.ui.LoadingPane
import com.joescrepes.courtside.ui.LocalGraph
import com.joescrepes.courtside.ui.LocalSnackbar
import com.joescrepes.courtside.ui.NbaLogo
import com.joescrepes.courtside.ui.Panel
import com.joescrepes.courtside.ui.SectionLabel
import com.joescrepes.courtside.ui.StatColumn
import com.joescrepes.courtside.ui.TeamLogo
import com.joescrepes.courtside.ui.dateFor
import com.joescrepes.courtside.ui.dayLabel
import com.joescrepes.courtside.ui.label
import com.joescrepes.courtside.ui.pts
import com.joescrepes.courtside.ui.theme.Grotesk
import com.joescrepes.courtside.ui.theme.Numeric
import com.joescrepes.courtside.ui.theme.Palette
import java.time.format.DateTimeFormatter
import java.util.Locale

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun LineupScreen() {
    val graph = LocalGraph.current
    val vm: LineupViewModel = viewModel { LineupViewModel(graph.api) }
    val ui by vm.ui.collectAsStateWithLifecycle()
    val snackbar = LocalSnackbar.current

    LaunchedEffect(ui.message) {
        ui.message?.let { snackbar.showSnackbar(it); vm.messageShown() }
    }

    when {
        ui.loading -> LoadingPane()
        ui.roster == null -> ErrorPane(ui.error ?: "Couldn't load your lineup", onRetry = { vm.load() })
        else -> PullToRefreshBox(
            isRefreshing = ui.refreshing,
            onRefresh = { vm.load(pullToRefresh = true) },
            modifier = Modifier.fillMaxSize(),
        ) {
            LineupList(ui, vm)
        }
    }

    ui.sheet?.let { sheet ->
        ConfirmSheet(
            title = "Lineup change",
            summary = sheet.preview?.summary,
            busy = sheet.busy,
            error = sheet.error,
            note = sheet.note,
            confirmLabel = "Confirm move",
            onConfirm = vm::confirm,
            onDismiss = vm::dismissSheet,
        )
    }
}

@Composable
private fun LineupList(ui: LineupUi, vm: LineupViewModel) {
    val roster = ui.roster ?: return
    val seats = ui.seats
    val starters = seats.filter { it.slot != BENCH && it.slot != IR }
    val bench = seats.filter { it.slot == BENCH }
    val ir = seats.filter { it.slot == IR }
    val playing = starters.count { it.player?.game != null }

    LazyColumn(
        contentPadding = PaddingValues(start = 16.dp, end = 16.dp, bottom = 24.dp),
        verticalArrangement = Arrangement.spacedBy(8.dp),
        modifier = Modifier.fillMaxSize(),
    ) {
        item {
            Header(roster.name, roster.logo, "${roster.wins}-${roster.losses}${if (roster.ties > 0) "-${roster.ties}" else ""}")
        }
        ui.matchup?.let { m -> item { MatchupStrip(m, ui.myTeamId, ui.teams) } }
        item { DayBar(ui, playing, starters.size, vm) }
        item {
            AnimatedVisibility(
                visible = ui.selected != null,
                enter = expandVertically() + fadeIn(),
                exit = shrinkVertically() + fadeOut(),
            ) {
                ui.selected?.let { MoveBanner(it, onCancel = vm::cancelSelection) }
            }
        }
        item { SectionLabel("Starters", Modifier.padding(top = 8.dp, start = 4.dp), trailing = "PROJ") }
        itemsIndexed(starters, key = { i, seat -> "s$i-${seat.player?.id}" }) { _, seat -> SeatRow(seat, ui, vm) }
        item { SectionLabel("Bench", Modifier.padding(top = 12.dp, start = 4.dp)) }
        itemsIndexed(bench, key = { i, seat -> "b$i-${seat.player?.id}" }) { _, seat -> SeatRow(seat, ui, vm) }
        if (ir.isNotEmpty()) {
            item { SectionLabel("Injured reserve", Modifier.padding(top = 12.dp, start = 4.dp)) }
            itemsIndexed(ir, key = { i, seat -> "ir$i-${seat.player?.id}" }) { _, seat -> SeatRow(seat, ui, vm) }
        }
    }
}

@Composable
private fun Header(name: String, logo: String?, record: String) {
    Row(
        Modifier.fillMaxWidth().statusBarsPadding().padding(top = 16.dp, bottom = 8.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        TeamLogo(logo, name, size = 48.dp)
        Spacer(Modifier.width(14.dp))
        Column(Modifier.weight(1f)) {
            Text(name, style = MaterialTheme.typography.headlineSmall, maxLines = 1, overflow = TextOverflow.Ellipsis)
            Text(record, style = MaterialTheme.typography.bodyMedium, color = Palette.TextDim)
        }
    }
}

@Composable
private fun MatchupStrip(m: Matchup, me: Int?, teams: Map<Int, TeamSummary>) {
    val mine = if (m.home?.teamId == me) m.home else m.away
    val theirs = if (m.home?.teamId == me) m.away else m.home
    val myPts = mine?.points ?: 0.0
    val theirPts = theirs?.points ?: 0.0
    val share by animateFloatAsState(if (myPts + theirPts > 0) (myPts / (myPts + theirPts)).toFloat() else 0.5f, label = "share")
    val ahead = myPts >= theirPts

    Panel(padding = PaddingValues(horizontal = 16.dp, vertical = 14.dp)) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Text("WEEK ${m.week}", style = MaterialTheme.typography.labelSmall, color = Palette.Hardwood)
            Spacer(Modifier.weight(1f))
            Text("vs ${theirs?.name ?: "BYE"}", style = MaterialTheme.typography.labelMedium, color = Palette.TextDim, maxLines = 1, overflow = TextOverflow.Ellipsis)
        }
        Spacer(Modifier.height(8.dp))
        Row(verticalAlignment = Alignment.CenterVertically) {
            Text(myPts.pts(), style = Numeric.copy(fontSize = 30.sp), color = if (ahead) Palette.Text else Palette.TextDim)
            Spacer(Modifier.weight(1f))
            theirs?.let { TeamLogo(teams[it.teamId]?.logo, it.name ?: "", size = 22.dp) }
            Spacer(Modifier.width(8.dp))
            Text(theirPts.pts(), style = Numeric.copy(fontSize = 30.sp), color = if (!ahead) Palette.Text else Palette.TextDim)
        }
        Spacer(Modifier.height(10.dp))
        Box(Modifier.fillMaxWidth().height(6.dp).clip(CircleShape).background(Palette.PanelHigh)) {
            Box(
                Modifier.fillMaxWidth(share).height(6.dp).clip(CircleShape)
                    .background(Brush.horizontalGradient(listOf(Palette.HardwoodDeep, Palette.Hardwood)))
            )
        }
    }
}

private val dayFormat = DateTimeFormatter.ofPattern("EEE, MMM d", Locale.US)

@Composable
private fun DayBar(ui: LineupUi, playing: Int, starters: Int, vm: LineupViewModel) {
    val day = ui.day ?: return
    val today = ui.today ?: day
    Panel(padding = PaddingValues(horizontal = 6.dp, vertical = 6.dp)) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            IconButton(onClick = { vm.shiftDay(-1) }, enabled = day > 1) {
                Icon(Icons.AutoMirrored.Rounded.KeyboardArrowLeft, "Previous day")
            }
            Column(
                Modifier.weight(1f).clip(RoundedCornerShape(12.dp)).clickable(enabled = day != today) { vm.goToToday() },
                horizontalAlignment = Alignment.CenterHorizontally,
            ) {
                Text(dayLabel(day, today), style = MaterialTheme.typography.titleMedium, color = if (day == today) Palette.Hardwood else Palette.Text)
                Text(
                    "${dayFormat.format(dateFor(day, today))} · $playing of $starters starters play",
                    style = MaterialTheme.typography.bodySmall, color = Palette.TextDim,
                )
            }
            IconButton(onClick = { vm.shiftDay(1) }) {
                Icon(Icons.AutoMirrored.Rounded.KeyboardArrowRight, "Next day")
            }
        }
    }
}

@Composable
private fun MoveBanner(player: Player, onCancel: () -> Unit) {
    Row(
        Modifier
            .fillMaxWidth()
            .padding(top = 4.dp)
            .clip(RoundedCornerShape(16.dp))
            .background(Palette.Hardwood.copy(alpha = 0.14f))
            .border(1.dp, Palette.Hardwood.copy(alpha = 0.5f), RoundedCornerShape(16.dp))
            .padding(start = 14.dp, end = 4.dp, top = 4.dp, bottom = 4.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Icon(Icons.Rounded.SwapVert, null, tint = Palette.Hardwood, modifier = Modifier.size(18.dp))
        Spacer(Modifier.width(10.dp))
        Column(Modifier.weight(1f)) {
            Text("Moving ${player.name}", style = MaterialTheme.typography.titleSmall, maxLines = 1, overflow = TextOverflow.Ellipsis)
            Text("Tap a highlighted slot", style = MaterialTheme.typography.bodySmall, color = Palette.TextDim)
        }
        IconButton(onClick = onCancel) { Icon(Icons.Rounded.Close, "Cancel move", tint = Palette.TextDim) }
    }
}

private enum class SeatState { Normal, Selected, Target, Dimmed }

@Composable
private fun SeatRow(seat: Seat, ui: LineupUi, vm: LineupViewModel) {
    val selected = ui.selected
    val state = when {
        selected == null -> SeatState.Normal
        seat.player?.id == selected.id -> SeatState.Selected
        ui.roster != null && intentFor(selected, seat, ui.roster.roster, ui.slotCounts) != null -> SeatState.Target
        else -> SeatState.Dimmed
    }
    val border by animateColorAsState(
        when (state) {
            SeatState.Selected -> Palette.Hardwood
            SeatState.Target -> Palette.Hardwood.copy(alpha = 0.45f)
            else -> Palette.Line
        },
        label = "border",
    )
    val background by animateColorAsState(
        if (state == SeatState.Selected) Palette.Hardwood.copy(alpha = 0.10f) else Palette.Panel, label = "bg",
    )
    val alpha by animateFloatAsState(if (state == SeatState.Dimmed) 0.35f else 1f, label = "alpha")
    val player = seat.player
    val locked = player?.lineupLocked == true

    Row(
        Modifier
            .fillMaxWidth()
            .alpha(alpha)
            .clip(RoundedCornerShape(18.dp))
            .background(background)
            .border(if (state == SeatState.Normal || state == SeatState.Dimmed) 1.dp else 1.5.dp, border, RoundedCornerShape(18.dp))
            .clickable(enabled = state != SeatState.Dimmed) { vm.tapSeat(seat) }
            .padding(horizontal = 12.dp, vertical = 10.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        SlotBadge(seat.slot, highlighted = state == SeatState.Target)
        Spacer(Modifier.width(12.dp))
        if (player == null) {
            Text("Empty", style = MaterialTheme.typography.bodyMedium, color = Palette.TextFaint, modifier = Modifier.weight(1f).padding(vertical = 12.dp))
            return@Row
        }
        Box {
            Headshot(player.id, player.name, ring = if (player.game != null) Palette.Live.copy(alpha = 0.7f) else Color.Transparent)
        }
        Spacer(Modifier.width(12.dp))
        Column(Modifier.weight(1f)) {
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                Text(
                    player.name, style = MaterialTheme.typography.titleSmall, maxLines = 1, overflow = TextOverflow.Ellipsis,
                    modifier = Modifier.weight(1f, fill = false),
                )
                InjuryTag(player.injuryStatus)
                if (locked) Icon(Icons.Rounded.Lock, "Locked", tint = Palette.TextFaint, modifier = Modifier.size(13.dp))
            }
            Spacer(Modifier.height(2.dp))
            Row(verticalAlignment = Alignment.CenterVertically) {
                NbaLogo(player.proTeam, size = 14.dp)
                Spacer(Modifier.width(5.dp))
                val game = player.game
                Text(
                    buildString {
                        append(player.positions.joinToString("/"))
                        append(" · ")
                        append(game?.label() ?: "No game")
                    },
                    style = MaterialTheme.typography.bodySmall,
                    color = if (game != null) Palette.TextDim else Palette.TextFaint,
                    maxLines = 1, overflow = TextOverflow.Ellipsis,
                )
            }
        }
        Spacer(Modifier.width(8.dp))
        StatColumn(player.projected?.pts() ?: "–", "PROJ", color = if (player.game != null) Palette.Text else Palette.TextFaint)
    }
}

@Composable
private fun SlotBadge(slot: String, highlighted: Boolean) {
    val tint = when (slot) {
        BENCH -> Palette.TextDim
        IR -> Palette.Out
        else -> Palette.Hardwood
    }
    Box(
        Modifier
            .width(46.dp)
            .height(30.dp)
            .clip(RoundedCornerShape(10.dp))
            .background(if (highlighted) tint.copy(alpha = 0.32f) else tint.copy(alpha = 0.12f)),
        contentAlignment = Alignment.Center,
    ) {
        Text(slot, color = tint, fontFamily = Grotesk, fontWeight = FontWeight.Bold, fontSize = if (slot.length > 3) 10.sp else 12.sp)
    }
}
