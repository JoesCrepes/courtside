package com.joescrepes.courtside.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.rounded.EmojiEvents
import androidx.compose.material.icons.rounded.PersonSearch
import androidx.compose.material.icons.rounded.Scoreboard
import androidx.compose.material.icons.rounded.SportsBasketball
import androidx.compose.material3.Icon
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.NavigationBarItemDefaults
import androidx.compose.material3.Scaffold
import androidx.compose.material3.SnackbarHost
import androidx.compose.material3.SnackbarHostState
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.joescrepes.courtside.ui.league.LeagueScreen
import com.joescrepes.courtside.ui.lineup.LineupScreen
import com.joescrepes.courtside.ui.matchup.MatchupScreen
import com.joescrepes.courtside.ui.players.PlayersScreen
import com.joescrepes.courtside.ui.theme.Palette

private enum class Tab(val label: String, val icon: ImageVector) {
    Lineup("Lineup", Icons.Rounded.SportsBasketball),
    Players("Players", Icons.Rounded.PersonSearch),
    Matchup("Matchup", Icons.Rounded.Scoreboard),
    League("League", Icons.Rounded.EmojiEvents),
}

@Composable
fun Root() {
    val session by LocalGraph.current.auth.session.collectAsStateWithLifecycle()
    if (session == null) LoginScreen() else Shell()
}

@Composable
private fun Shell() {
    var tab by rememberSaveable { mutableStateOf(Tab.Lineup) }
    val snackbar = remember { SnackbarHostState() }
    CompositionLocalProvider(LocalSnackbar provides snackbar) {
        Scaffold(
            containerColor = Palette.Court,
            snackbarHost = { SnackbarHost(snackbar) },
            bottomBar = {
                Column {
                    Box(Modifier.fillMaxWidth().height(1.dp).background(Palette.Line))
                    NavigationBar(containerColor = Palette.Court, tonalElevation = 0.dp) {
                        Tab.entries.forEach { t ->
                            NavigationBarItem(
                                selected = tab == t,
                                onClick = { tab = t },
                                icon = { Icon(t.icon, contentDescription = t.label) },
                                label = { Text(t.label) },
                                colors = NavigationBarItemDefaults.colors(
                                    selectedIconColor = Palette.Hardwood,
                                    selectedTextColor = Palette.Hardwood,
                                    indicatorColor = Palette.Hardwood.copy(alpha = 0.14f),
                                    unselectedIconColor = Palette.TextFaint,
                                    unselectedTextColor = Palette.TextFaint,
                                ),
                            )
                        }
                    }
                }
            },
        ) { inner ->
            Box(Modifier.fillMaxSize().padding(bottom = inner.calculateBottomPadding())) {
                when (tab) {
                    Tab.Lineup -> LineupScreen()
                    Tab.Players -> PlayersScreen()
                    Tab.Matchup -> MatchupScreen()
                    Tab.League -> LeagueScreen()
                }
            }
        }
    }
}

