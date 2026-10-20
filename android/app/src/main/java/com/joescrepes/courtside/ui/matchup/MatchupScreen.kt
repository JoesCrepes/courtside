package com.joescrepes.courtside.ui.matchup

import androidx.compose.animation.core.animateFloatAsState
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
import androidx.compose.material.icons.automirrored.rounded.KeyboardArrowLeft
import androidx.compose.material.icons.automirrored.rounded.KeyboardArrowRight
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
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.ViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewModelScope
import androidx.lifecycle.viewmodel.compose.viewModel
import com.joescrepes.courtside.data.Api
import com.joescrepes.courtside.data.Matchup
import com.joescrepes.courtside.data.Side
import com.joescrepes.courtside.data.TeamSummary
import com.joescrepes.courtside.ui.ErrorPane
import com.joescrepes.courtside.ui.LoadingPane
import com.joescrepes.courtside.ui.LocalGraph
import com.joescrepes.courtside.ui.Panel
import com.joescrepes.courtside.ui.SectionLabel
import com.joescrepes.courtside.ui.TeamLogo
import com.joescrepes.courtside.ui.attempt
import com.joescrepes.courtside.ui.friendly
import com.joescrepes.courtside.ui.pts
import com.joescrepes.courtside.ui.theme.Numeric
import com.joescrepes.courtside.ui.theme.Palette
import kotlinx.coroutines.async
import kotlinx.coroutines.coroutineScope
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

data class MatchupUi(
    val currentWeek: Int? = null,
    val week: Int? = null,
    val myTeamId: Int? = null,
    val matchups: List<Matchup> = emptyList(),
    val teams: Map<Int, TeamSummary> = emptyMap(),
    val loading: Boolean = true,
    val refreshing: Boolean = false,
    val error: String? = null,
)

class MatchupViewModel(private val api: Api) : ViewModel() {
    private val _ui = MutableStateFlow(MatchupUi())
    val ui: StateFlow<MatchupUi> = _ui

    init {
        load()
    }

    fun load(week: Int? = _ui.value.week, pullToRefresh: Boolean = false) {
        _ui.update { it.copy(loading = !pullToRefresh && it.matchups.isEmpty(), refreshing = pullToRefresh, error = null) }
        viewModelScope.launch {
            attempt {
                coroutineScope {
                    val ctx = async { api.context() }
                    val league = async { if (_ui.value.teams.isEmpty()) api.league() else null }
                    val board = api.scoreboard(week)
                    _ui.update {
                        it.copy(
                            currentWeek = ctx.await().matchupPeriod,
                            myTeamId = ctx.await().teamId,
                            week = board.week,
                            matchups = board.matchups,
                            teams = league.await()?.standings?.associateBy { t -> t.id } ?: it.teams,
                        )
                    }
                }
            }.onFailure { e -> _ui.update { it.copy(error = e.friendly()) } }
            _ui.update { it.copy(loading = false, refreshing = false) }
        }
    }

