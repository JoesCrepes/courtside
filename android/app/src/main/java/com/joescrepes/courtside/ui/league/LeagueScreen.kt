package com.joescrepes.courtside.ui.league

import androidx.compose.foundation.background
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
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.rounded.Logout
import androidx.compose.material.icons.rounded.Add
import androidx.compose.material.icons.rounded.Remove
import androidx.compose.material.icons.rounded.SwapHoriz
import androidx.compose.material.icons.rounded.SwapVert
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.pulltorefresh.PullToRefreshBox
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.ViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewModelScope
import androidx.lifecycle.viewmodel.compose.viewModel
import com.joescrepes.courtside.data.ActivityEntry
import com.joescrepes.courtside.data.ActivityItem
import com.joescrepes.courtside.data.Api
import com.joescrepes.courtside.data.League
import com.joescrepes.courtside.data.TeamSummary
import com.joescrepes.courtside.ui.ErrorPane
import com.joescrepes.courtside.ui.LoadingPane
import com.joescrepes.courtside.ui.LocalGraph
import com.joescrepes.courtside.ui.Panel
import com.joescrepes.courtside.ui.SectionLabel
import com.joescrepes.courtside.ui.TeamLogo
import com.joescrepes.courtside.ui.attempt
import com.joescrepes.courtside.ui.friendly
import com.joescrepes.courtside.ui.theme.Grotesk
import com.joescrepes.courtside.ui.theme.Numeric
import com.joescrepes.courtside.ui.theme.Palette
import com.joescrepes.courtside.ui.timeAgo
import kotlinx.coroutines.async
import kotlinx.coroutines.coroutineScope
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

data class LeagueUi(
    val league: League? = null,
    val activity: List<ActivityEntry> = emptyList(),
    val myTeamId: Int? = null,
    val email: String? = null,
    val loading: Boolean = true,
    val refreshing: Boolean = false,
    val error: String? = null,
)

class LeagueViewModel(private val api: Api) : ViewModel() {
    private val _ui = MutableStateFlow(LeagueUi())
    val ui: StateFlow<LeagueUi> = _ui

    init {
        load()
    }