    fun shiftWeek(by: Int) {
        val w = (_ui.value.week ?: return) + by
        if (w >= 1) load(w)
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun MatchupScreen() {
    val graph = LocalGraph.current
    val vm: MatchupViewModel = viewModel { MatchupViewModel(graph.api) }
    val ui by vm.ui.collectAsStateWithLifecycle()

    when {
        ui.loading -> LoadingPane()
        ui.week == null -> ErrorPane(ui.error ?: "Couldn't load the scoreboard", onRetry = { vm.load() })
        else -> PullToRefreshBox(isRefreshing = ui.refreshing, onRefresh = { vm.load(pullToRefresh = true) }) {
            val mine = ui.matchups.firstOrNull { it.involves(ui.myTeamId) }
            val others = ui.matchups.filter { it !== mine }
            LazyColumn(
                contentPadding = PaddingValues(start = 16.dp, end = 16.dp, bottom = 24.dp),
                verticalArrangement = Arrangement.spacedBy(10.dp),
                modifier = Modifier.fillMaxSize(),
            ) {
                item { WeekHeader(ui, vm) }
                mine?.let { m -> item { Hero(m, ui) } }
                if (others.isNotEmpty()) {
                    item { SectionLabel("Around the league", Modifier.padding(top = 10.dp, start = 4.dp)) }
                    items(others, key = { it.id }) { CompactMatchup(it, ui.teams) }
                }
            }
        }
    }
}

@Composable
private fun WeekHeader(ui: MatchupUi, vm: MatchupViewModel) {
    val week = ui.week ?: return
    Row(Modifier.fillMaxWidth().statusBarsPadding().padding(top = 12.dp), verticalAlignment = Alignment.CenterVertically) {
        Column(Modifier.weight(1f).padding(start = 4.dp)) {
            Text("Matchup", style = MaterialTheme.typography.headlineMedium)
            Text(
                if (week == ui.currentWeek) "Week $week · this week" else "Week $week",
                style = MaterialTheme.typography.bodyMedium, color = Palette.TextDim,
            )
        }
        IconButton(onClick = { vm.shiftWeek(-1) }, enabled = week > 1) { Icon(Icons.AutoMirrored.Rounded.KeyboardArrowLeft, "Previous week") }
        IconButton(onClick = { vm.shiftWeek(1) }) { Icon(Icons.AutoMirrored.Rounded.KeyboardArrowRight, "Next week") }
    }
}

private fun status(m: Matchup, currentWeek: Int?): Pair<String, androidx.compose.ui.graphics.Color> = when {
    m.winner != "UNDECIDED" -> "FINAL" to Palette.TextDim
    currentWeek != null && m.week < currentWeek -> "FINAL" to Palette.TextDim
    m.week == currentWeek -> "LIVE" to Palette.Live
    else -> "UPCOMING" to Palette.TextFaint
}

@Composable
private fun Hero(m: Matchup, ui: MatchupUi) {
    val me = if (m.home?.teamId == ui.myTeamId) m.home else m.away
    val them = if (m.home?.teamId == ui.myTeamId) m.away else m.home
    val (label, color) = status(m, ui.currentWeek)
    val myPts = me?.points ?: 0.0
    val theirPts = them?.points ?: 0.0
    val share by animateFloatAsState(if (myPts + theirPts > 0) (myPts / (myPts + theirPts)).toFloat() else 0.5f, label = "share")

    Panel(
        Modifier.background(
            Brush.verticalGradient(listOf(Palette.Hardwood.copy(alpha = 0.10f), Palette.Panel.copy(alpha = 0f))),
            RoundedCornerShape(20.dp),
        ),
        padding = PaddingValues(20.dp),
    ) {
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.Center, verticalAlignment = Alignment.CenterVertically) {
            Box(Modifier.size(7.dp).clip(CircleShape).background(color))
            Spacer(Modifier.width(6.dp))
            Text(label, style = MaterialTheme.typography.labelSmall, color = color)
        }
        Spacer(Modifier.height(16.dp))
        Row(verticalAlignment = Alignment.CenterVertically) {
            HeroTeam(me, ui.teams, Modifier.weight(1f))
            Column(horizontalAlignment = Alignment.CenterHorizontally, modifier = Modifier.width(132.dp)) {
                Text(myPts.pts(), style = Numeric.copy(fontSize = 34.sp), color = if (myPts >= theirPts) Palette.Text else Palette.TextDim)
                Text("–", color = Palette.TextFaint)
                Text(theirPts.pts(), style = Numeric.copy(fontSize = 34.sp), color = if (theirPts > myPts) Palette.Text else Palette.TextDim)
            }
            HeroTeam(them, ui.teams, Modifier.weight(1f))
        }
        Spacer(Modifier.height(18.dp))
        Box(Modifier.fillMaxWidth().height(8.dp).clip(CircleShape).background(Palette.PanelHigh)) {
            Box(
                Modifier.fillMaxWidth(share).height(8.dp).clip(CircleShape)
                    .background(Brush.horizontalGradient(listOf(Palette.HardwoodDeep, Palette.Hardwood)))
            )
        }
    }
}

@Composable
private fun HeroTeam(side: Side?, teams: Map<Int, TeamSummary>, modifier: Modifier) {
    val team = side?.let { teams[it.teamId] }
    Column(modifier, horizontalAlignment = Alignment.CenterHorizontally) {
        TeamLogo(team?.logo, side?.name ?: "BYE", size = 56.dp)
        Spacer(Modifier.height(8.dp))
        Text(
            side?.name ?: "Bye", style = MaterialTheme.typography.titleSmall, textAlign = TextAlign.Center,
            maxLines = 2, overflow = TextOverflow.Ellipsis,
        )
        team?.let { Text("${it.wins}-${it.losses}", style = MaterialTheme.typography.bodySmall, color = Palette.TextDim) }
    }
}

@Composable
private fun CompactMatchup(m: Matchup, teams: Map<Int, TeamSummary>) {
    Panel(padding = PaddingValues(horizontal = 14.dp, vertical = 12.dp)) {
        CompactSide(m.home, teams, leading = (m.home?.points ?: 0.0) >= (m.away?.points ?: 0.0))
        Spacer(Modifier.height(8.dp))
        CompactSide(m.away, teams, leading = (m.away?.points ?: 0.0) > (m.home?.points ?: 0.0))
    }
}

@Composable
private fun CompactSide(side: Side?, teams: Map<Int, TeamSummary>, leading: Boolean) {
    Row(verticalAlignment = Alignment.CenterVertically) {
        TeamLogo(side?.let { teams[it.teamId]?.logo }, side?.name ?: "BYE", size = 28.dp)
        Spacer(Modifier.width(10.dp))
        Text(
            side?.name ?: "Bye", style = MaterialTheme.typography.bodyMedium, maxLines = 1, overflow = TextOverflow.Ellipsis,
            color = if (leading) Palette.Text else Palette.TextDim, modifier = Modifier.weight(1f),
        )
        Text((side?.points ?: 0.0).pts(), style = Numeric.copy(fontSize = 16.sp), color = if (leading) Palette.Text else Palette.TextDim)
    }
}