    fun load(pullToRefresh: Boolean = false) {
        _ui.update { it.copy(loading = !pullToRefresh && it.league == null, refreshing = pullToRefresh, error = null) }
        viewModelScope.launch {
            attempt {
                coroutineScope {
                    val ctx = async { api.context() }
                    val league = async { api.league() }
                    val activity = async { api.activity() }
                    _ui.update {
                        it.copy(
                            league = league.await(), activity = activity.await().activity,
                            myTeamId = ctx.await().teamId, email = ctx.await().email,
                        )
                    }
                }
            }.onFailure { e -> _ui.update { it.copy(error = e.friendly()) } }
            _ui.update { it.copy(loading = false, refreshing = false) }
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun LeagueScreen() {
    val graph = LocalGraph.current
    val vm: LeagueViewModel = viewModel { LeagueViewModel(graph.api) }
    val ui by vm.ui.collectAsStateWithLifecycle()

    when {
        ui.loading -> LoadingPane()
        ui.league == null -> ErrorPane(ui.error ?: "Couldn't load the league", onRetry = { vm.load() })
        else -> PullToRefreshBox(isRefreshing = ui.refreshing, onRefresh = { vm.load(pullToRefresh = true) }) {
            val league = ui.league!!
            val teams = league.standings.associateBy { it.id }
            LazyColumn(
                contentPadding = PaddingValues(start = 16.dp, end = 16.dp, bottom = 24.dp),
                verticalArrangement = Arrangement.spacedBy(10.dp),
                modifier = Modifier.fillMaxSize(),
            ) {
                item {
                    Row(Modifier.fillMaxWidth().statusBarsPadding().padding(top = 12.dp), verticalAlignment = Alignment.CenterVertically) {
                        Column(Modifier.weight(1f).padding(start = 4.dp)) {
                            Text(league.name ?: "League", style = MaterialTheme.typography.headlineMedium)
                            Text(
                                listOfNotNull(
                                    "${league.standings.size} teams",
                                    when (league.scoringType) {
                                        "H2H_POINTS" -> "H2H points"
                                        "H2H_CATEGORY", "H2H_MOST_CATEGORIES" -> "H2H categories"
                                        "ROTO" -> "Roto"
                                        else -> null
                                    },
                                    league.acquisitions.perWeek?.let { "${it.toInt()} add/week" },
                                ).joinToString(" · "),
                                style = MaterialTheme.typography.bodyMedium, color = Palette.TextDim,
                            )
                        }
                        IconButton(onClick = { graph.auth.signOut() }) {
                            Icon(Icons.AutoMirrored.Rounded.Logout, "Sign out", tint = Palette.TextDim)
                        }
                    }
                }
                item { Standings(league.standings, ui.myTeamId) }
                if (ui.activity.isNotEmpty()) {
                    item { SectionLabel("Activity", Modifier.padding(top = 10.dp, start = 4.dp)) }
                    items(ui.activity) { ActivityCard(it, teams) }
                }
                ui.email?.let { email ->
                    item {
                        Text(
                            "Signed in as $email", style = MaterialTheme.typography.bodySmall, color = Palette.TextFaint,
                            modifier = Modifier.fillMaxWidth().padding(top = 12.dp),
                        )
                    }
                }
            }
        }
    }
}

@Composable
private fun Standings(teams: List<TeamSummary>, me: Int?) {
    Panel(padding = PaddingValues(vertical = 8.dp)) {
        Row(Modifier.padding(horizontal = 16.dp, vertical = 6.dp)) {
            Text("TEAM", style = MaterialTheme.typography.labelSmall, color = Palette.TextFaint, modifier = Modifier.weight(1f).padding(start = 30.dp))
            Text("W-L", style = MaterialTheme.typography.labelSmall, color = Palette.TextFaint, modifier = Modifier.width(52.dp))
            Text("PF", style = MaterialTheme.typography.labelSmall, color = Palette.TextFaint, modifier = Modifier.width(64.dp))
        }
        teams.forEachIndexed { i, t ->
            val mine = t.id == me
            Row(
                Modifier
                    .fillMaxWidth()
                    .background(if (mine) Palette.Hardwood.copy(alpha = 0.08f) else Color.Transparent)
                    .padding(horizontal = 16.dp, vertical = 8.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Text(
                    "${t.playoffSeed ?: (i + 1)}", fontFamily = Grotesk, fontWeight = FontWeight.Bold, fontSize = 13.sp,
                    color = if (mine) Palette.Hardwood else Palette.TextDim, modifier = Modifier.width(22.dp),
                )
                TeamLogo(t.logo, t.name, size = 28.dp)
                Spacer(Modifier.width(10.dp))
                Text(
                    t.name, style = MaterialTheme.typography.bodyMedium, maxLines = 1, overflow = TextOverflow.Ellipsis,
                    fontWeight = if (mine) FontWeight.SemiBold else FontWeight.Normal, modifier = Modifier.weight(1f),
                )
                Text("${t.wins}-${t.losses}", style = Numeric.copy(fontSize = 14.sp), modifier = Modifier.width(52.dp))
                Text(t.pointsFor.toInt().toString(), style = Numeric.copy(fontSize = 14.sp), color = Palette.TextDim, modifier = Modifier.width(64.dp))
            }
        }
    }
}

@Composable
private fun ActivityCard(entry: ActivityEntry, teams: Map<Int, TeamSummary>) {
    val team = entry.items.firstNotNullOfOrNull { it.teamId }?.let { teams[it] }
    Panel(padding = PaddingValues(horizontal = 14.dp, vertical = 12.dp)) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            TeamLogo(team?.logo, team?.name ?: "?", size = 24.dp)
            Spacer(Modifier.width(8.dp))
            Text(team?.name ?: "League", style = MaterialTheme.typography.titleSmall, modifier = Modifier.weight(1f), maxLines = 1, overflow = TextOverflow.Ellipsis)
            Text(timeAgo(entry.date), style = MaterialTheme.typography.bodySmall, color = Palette.TextFaint)
        }
        Spacer(Modifier.height(8.dp))
        Column(verticalArrangement = Arrangement.spacedBy(6.dp)) { entry.items.forEach { ActivityLine(it) } }
    }
}

@Composable
private fun ActivityLine(item: ActivityItem) {
    val (icon, tint) = when (item.kind) {
        "ADD" -> Icons.Rounded.Add to Palette.Live
        "DROP" -> Icons.Rounded.Remove to Palette.Out
        "TRADE" -> Icons.Rounded.SwapHoriz to Palette.Sky
        else -> Icons.Rounded.SwapVert to Palette.TextDim
    }
    Row(verticalAlignment = Alignment.CenterVertically) {
        Box(Modifier.size(22.dp).clip(CircleShape).background(tint.copy(alpha = 0.14f)), contentAlignment = Alignment.Center) {
            Icon(icon, null, tint = tint, modifier = Modifier.size(14.dp))
        }
        Spacer(Modifier.width(10.dp))
        Text(item.player ?: "Player ${item.playerId}", style = MaterialTheme.typography.bodyMedium, modifier = Modifier.weight(1f))
        if (item.kind == "MOVE" && item.fromSlot != null && item.toSlot != null) {
            Text("${item.fromSlot} → ${item.toSlot}", style = MaterialTheme.typography.bodySmall, color = Palette.TextDim)
        }
    }
}
